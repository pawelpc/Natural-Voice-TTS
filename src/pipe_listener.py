"""Named pipe listener for Natural Voice TTS.

Creates a Windows named pipe server that receives length-prefixed UTF-8 text
messages from external clients (e.g. the MCP TTS server) and enqueues them
for synthesis by the TTS worker thread.

Protocol (client → server):
  - 4-byte little-endian uint32: byte length of the UTF-8 payload
  - N bytes: UTF-8 encoded text

Protocol (server → client):
  - 2 bytes: b'OK' acknowledgment on success
  - 2 bytes: b'ER' if the message was rejected (too large or invalid UTF-8)

Special sentinel:
  - '__STOP__' payload triggers the on_stop callback instead of enqueueing.
"""

import queue
import struct
import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

PIPE_NAME = r'\\.\pipe\NaturalVoiceTTS'
BUFFER_SIZE = 65536  # 64 KB — sufficient for any typical response
STOP_SENTINEL = '__STOP__'

# 2-byte responses sent back to the client (must stay 2 bytes: the client
# reads exactly 2 bytes for its acknowledgment).
ACK_OK = b'OK'
ACK_ERROR = b'ER'


def _read_exactly(pipe, n: int, win32file) -> bytes:
    """Read exactly ``n`` bytes from a byte-mode named pipe.

    Windows byte-mode pipes (``PIPE_TYPE_BYTE``) do not guarantee that a single
    ``ReadFile`` returns all requested bytes, even when the peer wrote them in a
    single ``WriteFile`` — the data can arrive in fragments. A naive single-read
    therefore silently truncates the payload (dropping tail sentences) or slices
    through a multi-byte UTF-8 sequence (making ``decode`` raise and dropping the
    whole message). This loops until ``n`` bytes have accumulated, which is the
    correct framing behavior for length-prefixed messages.

    Args:
        pipe: The connected pipe handle.
        n: Exact number of bytes to read.
        win32file: The imported ``win32file`` module (passed in to avoid a
            top-level import that fails on non-Windows dev machines).

    Returns:
        Exactly ``n`` bytes.

    Raises:
        IOError: If the pipe reaches end-of-stream before ``n`` bytes arrive.
    """
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        hr, data = win32file.ReadFile(pipe, remaining)
        if not data:
            raise IOError(
                f"Pipe closed mid-read: expected {n} bytes, got {n - remaining}"
            )
        chunks.append(bytes(data))
        remaining -= len(data)
    return b''.join(chunks)


def _pipe_loop(
    text_queue: queue.Queue,
    stop_event: threading.Event,
    on_stop: Optional[Callable[[], None]],
) -> None:
    """Main loop: create pipe → wait for client → handle messages → repeat.

    Runs as a daemon thread. Checks stop_event between connections so the
    app can shut down cleanly without waiting for a client to connect.
    """
    try:
        import win32pipe
        import win32file
        import pywintypes
    except ImportError:
        logger.error(
            "pywin32 is not installed. Named pipe listener will not start. "
            "Install with: pip install pywin32"
        )
        return

    logger.info("Pipe listener starting on %s", PIPE_NAME)

    while not stop_event.is_set():
        pipe = None
        try:
            pipe = win32pipe.CreateNamedPipe(
                PIPE_NAME,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                1,            # max instances
                BUFFER_SIZE,  # out buffer
                BUFFER_SIZE,  # in buffer
                0,            # default timeout (50ms)
                None,         # security attributes (default = current user)
            )
            logger.debug("Pipe created, waiting for client...")

            # Block until a client connects (or the pipe is broken/closed).
            # This call blocks indefinitely; on shutdown the thread is a daemon
            # so it will be reaped when the process exits.
            win32pipe.ConnectNamedPipe(pipe, None)

            if stop_event.is_set():
                logger.debug("Stop event set, exiting pipe loop")
                break

            logger.debug("Client connected")
            _handle_client(pipe, text_queue, stop_event, on_stop, win32file, pywintypes)

        except Exception as e:
            # Don't crash the loop on unexpected errors; log and retry.
            logger.error("Pipe loop error: %s", e, exc_info=True)
        finally:
            if pipe is not None:
                try:
                    import win32pipe as _wp
                    import win32file as _wf
                    _wp.DisconnectNamedPipe(pipe)
                    _wf.CloseHandle(pipe)
                except Exception:
                    pass
                pipe = None

    logger.info("Pipe listener stopped")


def _handle_client(
    pipe,
    text_queue: queue.Queue,
    stop_event: threading.Event,
    on_stop: Optional[Callable[[], None]],
    win32file,
    pywintypes,
) -> None:
    """Read messages from a connected client until it disconnects.

    Each iteration: read 4-byte length header → read payload → enqueue → ACK.
    """
    while not stop_event.is_set():
        try:
            # Read 4-byte length header (accumulating short reads). A clean
            # disconnect between messages surfaces as an IOError/broken pipe
            # here, which is the normal way this loop ends.
            try:
                header = _read_exactly(pipe, 4, win32file)
            except IOError:
                logger.debug("Client closed before a full header arrived, disconnecting")
                break

            length = struct.unpack('<I', header)[0]
            if length == 0:
                logger.debug("Zero-length message, skipping")
                win32file.WriteFile(pipe, ACK_OK)
                continue

            if length > BUFFER_SIZE:
                # D3: don't silently drop — tell the client the message was
                # rejected so the MCP server can surface an error to the agent.
                logger.warning(
                    "Message length %d exceeds buffer %d, rejecting", length, BUFFER_SIZE
                )
                try:
                    win32file.WriteFile(pipe, ACK_ERROR)
                except Exception:
                    pass  # client may already be blocked writing; disconnect cleans up
                break

            # Read the full payload, looping until all `length` bytes arrive
            # (D1: this is where single-ReadFile short reads dropped sentences).
            data = _read_exactly(pipe, length, win32file)

            # Diagnostic: header-promised length vs. bytes actually accumulated.
            # With _read_exactly these always match; logging both proves the
            # pipe delivered the complete payload.
            logger.info(
                "Pipe payload: header=%d bytes, received=%d bytes", length, len(data)
            )

            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError as e:
                # Should no longer happen now that reads are complete, but if a
                # genuinely malformed payload arrives, signal the client rather
                # than swallowing the whole message.
                logger.error(
                    "Payload is not valid UTF-8 (%d bytes): %s", len(data), e
                )
                try:
                    win32file.WriteFile(pipe, ACK_ERROR)
                except Exception:
                    pass
                break

            logger.info("Received message: %d chars decoded", len(text))
            if len(text) > 200:
                logger.debug("Message head: %.100s", text)
                logger.debug("Message tail: %.100s", text[-100:])
            else:
                logger.debug("Message text: %s", text)

            # Acknowledge receipt before processing (so client doesn't block)
            win32file.WriteFile(pipe, ACK_OK)

            # Dispatch
            if text == STOP_SENTINEL:
                logger.info("Received STOP sentinel, calling on_stop")
                if on_stop is not None:
                    threading.Thread(target=on_stop, daemon=True, name='pipe-stop').start()
            else:
                logger.info("Enqueueing text from pipe (%d chars)", len(text))
                text_queue.put(text)

        except pywintypes.error as e:
            # Error 109 = ERROR_BROKEN_PIPE: client disconnected — normal exit.
            # Error 232 = ERROR_NO_DATA: client closed write end — normal exit.
            if e.args[0] in (109, 232):
                logger.debug("Client disconnected (error %d)", e.args[0])
            else:
                logger.error("Pipe read error: %s", e)
            break
        except IOError as e:
            # Raised by _read_exactly when the pipe closes partway through a
            # payload — the message was incomplete, so drop the connection.
            logger.warning("Incomplete message, disconnecting: %s", e)
            break
        except Exception as e:
            logger.error("Unexpected error handling pipe client: %s", e, exc_info=True)
            break


def start_pipe_listener(
    text_queue: queue.Queue,
    stop_event: threading.Event,
    on_stop: Optional[Callable[[], None]] = None,
) -> threading.Thread:
    """Start the named pipe listener as a daemon thread.

    Args:
        text_queue: Queue to put received text into (shared with TTS worker).
        stop_event: Set this event to signal the listener to stop.
        on_stop: Optional callback invoked when the '__STOP__' sentinel is
                 received. Should stop audio and drain the queue (same as
                 pressing Ctrl+Win+X).

    Returns:
        The started Thread object.
    """
    thread = threading.Thread(
        target=_pipe_loop,
        args=(text_queue, stop_event, on_stop),
        daemon=True,
        name='PipeListener',
    )
    thread.start()
    logger.info("Pipe listener thread started")
    return thread
