# Bug Report: Dropped Sentences in Agent-Triggered TTS

**Date:** 2026-07-01
**Reported during:** Sonnet 5 secretary-candidate evaluation session (not a dedicated debugging session — this is an intake report for a future planning session)
**Reporter:** Sonnet 5, based on Paul's observation + source review
**Status:** Root cause NOT confirmed. No live test/log was run. This is a grounded hypothesis for a team lead to verify.

## Summary

When Sonnet 5 sends response text to the `speak` MCP tool (agent → MCP server → named pipe → TTS app), Paul observed several complete sentences silently missing from the audio while reading along with the text. When Paul manually highlights the same kind of text and triggers TTS via the hotkey (Ctrl+Win+T, which bypasses the MCP/pipe path entirely), the problem does not appear to occur.

## What Paul Observed

1. While voice mode was on and Sonnet 5 was sending full responses to `speak()`, several complete sentences were audibly skipped, noticed by reading the text on screen while listening.
2. Separately, Paul noted that highlighting the same text after the fact and triggering TTS manually via the OS hotkey does **not** show the same dropped-sentence behavior.
3. Paul does not want the agent to send different text to the spoken and written channels (e.g., a "TTS-safe" sanitized version vs. the real response) as a workaround — he described the mismatch as jarring, comparable to mismatched anime dub/subtitle translations. **Whatever fix is applied, it should not rely on the agent silently diverging the two outputs.**

## Investigation So Far (Sonnet 5, this session)

### Initial hypothesis (now considered less likely)

First guess was that Unicode punctuation Sonnet 5 uses heavily (em dashes, in particular) was throwing an exception inside the Kokoro/espeak-ng phonemizer for a given sentence. In `Natural_Voice_TTS/src/app.py`, `_synthesize_sentence()` (~lines 128–137) wraps synthesis in a try/except; on exception it logs and returns `None`, and the caller in `_worker()` (~lines 97–122) does `continue` — silently skipping that sentence with no user-visible signal. This is a real defect regardless of root cause (see below), but Paul's observation in point 2 above undercuts it as the *primary* explanation: the downstream synthesis code (`split_sentences`, `_synthesize_sentence`, `tts_engine.synthesize`) is identical for both delivery paths, so if punctuation in the text were the cause, the manual-highlight path should fail identically. It doesn't.

### Revised leading hypothesis

The two delivery paths differ upstream of synthesis, and that difference lines up with the symptom:

- **Manual/hotkey path** (works correctly): `hotkeys.grab_selected_text()` → `app._on_read()` → text goes directly into the in-process `_text_queue` (`app.py` ~line 151). No serialization, no IPC.
- **Agent path** (shows the bug): Sonnet 5 → `mcp_tts_server/server.py` `speak()` → `_send_to_pipe()` writes a length-prefixed message over a Windows named pipe → `src/pipe_listener.py` `_handle_client()` reads it and puts it on the same `_text_queue`.

In `pipe_listener.py` `_handle_client()` (~lines 110–147), both the 4-byte length header and the payload are read with a **single** `win32file.ReadFile(pipe, N)` call each, with no loop to accumulate bytes if the OS returns fewer than requested:

```python
hr, header = win32file.ReadFile(pipe, 4)
...
hr, data = win32file.ReadFile(pipe, length)
```

Win32 named pipes in byte mode (`PIPE_TYPE_BYTE`) are not guaranteed to fill a `ReadFile` request in one call just because that many bytes were eventually written — a single call can return a short read. If that happens on the payload read, `data` would silently be a truncated prefix of the actual message (missing the tail — i.e., missing sentences), or, if the cut lands mid-UTF-8-multibyte-sequence, `data.decode('utf-8')` would raise and the whole message would be dropped via the exception handler. Either failure mode is consistent with what Paul described, and neither would occur on the manual path since it never goes through this read loop at all.

This has **not been confirmed** — no logging was added, no reproduction was run, and the live `app.log` (only written in frozen/installed mode, under `%APPDATA%\NaturalVoiceTTS\`) was not inspected, since it lives outside the folders this session has access to.

## Files Relevant to This Investigation

- `Natural_Voice_TTS/mcp_tts_server/server.py` — `_send_to_pipe()` (client-side write, ~lines 28–80)
- `Natural_Voice_TTS/src/pipe_listener.py` — `_handle_client()` (server-side read, ~lines 98–159) — **primary suspect**
- `Natural_Voice_TTS/src/app.py` — `_worker()` (~67–125) and `_synthesize_sentence()` (~128–137) — silent-drop-on-exception is a real secondary defect worth fixing regardless of root cause
- `Natural_Voice_TTS/src/text_processor.py` — `split_sentences()` — regex-based splitter, worth reviewing but not currently believed to be the cause
- `Natural_Voice_TTS/src/hotkeys.py` + `app.py` `_on_read()` — the working, non-piped path; useful as a control for comparison testing

## Suggested Diagnostic Steps for the Team Lead

1. Reproduce with a controlled long text string (known content, easy to verify against by ear/eye): send it once via the `speak` MCP tool, and once via copy/highlight + hotkey. Compare.
2. Add temporary logging in `_handle_client()` of expected `length` vs. actual `len(data)` on every payload read, and log any `UnicodeDecodeError`.
3. If a short-read is confirmed, fix by looping the `ReadFile` calls (for both the 4-byte header and the payload) until the full expected byte count has been accumulated — standard robust framing pattern for byte-mode pipes.
4. Independently of the above: fix the silent drop in `_synthesize_sentence`/`_worker` so a failed sentence is at least logged visibly (tray notification or similar) rather than disappearing with no trace — this is a real observability gap even if it's not the primary cause here.
5. Do **not** design the fix around having the agent send sanitized/alternate text for speech — Paul wants one output sent identically to both the visible text and the spoken channel.

## Workaround Status

Sonnet 5 briefly sent a punctuation-stripped version of responses to `speak()` as a same-session workaround. Paul rejected this approach (jarring mismatch between spoken and written content) and asked for identical text to both channels going forward. That workaround has been reverted for the remainder of this session.
