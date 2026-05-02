"""MCP TTS Server — forwards text to the Natural Voice TTS tray app via named pipe.

This server exposes two MCP tools:
  - speak(text)        — enqueues text for synthesis in the running TTS app
  - stop_speaking()    — stops current playback immediately

Transport: stdio (for Claude Desktop integration)

NO kokoro, NO torch, NO model loading. This file starts in under a second.
It is a pure text relay; the TTS app owns the audio pipeline.
"""

import asyncio
import struct
import logging

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

PIPE_NAME = r'\\.\pipe\NaturalVoiceTTS'
STOP_SENTINEL = '__STOP__'

# ---------------------------------------------------------------------------
# Pipe client helper
# ---------------------------------------------------------------------------

def _send_to_pipe(text: str) -> str:
    """Send a length-prefixed UTF-8 message to the TTS named pipe.

    Args:
        text: The text to send (or '__STOP__' to stop playback).

    Returns:
        The server's 2-byte response string (normally 'OK').

    Raises:
        FileNotFoundError: If the pipe does not exist (TTS app not running).
        OSError: On other pipe communication errors.
    """
    try:
        import win32file
        import pywintypes
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 is not installed. Run: pip install pywin32"
        ) from exc

    try:
        handle = win32file.CreateFile(
            PIPE_NAME,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0,    # no sharing
            None, # default security
            win32file.OPEN_EXISTING,
            0,    # default attributes
            None, # no template
        )
    except Exception as exc:
        error_code = getattr(exc, 'args', [None])[0]
        if error_code == 2:
            raise FileNotFoundError(
                f"Named pipe '{PIPE_NAME}' not found. "
                "Start the Natural Voice TTS tray app first."
            ) from exc
        raise OSError(f"Failed to connect to TTS pipe: {exc}") from exc

    try:
        encoded = text.encode('utf-8')
        header = struct.pack('<I', len(encoded))
        win32file.WriteFile(handle, header + encoded)
        hr, response = win32file.ReadFile(handle, 2)
        return response.decode('utf-8')
    except Exception as exc:
        raise OSError(f"Pipe communication error: {exc}") from exc
    finally:
        try:
            win32file.CloseHandle(handle)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("natural-voice-tts")


@mcp.tool()
async def speak(text: str) -> str:
    """Speak text aloud via Natural Voice TTS.

    Sends the given text to the running Natural Voice TTS application,
    which synthesizes and plays it using the Kokoro neural TTS engine.
    The TTS app must be running in the system tray.

    Supports existing hotkey controls: Ctrl+Win+X stops, Ctrl+Win+Z pauses.

    Args:
        text: The text to speak aloud. Large texts are automatically split
              into sentences by the TTS app.
    """
    logger.debug("speak() called with %d chars", len(text))
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None, _send_to_pipe, text
        )
        if response == 'OK':
            return "Speaking."
        else:
            return f"Unexpected response from TTS app: {response!r}"
    except FileNotFoundError as exc:
        return f"Error: {exc}"
    except OSError as exc:
        return f"Error: {exc}"
    except RuntimeError as exc:
        return f"Error: {exc}"


@mcp.tool()
async def stop_speaking() -> str:
    """Stop any currently playing speech immediately.

    Equivalent to pressing Ctrl+Win+X on the keyboard. Drains the
    synthesis queue so no further sentences are played.
    """
    logger.debug("stop_speaking() called")
    try:
        response = await asyncio.get_event_loop().run_in_executor(
            None, _send_to_pipe, STOP_SENTINEL
        )
        if response == 'OK':
            return "Stopped."
        else:
            return f"Unexpected response from TTS app: {response!r}"
    except FileNotFoundError as exc:
        return f"Error: {exc}"
    except OSError as exc:
        return f"Error: {exc}"
    except RuntimeError as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    )
    mcp.run()
