# Team Lead Instructions: Natural Voice TTS — Phase 5

## Startup Command

At the start of your session, read these files in order:
1. `_team-lead-brief.md` — Phases 1-4 spec (understand the full architecture you're extending)
2. This file (`_team-lead-instructions.md`)
3. `_context/kokoro-integration-notes.md` — Kokoro-specific technical details
4. `src/app.py` — the system tray app you're modifying
5. `src/hotkeys.py` — understand existing callback patterns
6. `src/audio_player.py` — understand stop/pause/reset API

Read ALL existing `src/` files before writing any code. You need to understand the threading model, queue usage, and shutdown sequence.

## Build Order

Follow this sequence strictly. Test each part before moving to the next.

### Step 1: `src/pipe_listener.py` — CREATE
Named pipe listener module. Key decisions:
- Use `win32pipe.CreateNamedPipe()` with `PIPE_ACCESS_DUPLEX` and `PIPE_TYPE_BYTE | PIPE_READMODE_BYTE`
- Length-prefixed protocol: 4-byte LE uint32 length header, then UTF-8 payload
- After reading a message, write back `OK` (2 bytes) as acknowledgment
- Run in a loop: create pipe → connect → read messages → client disconnects → loop
- Accept a `stop_event: threading.Event` — check it between connections to allow clean shutdown
- Handle `__STOP__` sentinel: call the stop callback instead of enqueuing text
- Log all activity at DEBUG level, errors at ERROR level

### Step 2: `src/app.py` — MODIFY
Minimal changes only:
- Import `pipe_listener`
- In the app initialization (after tray icon setup), start the pipe listener thread:
  ```python
  _pipe_stop_event = threading.Event()
  pipe_listener.start_pipe_listener(_text_queue, _pipe_stop_event, on_stop=_on_stop)
  ```
- In the quit handler, set `_pipe_stop_event` before other cleanup
- The `on_stop` callback should be `_on_stop` (the existing stop handler that drains the queue and stops audio)

### Step 3: Test pipe listener
Write `test_pipe.py` in the project root. This is a standalone script Paul runs to verify the pipe works:
```
python test_pipe.py "Hello, this is a test of the named pipe."
```
It should connect to the pipe, send the text, read the OK response, and print success/failure.

### Step 4: `mcp_tts_server/server.py` — CREATE
MCP server using the `mcp` Python SDK. Key points:
- Use `@server.tool()` decorator for `speak` and `stop_speaking`
- The pipe CLIENT code here is simple: open pipe with `open(PIPE_NAME, 'r+b')` or `win32file.CreateFile()` — whichever is simpler
- Handle pipe not found (TTS app not running) → return clear error string
- Use `mcp.server.stdio` transport
- NO kokoro imports. NO torch imports. This file must start instantly.

### Step 5: `mcp_tts_server/requirements.txt` — CREATE
```
mcp>=1.0
pywin32>=306
```

### Step 6: `mcp_tts_server/README.md` — CREATE
Document:
1. Prerequisites (Natural Voice TTS app must be running)
2. Install: `pip install -r requirements.txt`
3. Claude Desktop config JSON (exact content to paste)
4. System prompt text for toggle behavior
5. Usage: "Say 'speak your responses' to Claude"

### Step 7: `requirements.txt` — MODIFY
Add `pywin32>=306` to the main project requirements.

### Step 8: End-to-end test documentation
Add a section to the MCP server README explaining how to test manually:
1. Start TTS tray app
2. Run `python test_pipe.py "Test sentence"` — verify audio plays
3. Run `python mcp_tts_server/server.py` — verify it starts without error
4. Configure Claude Desktop and restart it
5. Tell Claude "speak your responses" and send a message

## Code Style

Match the existing codebase exactly:
- Python 3.11, type hints on function signatures
- Docstrings on all public functions
- Use `logging` module (not print)
- Constants at top of module
- Thread safety via `queue.Queue`, `threading.Event`, `threading.Lock`
- No classes where a function will do

## Important Technical Notes

### Named Pipe on Windows
```python
import win32pipe
import win32file

# Server side (in TTS app):
pipe = win32pipe.CreateNamedPipe(
    r'\\.\pipe\NaturalVoiceTTS',
    win32pipe.PIPE_ACCESS_DUPLEX,
    win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
    1,       # max instances
    65536,   # out buffer
    65536,   # in buffer
    0,       # default timeout
    None     # security attributes (default = same user)
)

# Block until client connects:
win32pipe.ConnectNamedPipe(pipe, None)

# Read length header (4 bytes):
hr, data = win32file.ReadFile(pipe, 4)
length = struct.unpack('<I', data)[0]

# Read payload:
hr, data = win32file.ReadFile(pipe, length)
text = data.decode('utf-8')

# Write acknowledgment:
win32file.WriteFile(pipe, b'OK')

# Disconnect and close for next client:
win32pipe.DisconnectNamedPipe(pipe)
win32file.CloseHandle(pipe)
```

### MCP Server Pattern
```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("natural-voice-tts")

@server.tool()
async def speak(text: str) -> str:
    """Speak text aloud via Natural Voice TTS."""
    try:
        _send_to_pipe(text)
        return "Speaking."
    except FileNotFoundError:
        return "Error: Natural Voice TTS is not running. Start the tray app first."

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Pipe Client Pattern (for MCP server and test script)
```python
import win32file

def _send_to_pipe(text: str) -> str:
    """Send text to the Natural Voice TTS named pipe. Returns response."""
    handle = win32file.CreateFile(
        r'\\.\pipe\NaturalVoiceTTS',
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        0, None,
        win32file.OPEN_EXISTING,
        0, None
    )
    try:
        encoded = text.encode('utf-8')
        header = struct.pack('<I', len(encoded))
        win32file.WriteFile(handle, header + encoded)
        hr, response = win32file.ReadFile(handle, 2)
        return response.decode('utf-8')
    finally:
        win32file.CloseHandle(handle)
```

## Reporting

When you complete work or hit a blocker, write a brief status note at the bottom of the main `_team-lead-instructions.md` file (NOT this staging copy) under the `## Session Notes` heading.

## What You Are NOT Doing

- No changes to tts_engine.py, audio_player.py, text_processor.py, hotkeys.py, config.py, or dialogs.py
- No Phase 4 packaging updates (installer, spec file, build script)
- No web server, HTTP API, or WebSocket
- No clipboard monitoring
- No Claude Desktop system prompt file — just document what Paul should use
