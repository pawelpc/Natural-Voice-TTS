# Closing Report: Dropped Sentences Bug Fix

**Date:** 2026-07-01
**Owner:** Paul | **Model:** Opus 4.8
**Task:** Diagnose and fix silently dropped sentences in the agent → MCP → pipe → TTS path.

---

## 1. Diagnosed Root Cause

**Confirmed by code analysis + simulation: a short-read bug in the named-pipe payload read (hypothesis D1).**

The failing path is unique in one respect — it is the only path that reassembles the
text from bytes off a Windows byte-mode named pipe. In
[`src/pipe_listener.py`](src/pipe_listener.py) the payload was read with a **single**
`win32file.ReadFile(pipe, length)` call:

```python
hr, data = win32file.ReadFile(pipe, length)   # OLD — no accumulation
text = data.decode('utf-8')
```

Windows pipes created with `PIPE_TYPE_BYTE | PIPE_READMODE_BYTE` (see the
`CreateNamedPipe` call, `pipe_listener.py:57`) do **not** guarantee that one
`ReadFile` returns all requested bytes, even though the client
([`mcp_tts_server/server.py`](mcp_tts_server/server.py) `_send_to_pipe`) writes the
header + payload in a single `WriteFile`. `ReadFile` on a byte-mode pipe returns as
soon as *any* data is available. For longer agent responses the payload arrives in
fragments, so a single read returns a **truncated prefix**. Two failure modes, both
matching Paul's report:

1. **Tail truncation** — `data` is a prefix of the message; the trailing sentences
   are simply gone. No error, no log. Exactly "complete sentences silently missing."
2. **Mid-UTF-8 cut** — if the truncation lands inside a multi-byte sequence (very
   common with the em dashes and curly quotes the agent uses), `data.decode('utf-8')`
   raises `UnicodeDecodeError`. The old broad `except Exception` swallowed it and
   `break`'d — dropping the **entire** message.

Why the hotkey path never showed this: it never touches the pipe. Selected text goes
straight into `_text_queue` in-process (`app.py:_on_read`), so there is no byte
reassembly to get wrong. The downstream synthesis code is shared and is *not* the
cause — which is consistent with Paul's observation that manual re-reads work fine.

I could not run the live pipe from the sandbox, but I reproduced the failure mode
deterministically with a fake `ReadFile` that returns ≤5 bytes per call: the old
single-read returns 5 of 102 bytes; the new `_read_exactly` returns all 102 and a
mid-stream EOF raises a clean `IOError`.

### On D2 (synthesis exceptions)
This is a real observability gap but is **not** the primary cause here (the hotkey
path shares this code and doesn't drop). It was made worse by a genuinely *silent*
sub-case: when `tts_engine.synthesize` returned **no chunks without raising**,
`_synthesize_sentence` returned `None` and the worker `continue`d with **no log at
all**. Fixed regardless (see below).

---

## 2. What Changed and Why

### `src/pipe_listener.py` — D1 (primary) + D3 + diagnostics
- **Added `_read_exactly(pipe, n, win32file)`** — accumulates chunks in a loop until
  exactly `n` bytes are read; raises `IOError` on premature EOF. This is the standard
  robust framing pattern for byte-mode pipes.
- **Applied it to both reads** — the 4-byte length header *and* the N-byte payload.
  (The header could short-read too, though less likely; both are now correct.)
- **Diagnostic logging (INFO):** `"Pipe payload: header=%d bytes, received=%d bytes"`
  and `"Received message: %d chars decoded"`. With the fix these always agree; logging
  both is the evidence that the complete payload now arrives. Head/tail of long
  messages logged at DEBUG.
- **UTF-8 decode is now explicitly caught** and reported (was previously indistinct
  from a disconnect).
- **D3 — oversized/invalid messages now signal the client.** Instead of silently
  `break`ing, the listener writes a 2-byte `b'ER'` response for a message that exceeds
  `BUFFER_SIZE` (64 KB) or fails UTF-8 decoding, then disconnects.
- **Added an `except IOError` arm** so an incomplete payload disconnects cleanly with a
  WARNING rather than falling through to the generic handler.

### `src/app.py` — D2 (secondary) + worker diagnostics
- `_synthesize_sentence` now logs a **WARNING with the sentence text** when the engine
  returns no audio without raising (the previously silent case). The existing
  exception log was kept.
- `_worker` counts `skipped` sentences, logs each skip at **WARNING** with index and
  text, and shows **one tray notification** at the end of a read if anything was
  skipped (`"N sentence(s) could not be spoken and were skipped."`) — one notification
  per read, not per sentence, to avoid spam.
- Added DEBUG head/tail logging of the received text so a dropped tail is visible when
  comparing sent vs. received.

### `mcp_tts_server/server.py` — D3 client side
- `speak()` now interprets the new `b'ER'` response and returns a clear error string to
  the agent (too long / invalid UTF-8, send smaller chunks) instead of an opaque
  "Unexpected response".

---

## 3. What Was NOT Changed and Why

- **The synthesis / `split_sentences` / `tts_engine` code** — shared by both paths and
  not the cause (R3: don't degrade the hotkey path). Untouched.
- **The lookahead pre-synthesis logic in `_worker`** — left as-is to avoid changing the
  working hotkey path. Note: a sentence whose lookahead synthesis returns `None` is
  re-synthesized when it becomes current (minor redundant work); the skip counter still
  counts it correctly. Out of scope for this fix.
- **No agent-side text divergence** (R1) — the fix is entirely in transport/observability.
  One text still goes identically to both the visible and spoken channels.
- **No new modules** (R4) — all changes are in the three existing files.
- **`BUFFER_SIZE` / streaming for >64 KB messages** — kept the 64 KB cap; oversized
  messages are now *reported* rather than dropped. Chunked streaming of huge messages
  would be a larger protocol change and isn't needed for normal responses.

---

## 4. Test Steps for Paul (run on your Windows machine)

> Running from source logs to the **console**. Running the installed/frozen app logs to
> `%APPDATA%\NaturalVoiceTTS\app.log`. For the sharpest diagnostics, temporarily set
> `level=logging.INFO` → `level=logging.DEBUG` in `app.py:main()` (`logging.basicConfig`)
> so head/tail lines appear; INFO alone is enough to confirm the byte counts.

### Test string (copy this exactly — 12 sentences, em dashes + curly quotes)
```
Sentence one is short. Sentence two runs a little longer — with an em dash — to add
bytes. Here is a third sentence with "curly quotes" and an ellipsis… Sentence four asks
a question? Sentence five! Number six keeps the payload growing so the pipe fragments.
Seven, eight, and nine follow in quick succession. Ten is here. Eleven is the
second-to-last. This twelfth and final sentence is the tail that used to disappear.
```

### A. Verify the pipe path (the bug) is fixed
1. Start the TTS tray app.
2. From the agent (voice mode on), send the test string via `speak()`.
3. **Listen:** all twelve sentences should play, including the final "twelfth and
   final sentence" — that tail is what previously vanished.
4. **Check the log** for a line like:
   `Pipe payload: header=NNN bytes, received=NNN bytes` — the two numbers must be
   **equal**. Then `Received message: MMM chars decoded` and, in the worker,
   `Processing text (MMM chars)` and `Reading 12 sentences`. You should see
   `Playing [1/12]` … `Playing [12/12]` with **no** `Skipped sentence` lines.

### B. Control — hotkey path still works (regression check, R3)
1. Highlight the same test string on screen.
2. Press **Ctrl+Win+T**.
3. All twelve sentences should play, identical to before. The worker log should again
   show `Reading 12 sentences` and `Playing [1/12]…[12/12]`. This path does not touch
   the pipe, so it exercises the shared worker changes only.

### C. Verify D2 (skipped-sentence visibility)
- This only triggers if the engine actually fails on a sentence. If during any read a
  sentence can't be synthesized, you'll now get a WARNING in the log
  (`Skipped sentence [i/n] …`) **and** a single tray balloon at the end
  (`"N sentence(s) could not be spoken and were skipped."`). Under normal input you
  should see neither — which is the point: silence now means nothing was dropped.

### D. Verify D3 (oversized message is reported, not silent)
- Have the agent send a message larger than 64 KB via `speak()` (roughly 30–40k+ words).
  Instead of silence, the agent should receive:
  `"Error: The TTS app rejected the text (too long — over 64 KB — or not valid UTF-8)…"`,
  and the app log shows `Message length … exceeds buffer 65536, rejecting`.

### Rollback
All changes are confined to `src/pipe_listener.py`, `src/app.py`, and
`mcp_tts_server/server.py`. `git checkout` those three files to revert.

---

## 5. Remaining Concerns / Unknowns

- **Live confirmation still pending.** Root cause is confirmed by code analysis and a
  short-read simulation, but not yet by a live capture on your machine. Test A step 4
  (equal header/received byte counts across several long sends) is the confirming
  evidence — please glance at it once.
- **Oversized (>64 KB) delivery is best-effort.** Because the client writes header +
  payload in one `WriteFile`, a message far larger than the 64 KB pipe buffer may block
  the client before the server can send `b'ER'`; in that case the client instead sees a
  broken-pipe `OSError`, which `speak()` still surfaces as an error. Either way it is no
  longer silent. True large-message support would need a chunked protocol — not needed
  for normal responses.
- **The diagnostic INFO lines are permanent.** They're low-volume (one pair per message)
  and genuinely useful for future triage. If you find them noisy, drop the
  `"Pipe payload: …"` line to DEBUG.
- **Lookahead double-synthesis** on a failed sentence (noted in §3) is harmless but
  slightly wasteful; worth a small follow-up if synthesis failures ever become common.
