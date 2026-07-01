# Team Lead Instructions: Dropped Sentences Bug Fix

## Startup Sequence

Read these files in this order before doing anything else:

1. `_bugfix-brief.md` — the task brief (scope, hypotheses, rules, acceptance criteria)
2. `_bug-report-dropped-sentences-2026-07-01.md` — original bug report with full context
3. `src/pipe_listener.py` — primary suspect file (~188 lines)
4. `src/app.py` — `_worker()` and `_synthesize_sentence()` (the silent-drop defect)
5. `mcp_tts_server/server.py` — the write side of the pipe protocol
6. `src/text_processor.py` — `split_sentences()` regex, for reference

## Workflow

This is a **diagnose-then-fix** task, not a "just apply the patch" task. The root cause is unconfirmed.

### Phase 1: Instrument

Add diagnostic logging to `_handle_client()` and `_worker()` per the brief's diagnostic steps. Write the code changes. Document how Paul should trigger them (send a known test string via speak(), check the log).

### Phase 2: Analyze

Based on what the instrumentation would reveal, assess which hypothesis is correct. Write your assessment in session notes. If your analysis reveals a different root cause than the two hypotheses in the brief, document it.

### Phase 3: Fix

Apply fixes for D1, D2, and D3 as described in the brief. D1's fix (`_read_exactly` accumulation loop) should be applied regardless of root cause — it's a real code defect.

### Phase 4: Test documentation

Write clear test steps for Paul to verify the fix on his machine. Include:
- Exact test string to send via speak()
- What to check in the log
- How to verify hotkey path still works
- How to verify the fix resolved the original symptom

## Code Style

Match the existing codebase:
- Python 3.11, type hints on function signatures
- `logging` module (not print) — use the existing `logger` in each file
- Constants at module top
- Docstrings on public functions

## Physical-World Constraints

You are in a sandbox. You **cannot** run the TTS app, the MCP server, or interact with the named pipe. Your deliverables are code changes and test documentation. Paul will run everything on his Windows machine.

The installed app's log file is at `%APPDATA%\NaturalVoiceTTS\app.log` — only written in frozen (PyInstaller) mode. When running from source, logging goes to the console.

## Session Reporting

When done, write a `_bugfix-closing-report.md` in this folder covering:
- What was the diagnosed root cause (or your best assessment)
- What code was changed and why
- What was NOT changed and why
- Test steps for Paul
- Any remaining concerns or unknowns
