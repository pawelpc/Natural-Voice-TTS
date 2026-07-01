# Team Lead Brief: Dropped Sentences Bug Fix

**Task**: Diagnose and fix dropped sentences in the agent→MCP→pipe→TTS pipeline.
**Owner**: Paul | **Model**: Opus 4.8 | **Environment**: Cowork (Claude Code also acceptable)
**Bug report**: `_bug-report-dropped-sentences-2026-07-01.md` in this folder — read it fully before starting.

---

## Symptom

When the Claude agent sends text via `speak()` MCP tool (agent → named pipe → TTS app), complete sentences are silently missing from the audio output. When Paul manually highlights the same text and triggers TTS via the hotkey (Ctrl+Win+T), no sentences are dropped. The synthesis code (`split_sentences`, `_synthesize_sentence`, `tts_engine.synthesize`) is shared by both paths — the divergence is upstream, in how text reaches the queue.

## Two Delivery Paths (the key difference)

- **Hotkey path (works)**: `hotkeys.grab_selected_text()` → `app._on_read()` → `_text_queue.put(text)`. No serialization, no IPC.
- **Pipe path (drops sentences)**: MCP `speak()` → `server.py:_send_to_pipe()` writes length-prefixed UTF-8 over a named pipe → `pipe_listener.py:_handle_client()` reads it → `_text_queue.put(text)`. The pipe read is the only code unique to the failing path.

## What to Fix

### D1 — Primary: diagnose and fix the pipe-path sentence loss

Leading hypothesis is a short-read bug in `pipe_listener.py:_handle_client()` (~lines 112-134). Both the 4-byte header and the N-byte payload are read with a single `ReadFile` call each, with no accumulation loop. If `ReadFile` returns fewer bytes than requested, the payload is silently truncated (losing tail sentences) or, if the cut lands mid-UTF-8-sequence, `decode('utf-8')` raises and the entire message is dropped by the exception handler.

**This hypothesis has NOT been confirmed.** Your first job is to add diagnostic logging and reproduce, not jump straight to patching. The root cause could be something else entirely. Follow the diagnostic steps below.

### D2 — Secondary: fix silent sentence drops in synthesis

`app.py:_synthesize_sentence()` (~line 128-137) catches all exceptions and returns `None`. The caller in `_worker()` does `continue` — silently skipping that sentence. This is a real observability gap regardless of whether it's the primary cause. Fix: at minimum, log at WARNING level with the failed sentence text; ideally, show a tray notification so Paul knows something was skipped.

### D3 — Secondary: oversized message rejection is silent to user

`pipe_listener.py` line 124-125 drops messages exceeding `BUFFER_SIZE` (64KB) with a log warning but no signal to the user or the MCP client. If an agent response is very long, the entire message vanishes. Fix: return an error indicator to the MCP server instead of just dropping and breaking.

## Diagnostic Steps (do these BEFORE writing fixes)

1. **Add temporary logging in `_handle_client()`**: Log `length` (from header) vs `len(data)` (actual bytes received) on every payload read. Also log any `UnicodeDecodeError` explicitly.
2. **Add temporary logging in `_worker()`**: Log the full text received from the queue (or at least its length and first/last 100 chars) so you can compare what was sent vs what arrived.
3. **Reproduce with controlled text**: Compose a multi-paragraph test string (~20 sentences including em dashes, curly quotes, and other Unicode). Send it via `speak()` MCP tool. Compare the logged received text against the original. Send the same text via hotkey path as a control.
4. **Check `app.log`**: If running in frozen/installed mode, the log is at `%APPDATA%\NaturalVoiceTTS\app.log`. Look for existing `Failed to synthesize` entries that would indicate D2.
5. **Only after diagnosis**: Apply the fix matching the confirmed root cause.

## Fix Approach for D1 (if short-read confirmed)

Wrap both `ReadFile` calls in an accumulation loop:
```python
def _read_exactly(pipe, n, win32file):
    """Read exactly n bytes from pipe, looping on short reads."""
    chunks = []
    remaining = n
    while remaining > 0:
        hr, data = win32file.ReadFile(pipe, remaining)
        if not data:
            raise IOError("Pipe closed during read")
        chunks.append(data)
        remaining -= len(data)
    return b''.join(chunks)
```
Apply to both the 4-byte header read and the payload read. This is the standard robust framing pattern for byte-mode pipes.

## Rules

- **R1**: Do NOT have the agent send different text to speech vs. chat. Paul explicitly rejected this. One text, both channels.
- **R2**: Diagnose first, fix second. Log evidence before changing behavior.
- **R3**: The fix must not degrade the hotkey path. Both paths share `_worker()` and downstream — any changes there affect both.
- **R4**: All code changes must be in existing files. No new modules needed for this fix.
- **R5**: Physical-world constraint — you cannot run the TTS app or the MCP server from the sandbox. Write the code changes, document test steps for Paul, and include instructions for how Paul should verify.

## Acceptance Criteria

- [ ] Root cause identified with logged evidence (short read, synthesis failure, or other)
- [ ] Primary fix applied — pipe-path speech no longer drops sentences
- [ ] `_read_exactly` or equivalent accumulation loop in `_handle_client` (fix D1 regardless — it's a real defect even if not the primary cause today)
- [ ] `_synthesize_sentence` failures are logged at WARNING with sentence text (fix D2)
- [ ] Oversized message rejection returns an error to the MCP client (fix D3)
- [ ] No divergence between spoken and written text channels
- [ ] Test steps documented for Paul to run on his machine
- [ ] Hotkey path still works correctly (regression check)

## Files to Modify

| File | Changes |
|------|---------|
| `src/pipe_listener.py` | Add `_read_exactly()`, use it for header+payload reads, improve error signaling for oversized messages |
| `src/app.py` | Improve logging in `_synthesize_sentence` (WARNING + sentence text), consider tray notification on skip |
| `mcp_tts_server/server.py` | No changes expected unless D3 fix requires returning error strings |
