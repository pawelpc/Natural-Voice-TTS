# Team Lead Instructions: Natural Voice TTS — Speaking Flow and Text Handling

Your first line states the model you are running. If it is not Opus 5.5, say so and wait for Paul.

## Startup sequence
Read these in order before doing anything else:
1. `_prosody-brief.md`: scope, rules R1–R8, phases and gates
2. `src/text_processor.py`: current splitter (55 lines)
3. `src/tts_engine.py`: `SPLIT_PATTERN`, `synthesize()`, model loading in `init()`
4. `src/app.py`: `_worker()` / `_synthesize_sentence()` (how chunks are played, and where gaps come from)
5. `_bugfix-closing-report.md`: the July fix you must not regress (R2)
6. The installed `kokoro/pipeline.py` and `misaki/en.py`: what Kokoro already normalizes, so you don't duplicate it

## Standing instructions
- Ask Paul before changing any factual detail or choosing between readings that are each plausible (R6).
  Do not infer causes. Prove them with a test string and its output.
- Work one phase at a time. At each gate: run the check, save its artifact, commit (R8), and post a 3–5 line
  status for Paul. Continue on your own through Phases 0–3 unless a gate fails. **Stop before Phase 4** and
  wait for Paul's listening check, and stop again before Phase 5.
- The repo already has uncommitted changes that are not yours (`install_config.py`, the plugin `SKILL.md`, `build.log`,
  `.claude/settings.local.json`). Stage only the files you changed, by path. Never `git add -A`.
- Paul may be on voice or Remote Control. Keep status messages short and in plain prose.
- Code style: Python 3.11, type hints on signatures, the module's existing `logger`, constants at module top,
  docstrings on public functions. Tests go under `tests/` and run with a single command; record that
  command in the closing report.

## Resume prompt (for a fresh session after a break)
> Read `_prosody-instructions.md` and `_prosody-brief.md`, then `git log --oneline -10` and the latest
> phase status in `_prosody-closing-report.md` (draft). Resume at the first phase whose gate is not passed,
> for Natural_Voice_TTS prosody.

## Closing
Write `_prosody-closing-report.md`: H1–H4 findings with evidence, changes per phase, R1–R8 compliance
(one line each, with the evidence location), measured time to first audio before and after, and open issues.
The manager will re-run the tests and listen to sample WAVs; it will not accept the report on its own word.
