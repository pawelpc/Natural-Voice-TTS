# Natural Voice TTS — MCP Server

Lets Claude Desktop speak responses aloud using the Natural Voice TTS tray app.

## How it works

```
Claude Desktop  ──MCP stdio──▶  server.py  ──named pipe──▶  TTS tray app  ──▶  audio
```

The MCP server is a ~100-line text relay. It has no model loading, no torch, and starts in under a second. All synthesis runs inside the already-loaded Kokoro engine in the tray app, so there is no duplicate model in RAM and all existing hotkeys keep working.

---

## Prerequisites

1. **Natural Voice TTS tray app must be running.** Start it before opening Claude Desktop. The pipe `\\.\pipe\NaturalVoiceTTS` only exists while the tray app is active.
2. **Python 3.11+** on your PATH (the same Python you use for the main project works fine).
3. **pywin32** — comes with the main project; if you need it standalone: `pip install pywin32>=306`.

---

## Install

```
cd mcp_tts_server
pip install -r requirements.txt
```

---

## Claude Desktop configuration

Open (or create) `%APPDATA%\Claude\claude_desktop_config.json` and add the `natural-voice-tts` entry inside `mcpServers`:

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

Restart Claude Desktop after saving. If it was already running, quit and relaunch — it loads MCP servers at startup.

**Verify it loaded:** Open Claude Desktop settings → Developer → MCP Servers. You should see `natural-voice-tts` listed as connected.

---

## System prompt (optional but recommended)

Add this to your Claude Desktop system prompt to enable a conversational toggle:

> When I say "speak your responses", "read aloud", or "voice on", call the `speak` tool with your full response text after each reply. When I say "stop speaking", "be quiet", or "voice off", stop calling the speak tool. When speaking is active, send your response as normal text first, then immediately call `speak` with the same content.

Without this system prompt you can still trigger the tools manually by asking Claude to use them explicitly.

---

## Tools exposed

| Tool | Description |
|------|-------------|
| `speak(text)` | Enqueues text for synthesis and playback |
| `stop_speaking()` | Stops current playback immediately (same as Ctrl+Win+X) |

---

## End-to-end test

Follow these steps in order to verify everything works:

**1. Start the TTS tray app**

```
python src/app.py
```

Wait for the tray icon to appear and the log to show `Ready!`.

**2. Test the named pipe directly**

```
python test_pipe.py "Hello from the pipe test script."
```

Expected output:
```
Connecting to \\.\pipe\NaturalVoiceTTS...
Sending text (38 chars): 'Hello from the pipe test script.'
Success! Server responded: 'OK'
Text enqueued — listen for audio.
```

You should hear the sentence spoken aloud. If not, check that the tray app is running and check its console log.

**3. Test the stop sentinel**

```
python test_pipe.py --stop
```

Any currently playing audio should stop immediately.

**4. Start the MCP server manually to check for import errors**

```
python mcp_tts_server/server.py
```

It will block waiting for MCP messages on stdio — that is normal. Press Ctrl+C to exit. A clean start (no tracebacks) means all dependencies are installed correctly.

**5. Configure Claude Desktop and restart it**

Add the JSON block from the [Claude Desktop configuration](#claude-desktop-configuration) section above, then quit and relaunch Claude Desktop.

**6. Tell Claude to speak**

In Claude Desktop, type:

> "Speak your responses from now on."

Then send a follow-up message. Claude should reply in text and simultaneously call the `speak` tool, and you will hear audio through the tray app.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `Error: Named pipe not found` | TTS tray app is not running | Start `src/app.py` first |
| MCP server not listed in Claude Desktop | Config JSON has a path typo | Double-check the path in `claude_desktop_config.json` |
| `ModuleNotFoundError: mcp` | Dependencies not installed | Run `pip install -r mcp_tts_server/requirements.txt` |
| Audio plays but cuts off mid-sentence | Another speak call arrived | Normal — each `speak` call replaces the queue |
| Ctrl+Win+X doesn't stop pipe audio | Already fixed by design | Both hotkeys and pipe feed `_text_queue`; stop works on both |
