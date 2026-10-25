# Team Lead Brief: Natural Voice TTS — Speaking Flow and Text Handling

**Project:** Natural_Voice_TTS (`C:\Users\paulp\Documents\Claude_Projects\Natural_Voice_TTS\`)
**Run in:** Claude Code, Opus 5.5 · **Drafted:** 2026-10-17 by the manager · **Approved by Paul:** 2026-10-17

## Goal
Make Kokoro read text as smoothly as Windows 11 Natural Voices or the iPhone voice in the Claude app. Today it
breaks sentences in the wrong places, mangles abbreviations, numbers and symbols, and its rhythm is choppy.
Paul's ear is the final judge.

## What it reads (priority order)
1. Claude responses sent through MCP `speak`: markdown, file paths, version numbers, short code.
2. Highlighted text from any app (web pages, PDFs, email) through the hotkey.
Both paths go through `split_sentences()`, so one fix covers both.

## Suspected causes — UNVERIFIED (manager read the code; nothing was run)
- H1: `text_processor.split_sentences()` splits on any `.!?` followed by whitespace, so "Dr. Smith",
  "e.g. this" and "U.S. Army" each break into separate chunks with sentence-final intonation.
- H2: `tts_engine.SPLIT_PATTERN = r'[.!?\n]+'` is passed to `KPipeline`. It probably splits on every period
  even with no space after it ("3.5", "v1.1.0", "app.py"). It also probably strips the end punctuation that
  Kokoro/misaki use for intonation, which would explain flat sentence endings.
- H3: There's no normalization step before Kokoro, so markdown (`**`, `#`, backticks, bullets), paths, URLs,
  units, times and dates go through raw or are left to misaki.
- H4: Nothing controls pause length. Sentence and paragraph gaps are whatever the audio happens to contain.
Confirm or reject each one with evidence (a test string, its chunks or phonemes, a rendered WAV)
before fixing.

## Scope — decisions Paul made 2026-10-17
- **All failure types are in scope.** Rhythm and choppiness rank first, then abbreviations, numbers and versions,
  markdown and symbols, paths and URLs, units, times and dates, and lists.
- **Code and symbols:** read short paths, URLs and identifiers naturally ("src slash app dot py").
  Replace fenced code blocks with a short spoken note (for example "code block skipped"), not the contents.
- **Pauses:** use deliberate silence lengths (short for a comma, medium for a sentence end, long for a
  paragraph or heading). Fixed values as constants; no Settings UI this round.
- **Fully local.** No cloud and no LLM rewriting. Light local dependencies are OK if justified
  (for example a text-normalization library). A dependency needing HuggingFace downloads at runtime is not OK.
- **No reference recordings.** This machine is Windows 10, so Win 11 voices are unavailable. Paul compares by ear.

## Rules (numbered for auditing)
- R1: Do not change the Kokoro model, the default voice (`af_heart`) or the default speed.
- R2: Leave `pipe_listener.py` and `mcp_tts_server/` alone unless a fix needs it. If one does, stop and
  ask Paul first. (These hold the July dropped-sentence fix, `bba2200`.)
- R3: Time to first audio must not get worse. Measure it before and after on the same passage; a regression
  of more than 10% fails.
- R4: No sentence may be dropped. The words spoken must match the normalized input text (testable from the
  chunk list).
- R5: The text on screen is never changed, only what is spoken (Paul's rule: don't let the screen and the
  speech say different things beyond pronunciation). Normalization changes pronunciation, never meaning.
- R6: Ask Paul before choosing between two plausible readings (for example "Dr." as Doctor or Drive). Do not guess.
- R7: Work from source. No installer rebuild and no GitHub release until Paul passes the listening check (Phase 4).
- R8: Commit to the project's git repo at each phase gate, using clear messages.

## Phases and gates
- **Phase 0 — Environment and baseline.** Confirm the source run works on this machine (venv, CUDA,
  where the model is loaded from; the bundle in `dist/` holds the model). Build `tests/passages/`, about 30 hard
  passages: about half taken from real Claude responses, the rest synthetic, one tagged category each. Render a
  baseline WAV per passage. Record time to first audio. Confirm or reject H1–H4.
  **Gate:** source synthesis runs; 30 baseline WAVs exist; H1–H4 each marked confirmed or rejected, with evidence.
  If the source run can't load the model locally, **stop and report**.
- **Phase 1 — Splitting.** Replace the splitting so sentence ends are found correctly (abbreviations, decimals,
  versions, initials, ellipses, quotes) and Kokoro keeps the end punctuation.
  **Gate:** unit tests pass on every splitting case in the passage set; zero wrong splits.
- **Phase 2 — Normalization.** Add a normalization pass (markdown, symbols, paths, URLs, units, numbers,
  times and dates, lists, code blocks) as its own module with unit tests.
  **Gate:** each passage's normalized text matches an expected-output file; R4 and R5 hold.
- **Phase 3 — Pauses.** Add pause insertion by boundary type, as named constants.
  **Gate:** gap lengths measured in the rendered WAVs are within ±50 ms of their targets.
- **Phase 4 — Paul's listening check.** Render "after" WAVs for the same passages. Give Paul a simple A/B list
  (an HTML page or folder of pairs, labeled by category). Paul marks each pair better, same or worse.
  **Gate:** Paul passes it. Fix anything marked "worse" before going further.
- **Phase 5 (only after the Phase 4 pass)** — Rebuild the installer, bump to v1.2.0 and update the README.
  Give Paul the exact commands for the release; he publishes it.

## Deliverables
Code changes with tests · `tests/passages/` with expected outputs · before/after WAVs and the A/B page ·
`_prosody-closing-report.md` (findings on H1–H4, what changed, rules compliance R1–R8, open issues).

## Known risks and preemptive guidance (from manager memory)
- Test assumptions first (CF-2). The model-loading path in source mode is the first thing to check, not the last.
- In the last TTS fix, a closing report was accepted as evidence and this was later regretted. Every gate needs
  an artifact (test output, WAV, measured number) the manager can re-check.
- HuggingFace downloads are blocked in Claude environments. Don't plan on fetching models or voices.
- Commands given to Paul target PowerShell 7 (`pwsh`).
- If a gate forces an extreme parameter (for example pause limits that can't be met), push back. Don't quietly work around it.
