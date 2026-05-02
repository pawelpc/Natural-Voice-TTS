"""Standalone test script for the Natural Voice TTS named pipe.

Usage:
    python test_pipe.py "Hello, this is a test of the named pipe."
    python test_pipe.py --stop

Requires the Natural Voice TTS tray app to be running first.
"""

import struct
import sys

PIPE_NAME = r'\\.\pipe\NaturalVoiceTTS'
STOP_SENTINEL = '__STOP__'


def send_to_pipe(text: str) -> str:
    """Send text to the named pipe. Returns the server's response string."""
    try:
        import win32file
        import pywintypes
    except ImportError:
        print("ERROR: pywin32 is not installed.")
        print("Install with: pip install pywin32")
        sys.exit(1)

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
    except Exception as e:
        print(f"ERROR: Could not connect to pipe '{PIPE_NAME}'.")
        print(f"  Details: {e}")
        print()
        print("Make sure the Natural Voice TTS tray app is running first.")
        sys.exit(1)

    try:
        encoded = text.encode('utf-8')
        header = struct.pack('<I', len(encoded))
        win32file.WriteFile(handle, header + encoded)

        hr, response = win32file.ReadFile(handle, 2)
        return response.decode('utf-8')
    finally:
        win32file.CloseHandle(handle)


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  python test_pipe.py \"Text to speak\"")
        print("  python test_pipe.py --stop")
        sys.exit(0)

    if args[0] == '--stop':
        text = STOP_SENTINEL
        label = '__STOP__ sentinel'
    else:
        text = ' '.join(args)
        label = f'text ({len(text)} chars)'

    print(f"Connecting to {PIPE_NAME}...")
    print(f"Sending {label}: {text!r}")

    response = send_to_pipe(text)

    if response == 'OK':
        print(f"Success! Server responded: {response!r}")
        if text == STOP_SENTINEL:
            print("Stop command sent — playback should have halted.")
        else:
            print("Text enqueued — listen for audio.")
    else:
        print(f"Unexpected response: {response!r}")
        sys.exit(1)


if __name__ == '__main__':
    main()
