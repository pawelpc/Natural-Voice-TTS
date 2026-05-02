# Team Lead Brief: Natural Voice TTS — Phase 5: Claude Desktop Integration

**Prepared by:** Manager Agent
**Date:** 2026-05-02
**Model:** Sonnet (straightforward integration work, well-defined scope)
**Prerequisite:** Phases 1-3 verified working. Phase 4 (distribution) independent — not required for Phase 5.
**Deliverables:** Modified `app.py`, new `pipe_listener.py`, new `mcp_tts_server/` directory, updated `requirements.txt`, test script, integration documentation

---

## Project Summary

Add a named pipe listener to the existing Natural Voice TTS system tray app so external programs can send text to be spoken. Then build a lightweight MCP server that Claude Desktop calls as a `speak` tool, which forwards text to the named pipe. This gives Paul a conversational toggle: say "read your responses aloud" and Claude speaks via Kokoro; say "stop speaking" and it stops.

**Why named pipe + MCP relay (not direct MCP-to-Kokoro):**
- Reuses the already-loaded Kokoro engine in the running tray app (no duplicate 350MB model in RAM)
- Preserves existing hotkey controls — Ctrl+Win+X still stops audio, Ctrl+Win+Z still pauses
- The MCP server is trivially simple (no torch, no model loading, ~80 lines)
- Clean separation: TTS app owns audio, MCP server is just a text relay

---

## Architecture

```
Claude Desktop                    MCP TTS Server              Natural Voice TTS (tray app)
─────────────                    ──────────────              ────────────────────────────
User: "speak your responses"
  ↓
Claude calls speak(text) tool
  ↓                              \\.\pipe\NaturalVoiceTTS
  ↓ ──── MCP stdio ────→  Write text to named pipe ──────→  Pipe listener thread
                                                                ↓
                                                            _text_queue.put(text)
                                                                ↓
                                                            Worker thread (existing)
                                                                ↓
                                                            Kokoro synthesis → audio
                                                                ↓
                                                            sounddevice playback
```

**Control flow stays unchanged:** Ctrl+Win+X (stop) and Ctrl+Win+Z (pause/resume) work on pipe-sourced audio exactly as they do on hotkey-sourced audio, because both paths feed the same `_text_queue`.

---

## What You're Building

### Part A: Named Pipe Listener (modify existing app)

**New file:** `src/pipe_listener.py`

A daemon thread that creates a Windows named pipe and listens for incoming text. Each message received gets put into the app's existing `_text_queue`.

**Pipe specification:**
- Name: `\\.\pipe\NaturalVoiceTTS`
- Direction: Inbound (clients write, server reads)
- Protocol: Length-prefixed UTF-8 messages
  - Client writes 4-byte little-endian uint32 (message length in bytes)
  - Client writes UTF-8 encoded text of that length
  - Server reads, decodes, enqueues
  - Server writes back 2-byte response: `OK` (UTF-8) to confirm receipt
- Concurrency: Single-client at a time (adequate for MCP relay). Reconnects after each client disconnects.
- Timeout: Pipe operations use overlapped I/O with 5-second timeouts so the thread can check a stop event and shut down cleanly.

**Key implementation details:**
```python
import win32pipe
import win32file
import pywintypes
import struct
import threading
import logging

PIPE_NAME = r'\\.\pipe\NaturalVoiceTTS'
BUFFER_SIZE = 65536  # 64KB — more than enough for any response

def start_pipe_listener(text_queue, stop_event):
    """Start daemon thread that listens on named pipe and enqueues text."""
    thread = threading.Thread(
        target=_pipe_loop,
        args=(text_queue, stop_event),
        daemon=True,
        name='PipeListener'
    )
    thread.start()
    return thread
```

**Modified file:** `src/app.py`
- Import and start pipe listener thread during app initialization (after tray icon setup)
- Pass `_text_queue` and a stop event to the listener
- Stop the listener on app quit (set the stop event)

**New dependency:** `pywin32` (for `win32pipe`, `win32file`)
- This is a standard Windows Python package
- Add to `requirements.txt`: `pywin32>=306`

### Part B: MCP TTS Server

**New directory:** `mcp_tts_server/`

A minimal MCP server that exposes a `speak` tool. When Claude calls it, the server writes the text to the named pipe. That's all it does.

**Files:**

| File | Purpose |
|------|---------|
| `mcp_tts_server/server.py` | MCP server with `speak` and `stop` tools |
| `mcp_tts_server/requirements.txt` | `mcp>=1.0` (the Anthropic MCP Python SDK) |
| `mcp_tts_server/README.md` | Setup instructions for Claude Desktop config |

**Tool definitions:**

```python
@server.tool()
async def speak(text: str) -> str:
    """Speak the given text aloud using Natural Voice TTS.

    Send text to the running Natural Voice TTS application,
    which will synthesize and play it using the Kokoro neural
    TTS engine. The TTS app must be running in the system tray.

    Args:
        text: The text to speak aloud.
    """
    # Connect to named pipe, send length-prefixed message, read OK
    ...
    return "Speaking."

@server.tool()
async def stop_speaking() -> str:
    """Stop any currently playing speech immediately."""
    # Send a special control message (e.g., empty string or "__STOP__" sentinel)
    ...
    return "Stopped."
```

**The `stop_speaking` tool** sends a sentinel value (`__STOP__`) through the pipe. The pipe listener in the TTS app recognizes this and calls `audio_stop()` + drains the queue — identical to pressing Ctrl+Win+X.

**MCP server transport:** stdio (standard for Claude Desktop MCP servers)

### Part C: Claude Desktop Configuration

**Document in `mcp_tts_server/README.md`** the exact JSON to add to Claude Desktop's config file:

Location: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "natural-voice-tts": {
      "command": "python",
      "args": ["C:\\Users\\paulp\\Documents\\Claude_Projects\\Natural_Voice_TTS\\mcp_tts_server\\server.py"],
      "env": {}
    }
  }
}
```

**Also document** the system prompt addition Paul can use to enable the toggle behavior:

> When I say "speak your responses" or "read aloud", call the `speak` tool with your full response text after each reply. When I say "stop speaking" or "be quiet", stop calling the speak tool. When speaking, send your response as normal text first, then call speak with the same content.

---

## Files to Read Before Writing

1. `_team-lead-brief.md` — Phases 1-4 spec (understand the full architecture)
2. `_team-lead-instructions.md` — code style, patterns, testing approach
3. `src/app.py` — the system tray app (you're modifying this)
4. `src/hotkeys.py` — understand the existing `_on_read()` / `_on_stop()` callbacks
5. `src/audio_player.py` — understand `stop()` and `reset()` functions
6. `src/tts_engine.py` — understand synthesis pipeline (you won't modify this)
7. `_context/kokoro-integration-notes.md` — Kokoro-specific details

---

## Build Order

1. `src/pipe_listener.py` — CREATE — named pipe listener module
2. `src/app.py` — MODIFY — integrate pipe listener startup/shutdown
3. Test pipe listener standalone (write a small test script that sends text to the pipe)
4. `mcp_tts_server/server.py` — CREATE — MCP server with speak/stop tools
5. `mcp_tts_server/requirements.txt` — CREATE — MCP SDK dependency
6. `mcp_tts_server/README.md` — CREATE — Claude Desktop setup instructions
7. `requirements.txt` — MODIFY — add `pywin32>=306`
8. Test end-to-end: start TTS app, start MCP server manually, send test text

---

## Acceptance Criteria

- [ ] Named pipe `\\.\pipe\NaturalVoiceTTS` is created when the TTS tray app starts
- [ ] Text sent to the pipe is spoken aloud using the currently selected voice and speed
- [ ] The `__STOP__` sentinel stops playback immediately (same as Ctrl+Win+X)
- [ ] Existing hotkeys (Ctrl+Win+T/X/Z) continue to work alongside pipe input
- [ ] Pipe listener handles client disconnect/reconnect gracefully (no crash, no orphan handles)
- [ ] Pipe listener shuts down cleanly on app quit
- [ ] MCP server starts via `python server.py` and responds to MCP tool calls over stdio
- [ ] `speak` tool sends text to the pipe and returns confirmation
- [ ] `stop_speaking` tool stops current playback
- [ ] MCP server handles "TTS app not running" gracefully (clear error message, no crash)
- [ ] README documents exact Claude Desktop config JSON and system prompt text
- [ ] All new code follows existing code style (type hints, logging, docstrings)

---

## Design Constraints

1. **No duplicate model loading**: The MCP server must NOT import kokoro or torch. It is a pure text relay.
2. **Existing behavior unchanged**: All current hotkey, tray menu, and audio functionality must work exactly as before.
3. **Fail gracefully**: If the TTS app isn't running, the MCP server returns a clear error — no hang, no crash.
4. **No network**: The named pipe is local IPC only. Nothing leaves the machine.
5. **Minimal dependencies in MCP server**: Only `mcp` SDK. No torch, no kokoro, no pywin32 beyond what's needed for pipe client.

---

## What You Are NOT Building

- No modification to the Kokoro engine or synthesis pipeline
- No new voices or audio processing
- No web server or HTTP API
- No clipboard monitoring mode
- No changes to Phase 4 packaging (installer/PyInstaller) — that's separate
- No system prompt file creation — Paul manages that himself
- No auto-detection of Claude Desktop — manual config only

---

## Known Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `pywin32` not installed | Clear error message on import; add to requirements.txt; document in README |
| Named pipe permissions on Windows 10 Home | Default pipe security allows same-user access — sufficient for local MCP server |
| MCP SDK version compatibility | Pin to `mcp>=1.0`; use the stable `@server.tool()` decorator pattern |
| Pipe handle leak on ungraceful shutdown | Use try/finally with `win32file.CloseHandle()`; overlapped I/O with timeouts |
| Large Claude responses exceeding buffer | 64KB buffer handles ~32,000 characters — far beyond typical responses. For longer, chunk the text. |
| Claude Desktop MCP config format changes | Document the config format as of May 2026; link to Anthropic's MCP docs |

---

## Testing Notes

You are in a sandbox and cannot run Windows-specific code (`win32pipe`, `pystray`, etc.). Write the code, review it carefully, and provide a test script (`test_pipe.py`) that Paul can run on his machine to verify the pipe communication works independently of the MCP server.

**Test script should:**
1. Connect to `\\.\pipe\NaturalVoiceTTS`
2. Send a test sentence ("Hello from the pipe test script.")
3. Read the OK response
4. Send the `__STOP__` sentinel
5. Print results

This lets Paul verify Part A works before moving to Part B.
