"""Named pipe listener for Natural Voice TTS.

Creates a Windows named pipe server that receives length-prefixed UTF-8 text
messages from external clients (e.g. the MCP TTS server) and enqueues them
for synthesis by the TTS worker thread.

Protocol (client → server):
  - 4-byte little-endian uint32: byte length of the UTF-8 payload
  - N bytes: UTF-8 encoded text

Protocol (server → client):
  - 2 bytes: b'OK' acknowledgment

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
            # Read 4-byte length header
            hr, header = win32file.ReadFile(pipe, 4)
            if not header or len(header) < 4:
                logger.debug("Client sent empty header, disconnecting")
                break

            length = struct.unpack('<I', header)[0]
            if length == 0:
                logger.debug("Zero-length message, skipping")
                win32file.WriteFile(pipe, b'OK')
                continue

            if length > BUFFER_SIZE:
                logger.warning("Message length %d exceeds buffer %d, dropping", length, BUFFER_SIZE)
                break

            # Read payload
            hr, data = win32file.ReadFile(pipe, length)
            if not data:
                logger.debug("Empty payload, disconnecting")
                break

            text = data.decode('utf-8')
            logger.debug("Received message (%d chars): %.80s...", len(text), text)

            # Acknowledge receipt before processing (so client doesn't block)
            win32file.WriteFile(pipe, b'OK')

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
