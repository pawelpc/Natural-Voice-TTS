# Closing Report: Natural Voice TTS — Speaking Flow and Text Handling

**Team lead:** Opus 5.5 (`claude-opus-5-5`) · **Work:** 2026-10-17 to 2026-10-22 · **For:** the manager
**Brief:** `_prosody-brief.md`, `_prosody-instructions.md` · **Last commit:** see `git log` on `master` (not pushed)

## Summary for the manager

- **Outcome:** all five phases done. Paul's listening check (Phase 4): **32 better, 1 same, 0 worse; overall
  pass** (`tests/phase4/ratings.txt`, his own words). **v1.2.0 is published** on GitHub by Paul: tag `v1.2.0` at
  `b57abfc`. The asset `NaturalVoiceTTS_Setup_1.2.0.exe` (1,885,275,055 bytes) is the build I made and launch-tested.
- **Hypotheses:** H1, H3, H4 confirmed; H2 confirmed for splitting and stripping, but its claim of flat
  endings was **not** shown by measurement (§Phase 0). The biggest cause of choppiness was not a hypothesis
  in the brief: every boundary got about 0.8 s of Kokoro padding, plus a synthesis wait before each sentence.
- **After the release, on `master` but not in any installer:** the pronunciation list (Paul's note #8) and
  spoken emphasis, on by default (note #13), from two follow-up sessions. I reviewed them and fixed one regression
  in them (§After the release). They are the content of the **next** release.
- **The next session builds and pushes that release.** Follow the handoff checklist below. Two traps
  nearly broke the 1.2.0 build (§Phase 5).

### Measured results

| What | Before (v1.1.0 code) | After | Evidence |
|---|---|---|---|
| Time to first audio, passage 17 (July string) | 0.533 s | **0.130 s** (−76%) | `tests/phase4/render/r3.json` |
| Time to first audio, passage 16 (real `speak` call) | 0.680 s | **0.270 s** (−60%) | same |
| Time to first audio, passage 01 (markdown) | 0.516 s | **0.118 s** (−77%) | same |
| Same with emphasis on (current master vs released 1.2.0) | — | worst **+6.4%** (emphasized first chunk) | `tests/emphasis/r3_emphasis_on.json` |
| Pauses on target (±50 ms) | not controlled (~0.8 s at every boundary) | **539/539** | `tests/phase4/render/pauses.json` |
| Wrong sentence splits, 33 passages | 6 of 7 probe cases wrong | **0** (hand-reviewed) | `tests/passages/expected_splits.json` |
| Words silently dropped (Kokoro level) | at least 3 ("zero", "12", "Don't") | **0** | `tests/phase4/render/meta`, `test_every_word_gets_phonemes` |
| Automated tests | none | **347 pass** | `python -m pytest tests -q` |

All A/B timings use ABBA order with 30 samples a side and a bootstrap 95% CI (`tests/compare_ttfa.py`).

### How to re-check (manager)

- Tests (about 15 s; a few emphasis tests need the local model and skip without it): `python -m pytest tests -q`
- Re-render and re-measure the pauses (GPU, about 12 min): `python tests/render_passages.py --out <dir>`,
  then `python tests/measure_pauses.py --render <dir> --out <dir>/pauses.json`
- R3 (about 30 min; needs a checkout of the "before" commit, e.g. `git worktree add <dir> ce7177d`):
  `python tests/compare_ttfa.py --before <dir> --after . --rounds 6 --out <file>`
- **Listen:** the before/after WAVs (33 each) are local and gitignored: `tests/baseline/wav` (v1.1.0) and
  `tests/phase4/render/wav` (final = 1.2.0). The A/B page: https://claude.ai/artifact/YavTFrd8ndpBu7MPSeKkTZ
  (private to Paul), or locally `tests/phase4/listening.html` (MP3s in `tests/phase4/audio`).
  Emphasis comparisons: `tests/emphasis/listen.html`. Its WAVs exist only in the side worktree
  `.claude/worktrees/angry-engelbart-71f331/tests/emphasis/`; regenerate them with `tests/probe_emphasis.py` if
  that worktree is gone.

## Handoff: building and pushing the next release

Master is **ahead of `origin/master`** by the follow-up work (`b18f35a` onward). The next session should:

1. **Pick the version** with Paul. I suggest **1.3.0**, since both changes are new features. Bump it in
   `installer/setup.iss` (`MyAppVersion`), `src/dialogs.py` (`APP_VERSION`), `build.bat` (title line and the
   "Installer:" echo), `version_info.txt` (four places, `x.y.0.0`), and the README download link and filename.
2. **README and release notes:** turn the README's "Coming in the next release" section into "What's new in
   1.3.0" and remove the two "*Not in the 1.2.0 installer…*" lines. Write `release_notes/1.3.0.md` in the
   style of `release_notes/1.2.0.md`.
3. **Model (trap 1):** PyInstaller deletes `dist\NaturalVoiceTTS\`, including `kokoro_model\`, the folder
   source mode loads from. `build.bat` then copies the model back from the HuggingFace cache. The cache now
   holds a complete copy in `%USERPROFILE%\.cache\huggingface\hub\models--hexgrad--Kokoro-82M\snapshots\local-from-dist\`
   (config, `kokoro-v1_0.pth`, 27 voices). **Don't delete it.** Check that the build log says
   `Found model at: …local-from-dist`.
4. **MCP files (trap 2):** `build.bat` copies the working-tree `mcp_tts_server\` into the installer. Run
   `git status -- mcp_tts_server` first; it is clean today. If Paul has uncommitted edits there, ask him
   whether they ship. For 1.2.0 he said no.
5. **Run the build by full path** from PowerShell (a bare `cmd /c build.bat` failed with "not recognized"):
   `cmd /c "C:\Users\paulp\Documents\Claude_Projects\Natural_Voice_TTS\build.bat"`. It takes about 30 min.
   Expect about 48 harmless PyInstaller "Hidden import not found" errors (`munch`,
   `torch.distributed._shard…`); 1.2.0 ran fine with them.
6. **Check the build:** the installer exists and is under 2 GiB;
   `dist\NaturalVoiceTTS\_internal\assets\pronunciations.json` exists (the frozen app reads it there); the
   model in `dist` matches the cache copy; and the bundled `mcp_server` files equal HEAD.
7. **Launch test:** Paul must quit the installed tray app first (single-instance lock). Start
   `dist\NaturalVoiceTTS\NaturalVoiceTTS.exe`, wait for `Ready!` in `%APPDATA%\NaturalVoiceTTS\app.log`, then
   run `python test_pipe.py "**Important:** Cowork is NOT down."`. The log should show
   `Pronunciation list: 1 entries`, one `Playing [1/1]` line and `Finished reading` with no `Skipped`. Stop the
   test instance afterwards.
8. **Push and release** (with Paul's go-ahead; he published 1.2.0 himself): `git push origin master`,
   `git tag -a v1.3.0 -m "Natural Voice TTS 1.3.0"`, `git push origin v1.3.0`, then
   `gh release create v1.3.0 "dist\NaturalVoiceTTS_Setup_1.3.0.exe" --title "Natural Voice TTS 1.3.0" --notes-file "release_notes\1.3.0.md"`.
9. Optional cleanup after the push: the merged branches `claude/jovial-hypatia-0d6e6d` and
   `claude/angry-engelbart-71f331`, and their worktrees (save any WAVs you want first).

## Phase status

| Phase | Gate | Status | Evidence |
|---|---|---|---|
| 0 Environment and baseline | source synthesis runs; 30 baseline WAVs; H1–H4 decided | **Passed** | §Phase 0 below |
| 1 Splitting | unit tests, zero wrong splits | **Passed** (R3 later found failing on passage 16) | §Phase 1 below |
| 2 Normalization | expected-output files match; R4, R5 hold | **Passed**; R3 open | §Phase 2 below |
| 3 Pauses | measured gaps within ±50 ms of targets | **Passed**: 516/516; R3 passes | §Phase 3 below |
| 4 Paul's listening check | Paul passes it | **Passed**: 32 better, 1 same, 0 worse | §Phase 4 below |
| 5 Release | only after Phase 4 | **Done**: v1.2.0 built and launch-tested; published by Paul | §Phase 5 below |
| After | review of the follow-up sessions | **Done**; one regression fixed | §After the release |

The sections below are the working record, phase by phase, written as the work happened. Where a later
finding corrected an earlier claim, the correction is marked in place (Phase 1 R3).

---

## Phase 0 — Environment and baseline

### Environment (checked, not assumed)
- **Python 3.10.11** (Microsoft Store build). No venv: kokoro 0.9.4, misaki 0.9.4, torch 2.6.0+cu124,
  spaCy 3.8 with `en_core_web_sm`, num2words, pytest 7.2 are installed in the user site-packages.
  The brief's style rule says Python 3.11; the machine runs 3.10, so new code avoids 3.11-only features.
- **CUDA works:** GTX 1650, torch reports `cuda=True`; GPU benchmark 0.15 s.
- **espeak-ng** is at `C:\Program Files\eSpeak NG` (used by misaki for unknown words).
- **Model loading, source mode: was broken.** `tts_engine.init()` in source mode called
  `KPipeline(lang_code='a')`, which asks Hugging Face for `config.json`. The HF cache has no Kokoro
  entry and `HF_HUB_OFFLINE=1` is forced, so it raised `LocalEntryNotFoundError`.
  The model exists locally in `dist/NaturalVoiceTTS/kokoro_model/` (config, `kokoro-v1_0.pth` 327 MB,
  27 voices). **Fix:** `_get_bundled_model_dir()` (`src/tts_engine.py`) now also finds a local model
  folder in source mode (`NVTTS_MODEL_DIR`, else `dist/NaturalVoiceTTS/kokoro_model`) and goes through
  the same load path the frozen app uses. No network. Same model file, voice and speed (R1).
  Verified: init 4.6 s, then synthesis on `cuda`.

### Passage set — `tests/passages/`
33 passages, one category each, provenance in `manifest.json`:
- **17 real**: 15 verbatim excerpts of Claude's own messages in this project's earlier session
  (transcript `ed778b0c`; markdown headings, tables, fenced code, paths, versions, times, sizes),
  1 actual MCP `speak` input, and the July regression string from `_bugfix-closing-report.md`.
  Personal or off-topic messages (vault/Blue Van, the Napoleon/lyrics message, a video transcript) were
  left out because the repo is on GitHub.
- **16 synthetic**: abbreviations, initials, decimals/versions, ellipses/quotes, paths/URLs,
  identifiers, units, times/dates, mixed numbers, markdown, lists, code blocks, symbols, long
  sentences, hard-wrapped PDF/email text.
- Categories: rhythm 4, splitting 5, abbreviations 3, numbers_versions 3, markdown 3, paths_urls 3,
  tables 2, code_blocks 2, lists 2, symbols 2, units 2, times_dates 2.

### Baseline render — `tests/baseline/`
- `render_passages.py` speaks each passage exactly as the app does (`split_sentences()` →
  `app._synthesize_sentence()`), recording what Kokoro received.
- **33 WAVs** in `tests/baseline/wav/` (1673.7 s total; gitignored by the existing `*.wav` rule, so
  they're on disk only). Their sha256, chunk lists, Kokoro segments, phonemes and silence measurements
  are committed in `tests/baseline/meta/*.json` and `render_summary.json`.
- Skips: one chunk, `---` (a markdown rule with no words). No sentence with words was skipped.

### Time to first audio (R3 baseline)
`measure_ttfa.py`: runs the app's real `_worker` thread, with `play_audio` replaced by a sleep of the
clip's length. 5 runs each, warm engine. `tests/baseline/ttfa.json`.

| Passage | TTFA median | min–max | Gap between chunks, median (max) |
|---|---|---|---|
| 17 July regression string | **0.485 s** | 0.463–0.586 | 0.428 s (0.490) |
| 16 real `speak` call | **0.642 s** | 0.585–0.647 | 0.121 s (0.731) |
| 01 real markdown response | **0.508 s** | 0.466–0.519 | 0.643 s (0.878) |

Plus the sound device itself (`measure_device.py`, `device_overhead.json`, Baseus Bluetooth headset):
**+0.886 s** on the first play after idle, **+0.111 s** median on each later play.
The R3 comparison will use the same three passages and the same scripts.

### Hypotheses

**H1 — CONFIRMED.** `split_sentences()` breaks after any `.!?` + space.
Evidence (`hypotheses.json` → `H1`): 6 of 7 cases split wrongly:
`'Dr. Smith arrived late.'` → `['Dr.', 'Smith arrived late.']`;
`'Mr. and Mrs. Jones came at 5 p.m. today.'` → `['Mr.', 'and Mrs.', 'Jones came at 5 p.m.', 'today.']`;
`'J. R. R. Tolkien…'` → 4 chunks; `'The U.S. Army…'`, `'e.g. this'`, `'ended... then'` likewise.
`'Version 3.5 is out now.'` stays whole (no space after the dot). Passage 18 (19 words) becomes 11 chunks.

**H2 — CONFIRMED (splitting and stripping); the intonation effect is NOT shown.**
`SPLIT_PATTERN = r'[.!?\n]+'` goes to `re.split()` inside `KPipeline.__call__`, so (`H2`):
- It splits inside tokens. `'Pi is 3.5 or so.'` → `'Pi is 3'` | `'5 or so'` (spoken "three … five",
  no "point"). `'Open app.py today.'` → `'Open app'` | `'py today'`. `'3.14159'` → "three" |
  "fourteen thousand one hundred fifty-nine" (passage 21).
- **It drops words (an R4 violation in today's app):** `'Upgrade to v1.1.0 now.'` → segments
  `'Upgrade to v1'` | `'1'` | `'0 now'`. The last segment's phonemes are `nˈW` ("now") only; the
  "zero" is lost. Kokoro's own default split keeps it: `… wˈʌn wˈʌn zˈɪɹO nˈW.`
- It strips end punctuation. Current phonemes for `'Are you sure?'` are `ˌɑɹ ju ʃˈʊɹ`; with the
  default split they are `ˌɑɹ ju ʃˈʊɹ?`. Same for `!` and `.`. No segment ever reaches Kokoro with its
  final punctuation.
- It splits hard-wrapped lines mid-sentence (passage 33: "…a hard line" | "break even though…").
- **Intonation:** the claim that stripping causes flat endings was **not supported by measurement**.
  A simple pitch tracker on 3 yes/no questions found falling final pitch with and without the `?`
  (−23.7% vs −22.0%, −16.7% vs −13.4%, −1.5% vs −27.2%). The tracker is crude. A/B WAVs for listening:
  `tests/baseline/probe/h2_question{1,2,3}_{current,kokoro_default}.wav`. Phase 1 restores the
  punctuation anyway, because it's correct input for the model. Whether endings sound better is for
  Paul's ear in Phase 4.

**H3 — CONFIRMED.** `clean_text()` only fixes whitespace; nothing else changes the text before misaki.
What misaki does with raw input (`H3`, phonemes in the JSON):
- `**Bold**` → "bold asterisk asterisk"; `# Release Notes` → "hash release notes"; table pipes
  `|` → dropped silently; `[the README](url)` → "the R-E-A-D-M-E" (misaki treats the link as its own
  markup and drops the URL).
- `split_sentences()` → "splitsentences" (run together); `src/app.py` → "S-R-C slash app-pie".
- `C:\Users\paul\notes.txt` → "C colon backslash users backslash paul backslash notes T-X-T".
- `https://github.com/pawelpc/...` → "H-T-T-P-S colon slash slash github.com slash [garbled] …".
- `25 mm` → "twenty-five m"; `1.2 kg` → "one point two K-G"; `14:30` → "fourteen thirty" (colon
  kept as a pause mark); `2026-10-17` → "twenty twenty-six ten seventeen".
- `~50% →` → "tilde fifty percent right arrow"; `Louis XVI` → "Louis X-V-I".
- Commit hash `e3f15ec..bba2200` → "e three f fifteen ec … two thousand two hundred".
- Already handled well by misaki (no need to duplicate): `$ £ €` amounts, ordinals, 4-digit years,
  `%`, `&`, `Dr`→"doctor", `etc`→"et cetera". (`@` → "at" works, but the dots in
  `example.com` stay as pause marks, not "dot".)
- Unknown words go to espeak (hundreds of `phonemizer words count mismatch` warnings during the render).
  Anything espeak can't handle is silently dropped (`unk=''` in `KPipeline`).

**H4 — CONFIRMED.** No code sets a pause length (`app.py`, `tts_engine.py` and `audio_player.py` insert
no silence). Measured (`H4`, all 33 baseline renders):
- **Kokoro pads every segment** with about 330 ms of near-digital silence before and 485 ms after
  (medians; frames at about −93 dBFS; the same from −60 to −35 dBFS thresholds). So **every boundary
  gets about 0.8 s**, whatever kind it is:

  | Boundary | n | median | p10–p90 |
  |---|---|---|---|
  | inside a chunk (SPLIT_PATTERN cut, e.g. mid-number) | 169 | 825 ms | 725–920 |
  | between sentences, same paragraph | 162 | 823 ms | 750–890 |
  | between paragraphs | 51 | 805 ms | 380–880 |
  | inside a segment (commas etc.) | 979 | 90 ms | 60–420 |

  A paragraph break is no longer than a sentence end, and the cut inside "3.14159" gets the same
  pause as a full stop.
- **The worker adds a synthesis time between sentences.** `_worker` (`app.py:106-139`) synthesizes
  the *next-but-one* sentence before playing the current one, not while it plays. Measured: TTFA ≈
  synth(chunk 1) + synth(chunk 2) (0.443 s predicted vs 0.485 s measured, passage 17). Each gap
  tracks a later chunk's synthesis time (passage 01: 0.650 s gap vs 0.651 s synth) and falls to
  0.0001 s when nothing is left to synthesize (passage 16, last gap).
- **Live sentence gap today** ≈ 0.8 s audio padding + 0.1–0.9 s worker synthesis + 0.11 s device ≈
  **1.0–1.8 s**, varying from sentence to sentence. That fits "choppy".
  The worker fix touches `app.py` (not R2-protected), but it must keep the July D2 skip counting.

### Open issues found in Phase 0
1. **Device-mode harness hang, cause unknown.** Running the real `_worker` with the real `play_audio()`
   (playing silence) hung in the `while sd.get_stream().active` loop (`audio_player.py:43`) on the
   3rd play, twice. I could not reproduce it outside the harness: same thread, GPU synthesis between
   plays, same clip lengths, all finished. Device mode was removed from the harness, and device overhead
   is measured separately instead. Not diagnosed further. Worth asking Paul whether the app ever gets
   stuck mid-read.
2. Source mode logs Kokoro's "Defaulting repo_id" warning (harmless; `KPipeline` isn't given `repo_id`).

### R6 questions for Paul
Asked and answered on 2026-10-17. See "R6 decisions" under Phase 2.

### Reproduce
```bash
python tests/render_passages.py --out tests/baseline
python tests/measure_ttfa.py --out tests/baseline/ttfa.json
python tests/measure_device.py --out tests/baseline/device_overhead.json
python tests/probe_hypotheses.py --baseline tests/baseline
```

---

## Phase 1 — Splitting

### What changed
- **`src/text_processor.py`**: new splitter. `split_sentences()` keeps its signature (the app calls it
  unchanged); it now wraps `split_chunks()`, which also returns each chunk's block kind for Phase 3.
  1. **Blocks first.** Fenced code (kept whole), headings and bold-only lines, table rows, list
     items, quotes (a bare `>` breaks the quote's paragraph) and paragraphs. Hard-wrapped lines are
     joined. Blocks with no words (`---`, `|---|---|`, bare `>`) are dropped, so the worker never gets
     a chunk that makes no audio. Before, `---` triggered the July "sentence skipped" warning.
  2. **Sentences inside prose blocks.** A boundary is end punctuation + optional closing
     quote/bracket/emphasis + whitespace, and it's rejected when: the next word is lowercase;
     the word is a title or Latin abbreviation (`Dr. Mr. Mrs. Prof. St. e.g. i.e. vs. cf. approx.` …);
     a number follows `No. Vol. pp. Fig. Jan.` …; it's a list enumerator (`**1.`); or it's
     `etc. Inc. Jr.`, a dotted acronym (`U.S.`, `p.m.`) or an initial (`J.`) and the next word isn't a
     typical sentence opener (`The`, `Then`, `It`, …). A letter after an operator (`A + B.`) is a
     variable, not an initial. A wordless piece (`⚠️`) joins the sentence before it.
  3. When it's ambiguous, it keeps text together. Kokoro reads an inner period correctly; a wrong split
     costs a full 0.8 s pause and sentence-final intonation.
- **`src/tts_engine.py`**: `SPLIT_PATTERN = r'\n+'` (Kokoro's own default). Kokoro now gets
  whole sentences with their end punctuation, and nothing splits inside "3.5", "v1.1.0" or "app.py".

### Gate evidence
- **Unit tests: 101 passed** (`python -m pytest tests -q`, `tests/test_splitting.py`):
  32 hand-written cases (including the 7 Phase 0 H1 cases and boundary cases such as
  `'We met at 5 p.m. Then we left.'` → 2 chunks); all 33 passages match the reviewed split in
  `tests/passages/expected_splits.json`; for all 33 passages every word of the input is in the chunks,
  in order (R4 at the split step); no wordless chunks; block kinds; `SPLIT_PATTERN` keeps `? ! .`
  and doesn't cut `3.5`, `v1.1.0`, `app.py`.
- **Zero wrong splits** on the passage set. I reviewed every chunk of all 33 passages by hand.
  The first pass found 5 wrong splits (`**1.` enumerator, bold-only pseudo-heading run into the next
  sentence, blockquote `>` break, lone `⚠️` chunk, `A + B. Temperatures` not split). All 5 were fixed;
  the re-review diff showed only those changes.
- **Render** (`tests/phase1/`, same scripts): 33 WAVs, 0 skipped chunks (baseline 1).
  Kokoro segments 415 → 256 (fewer mid-sentence cuts); total audio 1673.7 s → 1572.4 s
  (about 100 s less padding).
- **R3 — CORRECTED, see Phase 2.** At the time I recorded a pass (`tests/phase1/r3.json`: 3 rounds ×
  5 runs, passage 16 −4.5%). That measurement was too weak: 15 samples per side, and "before" always
  ran first in each round. The stronger Phase 2 measurements show passage 16 is about **+12% slower since
  Phase 1** (Phase 1 vs Phase 2 is −0.5%, so the change came in Phase 1). Phase 1 did not pass R3
  on that passage.
- **R2:** no commit touches `src/pipe_listener.py` or `mcp_tts_server/`
  (`git log 0018ba1..HEAD -- src/pipe_listener.py mcp_tts_server` is empty). `app.py` is unchanged.

### R4 at the audio step: words that reach Kokoro but aren't spoken
The recorder now lists tokens that Kokoro received but gave no phonemes (`silent_words` in
`tests/phase1/meta/*.json`). Across 33 passages there are two real words:
- `12` in "(`ISCC` pid 12024, ~12 min of CPU so far)" (passage 05),
- `Don't` in `> ~~"Don't call…` (passage 12).
Both were **already silent before Phase 1** (same misaki result on the Phase 0 segment text),
and both depend on context: "about ~12 min" on its own is spoken. These go to Phase 2
(normalize `~` and strikethrough before misaki), and "no silent words" becomes part of the Phase 2 gate.
(The `_` entries in the phase1 meta for passages 09 and 28 are markdown underscores; the word regex
was tightened afterwards to letters and digits.)

---

## Phase 2 — Normalization

### R6 decisions (asked and answered by Paul, 2026-10-17)
| Question | Paul's answer | How it's implemented |
|---|---|---|
| `St.` / `Dr.` | By context | Before a name: Saint / Doctor; after a capitalized word: Street / Drive |
| Tables | Under 10 data rows: "Table", header row, then "Row N" + cells with a short pause. Larger: "Table", header row, then the row count | `TABLE_MAX_READ_ROWS = 9`; cells joined with commas; "N rows." |
| Emoji | Name them | Short names for common ones (✅ "check mark", ⚠️ "warning", ⏳ "hourglass"…), else the Unicode name |
| Strikethrough | "begin strike", the text, "end strike" | `STRIKE_OPEN` / `STRIKE_CLOSE` |
| URLs and paths | Full, natural | `https://` dropped; "github dot com slash pawelpc slash Natural Voice TTS"; "C drive, Users, paul, notes dot txt"; `%APPDATA%` → "App Data" |
| Dates | "October 17th, 2026" | ISO, US M/D/YYYY and "Oct 3, 2026" all read this way |
| Times | As written | 14:30 "fourteen thirty", 17:06:27 "seventeen oh six twenty seven", 9:00 a.m. "nine A M", 14:00 "fourteen hundred" |
| Versions | "version one point two point zero" | `v1.2.0`; 3-part numbers; 2-part after a known product name ("Python 3 point 11"); `+cu124` → "plus c u 124" |
| Commit hashes | Character by character | 7–40 hex chars with a letter and a digit; `a..b` → "to" |
| Arrow → | "to" | Everywhere (also ⇒) |
| Key combos, operators | Spoken names | Ctrl+Win+T "Control Windows T"; `!=` "not equal to"; `<=`; `×` "times"; `~50%` "about 50%" |
| Code blocks | (brief) a short note | "Code block skipped." |

**Choices I made without asking** (they're standard readings, not two equally plausible ones; all can
be changed after Phase 4): `e.g.` "for example", `i.e.` "that is", `vs.` "versus", `approx.`
"approximately", `cf.` "compare", `No. 7` "number 7", `p./pp.` "page/pages", `Fig.` "figure", `#1`
"number 1"; units spelled out (singular when used as an adjective: "a 1.8 gigabyte installer");
`14–18` "14 to 18"; `[1–20/20]` "1 to 20 of 20"; `1/3` "one third"; phone numbers digit by digit;
Roman numerals after a name "Louis the Sixteenth" (Paul's earlier court-reporter note), but
cardinal after War/Part/Phase/…; list numbers "One. Clone the repo" (misaki ran "1. Clone" together
with no pause); `snake_case` → spaces; `()` dropped; `--flag` "dash dash flag".
Left to misaki on purpose: currency, ordinals, years, `%`, camelCase, `Mr.`, `Mrs.`, `Ph.D.`, `U.S.`,
`a.m.`, `etc.`.

### What changed
- **`src/normalizer.py`** (new): `prepare_speech(text)` → `split_chunks()` (Phase 1), then block
  handling (headings get a final period, bullets dropped, list and heading numbers spoken, quotes
  unwrapped, tables per Paul's rule, code blocks → "Code block skipped.") and `normalize_inline()`
  for each chunk. Each `Spoken` keeps its screen `source`. Code spans are protected while
  markdown emphasis is removed, so `**` or `_read_exactly` inside backticks isn't treated as markup.
- **`src/app.py`**: new `speech_chunks(text)`, which `_worker` now calls in place of
  `split_sentences(text)`. The render harness calls the same function, so the WAVs match the app.
  Nothing else in the worker changed (the D2 skip logic is intact).

### Gate evidence
- **Unit tests: 242 passed** (`python -m pytest tests -q`). `tests/test_normalizer.py` adds:
  36 hand-written inline cases (every R6 decision, markdown/code, numbers, units, abbreviations, and
  things deliberately left to misaki) and 8 block cases (headings, lists, quotes, code, small and
  large tables). These hand-written cases caught two real bugs, which are now fixed: `+cu124.` swallowed the
  sentence dot, and `World War II.` before a period wasn't recognized.
- **Expected outputs:** each passage's spoken text matches `tests/passages/expected_spoken/<id>.txt`
  (one chunk per line). I reviewed all 278 chunks by hand. The first review found 6 wrong outputs
  (`not.75`, "Copyright copyright", "5 volts, 2 amps supply", "October 3" vs ordinal, numbered
  headings run together, lowercase "figure" at a sentence start), and the re-review diff showed only
  those fixes.
- **R4:** `test_every_word_gets_phonemes` runs misaki exactly as Kokoro does on every spoken chunk
  of all 33 passages: no word is left without phonemes. The Kokoro-level render (`tests/phase2/meta`,
  `silent_words`) also shows **0 silent words in 33 passages** (Phase 1 had 2: "12" and "Don't").
  The only words deliberately not spoken are code-block contents and rows of tables with 10 or more
  data rows (both Paul's/brief's rules).
- **R5:** `test_screen_text_unchanged`: `prepare_speech()` never modifies its input, and every
  spoken chunk's `source` is found verbatim in the screen text. The app has no display of its own;
  the normalized copy only goes to Kokoro.
- **Render** (`tests/phase2/`): 33 WAVs, 0 skipped, total audio 1461.9 s (Phase 1: 1572.4 s;
  code blocks are now a one-line note).

### R3 at the Phase 2 checkpoint — OPEN (fails on one passage)
R3 is a before/after rule for the finished work, but I measured it at each checkpoint:
- `tests/phase2/r3.json` (Phase 0 vs Phase 2, 6 alternating rounds × 5 runs = 30 samples a side,
  bootstrap 95% CI): passage 17 0.520 → 0.535 s, **+2.9%** (CI −3.7% to +11.6%); passage 16
  0.652 → 0.731 s, **+12.1%** (CI +4.8% to +14.9%); passage 01 0.520 → 0.291 s, **−43.9%**
  (its first chunks are now a short heading and sentence). **Fails R3 on passage 16.**
- Where it comes from: Phase 1 vs Phase 2 on passage 16 (ABBA order, 8 rounds, 40 samples a
  side, `tests/phase2/r3_phase1_vs_phase2_p16.json`): **−0.5%** (CI −1.7% to +0.8%). So Phase 2
  adds nothing; the change came in Phase 1.
- What it isn't: the normalizer takes 0.7 ms on this passage. With a warm GPU, Kokoro synthesizes
  passage 16's two first chunks within 0.5% of each other with and without the end punctuation
  (88 vs 91 ms and 342 vs 344 ms, 3 rounds × 10). The cause is **not identified**.
- Method fix: `compare_ttfa.py` now alternates which side runs first (ABBA) and reports a
  bootstrap confidence interval.
- Plan: Phase 3 changes the worker so the first sentence plays without waiting for the second one
  to be synthesized. That is the step this TTFA depends on. The final R3 check (Phase 0 vs Phase 3, ABBA)
  decides it. If it still fails there, I stop and report to Paul.

### Things to listen for in Phase 4 (faithful to the rules, but maybe not ideal)
- A leading `→` reads "to" ("to "You may strip…"", passage 12) because "to" applies everywhere.
- "Louis XVI" is converted even where the sentence is *about* the notation (passage 15).
- A version inside a file name reads with "dot" ("Setup 1 dot 1 dot 0 dot exe").
- "the about 1.8 gigabyte installer" (`~` is always "about").

---

## Phase 3 — Pauses

### What changed
- **`src/pauses.py`** (new). Pause targets as named constants:
  `COMMA_PAUSE_MS = 200` (`, ; : — …` inside a sentence), `SENTENCE_PAUSE_MS = 450`,
  `ITEM_PAUSE_MS = 550` (between list items or table rows), `PARAGRAPH_PAUSE_MS = 800`,
  `HEADING_PAUSE_MS = 800`. These are my starting values; Paul's ear in Phase 4 decides.
  - `pause_after(chunks, i)` picks the boundary kind from the chunk's block (Phase 1 `split_chunks`).
  - `trim_edges()` cuts Kokoro's ~330 ms lead and ~490 ms tail of near-silence from every chunk.
  - `set_clause_pauses()` uses Kokoro's token timestamps (`start_ts`/`end_ts`) to find the pause at
    each clause mark and replaces the whole silent run with exactly 200 ms. Where Kokoro left no
    silence, 200 ms is inserted at the quietest frame between the two words, with 4 ms fades.
  - `shape_chunk()` builds a chunk's final audio and returns a `PauseMark` for each pause.
- **`src/tts_engine.py`**: `synthesize_segments()` also yields Kokoro's tokens; `synthesize()`
  wraps it unchanged.
- **`src/app.py`** worker: a producer thread (`_produce`, `PREFETCH_CHUNKS = 2`) synthesizes the next
  chunks **while the current one plays**. Before, the worker synthesized the next-but-one sentence
  *before* playing the current one, so each gap included a synthesis time (Phase 0, H4) and the first
  audio waited for two syntheses. `render_chunk()` (synthesize + shape) is used by both the worker
  and the render harness. A lock keeps synthesis to one at a time across a stop and a new read. The
  D2 behaviour is kept: a chunk with no audio is skipped, logged and counted, with one notification
  per read.

### Gate evidence
- **Pause gate: PASS.** `tests/measure_pauses.py` reads only the WAVs (`tests/phase3/wav`), finds
  the silent run at each recorded pause, and compares its length to the target
  (`tests/phase3/pauses.json`): **516 of 516 within ±50 ms**. Comma 304/304 (max error 25 ms), sentence
  129/129, paragraph 48/48, item 21/21, heading 14/14 (0 ms).
  The first full run had 518/519. The miss was a comma pause wrongly placed after "…" when only a
  closing quote followed it. It was fixed and has a regression test.
  The smoke run before that had found a real bug: only the part of Kokoro's pause inside the search window
  was replaced, which left 380 ms instead of 200 ms. Also fixed, with its own test.
- **Unit tests: 257 passed** (`python -m pytest tests -q`). New: `tests/test_pauses.py` (11,
  synthetic audio) and `tests/test_worker.py` (4, the real `app._worker` with a fake engine and
  player: every chunk plays in order; a failing chunk is skipped and reported exactly once (D2);
  stop ends the read and the synthesis thread, and the next read plays in full; chunk 2 is
  synthesized while chunk 1 plays, with no extra wait).
- **Render** (`tests/phase3/`): 33 WAVs, 1346.6 s of audio (baseline 1673.7 s), 0 skipped,
  0 silent words (R4).
- **R2:** `pipe_listener.py` and `mcp_tts_server/` are untouched (no commit touches them).

### What the live app adds that the WAVs don't show
Each chunk is still played with its own `sd.play()` call. On Paul's Bluetooth headset that adds
about **+0.11 s per chunk** (`tests/baseline/device_overhead.json`, median of later plays), and about
+0.89 s on the first play after idle. So a 450 ms sentence pause is about 560 ms live. If Paul hears that
as too long or uneven, the fix is a single continuous output stream in `audio_player.py` (not done:
it changes pause/stop behaviour and needs a live test on his device).

### R3 — final check, Phase 0 vs Phase 3: PASS
`tests/phase3/r3.json` (ABBA order, 6 rounds × 5 runs = 30 samples a side, bootstrap 95% CI):

| Passage | Phase 0 | Phase 3 | Change (95% CI) |
|---|---|---|---|
| 17 July regression string | 0.526 s | 0.131 s | **−75.1%** (−76.5% to −72.2%) |
| 16 real `speak` call | 0.644 s | 0.367 s | **−43.0%** (−60.2% to −41.2%) |
| 01 real markdown response | 0.517 s | 0.117 s | **−77.4%** (−78.0% to −76.1%) |

Even the worst confidence bound (−41.2%) is far inside the +10% limit, so the +12% open since Phase 1 is
resolved: the first sentence no longer waits for the second to be synthesized. Also, the first chunk
now starts with its sound, not ~330 ms of Kokoro's leading silence, so the audible start comes earlier
still (not included in these numbers, which stop at the first `play_audio()` call).
Passage 16 is higher than the other two. A likely but **unverified** reason: in the harness each read is
stopped after 4 chunks, and the next read's first synthesis waits on the lock while the old
producer finishes its current chunk (passage 16's second chunk takes about 340 ms). The same wait would
happen when Paul starts a new read while one is still playing.
---

## Phase 4 — Paul's listening check

- **A/B page:** https://claude.ai/artifact/YavTFrd8ndpBu7MPSeKkTZ (private to Paul). It holds 33 pairs,
  filterable by category: **Before** = `tests/baseline/wav` (v1.1.0 code), **After** = `tests/phase3/wav`
  (final code, commit `2478f8f`). Each pair is rated Better / Same / Worse with an optional note,
  and there is an overall Pass / Not yet.
- **Where the ratings go:** the page's database, collection `ratings` (one document per passage id) and
  `summary/overall`, read back with `ArtifactData list`. The page falls back to browser storage
  plus a "Copy results as text" button if the store isn't available.
- **Source:** `tests/phase4/listening.template.html` + `tests/phase4/build_page.py` (which fills in the
  passages, the Phase 0 chunks, the reviewed spoken output and the render durations).
  The MP3s (24.2 MB, 64 kbit/s) are made by `build_page.py --audio-out <dir>` and are not committed.
- **Checked after publishing:** a probe rating written, listed and deleted through the page's store; one
  published MP3 fetched back byte-identical (152,640 bytes). Not checked: playback in Paul's browser
  or phone, which only he can confirm.
### Result: PASS
Paul's ratings, verbatim in `tests/phase4/ratings.txt`: **32 better, 1 same (#16, the clean-prose speak
call), 0 worse; overall: pass.** He rated on the local copy of the page, so the ratings reached me
by "Copy results as text", not through the page's store (which is empty).

### Paul's notes applied after the pass (2026-10-17)
| # | Paul's note | Change | Evidence |
|---|---|---|---|
| 7 | Small pause between the row number and the first cell | A `.`/`!`/`?` inside a chunk ("Row 1.", "One. Clone…") now gets `INNER_STOP_PAUSE_MS = 300`. misaki keeps the dot inside "Mr.", "U.S.", "etc.", "Ph.D." (checked), so abbreviations don't get the pause | `test_inner_stop_pause_after_row_label`; pause gate below |
| 27 | Colon between two numbers reads "by" when it can't be a time | `RATIO_RE`: two numbers, first over 12 or second over 59, no a.m./p.m. → "16 by 9". Three-part times unchanged. Asked first (R6): his rule as written also makes 24-hour times read "14 by 30" (passage 26); he chose that | 3 new inline cases; passages 26, 27 expected files updated |
| 31 | "A" next to a symbol should be the letter | misaki read "A" in "not A + B" as the article `ɐ` (checked). A lone capital A next to an operator is now written `[A](/ˈA/)`, misaki's own phoneme markup, giving `ˈA` | 2 new inline cases; passage 31 expected file updated; R4 misaki test passes on it |

Edge cases of the #27 rule, as written: "4:3" stays as is (neither number is over the limits) and "14:00" reads "14 by 0".

### Notes for future sessions (Paul asked not to do these now)
- **#8 Pronunciation list for names and brands:** "Cowork" is read "Cow ork". It should be "Co work". misaki's
  `[word](/phonemes/)` markup (used for #31) is a ready mechanism: a small user-editable lexicon applied
  in the normalizer.
- **#13 Emphasis** for **bold**, `*asterisk*` and ALL-CAPS (non-abbreviation) text: pitch, loudness, duration.
  Kokoro has no emphasis input. Options to research: misaki stress markup, a slower `speed` per span
  (Kokoro takes speed per call), and gain on the span's audio.
- **Live sentence gap on Paul's headset** (+~0.11 s per chunk, Phase 3): a continuous output stream in
  `audio_player.py`, if he hears it.
### Re-check after the notes (`tests/phase4/render`, final code)
- Pause gate: **539/539 within ±50 ms** (comma 304, inner stop 23, sentence 129, paragraph 48, item 21,
  heading 14; worst error 25 ms) (`tests/phase4/render/pauses.json`). 0 skipped, 0 silent words.
- Unit tests: **263 passed** (`python -m pytest tests -q`).
- R3 (Phase 0 vs final, ABBA, 30 samples a side, `tests/phase4/render/r3.json`): passage 17
  0.533 → 0.130 s (**−75.6%**), passage 16 0.680 → 0.270 s (**−60.3%**), passage 01 0.516 → 0.118 s
  (**−77.1%**). Pass.
- The listening page now plays this render as "After", so Paul can spot-check #7, #26, #27 and #31.

---

## Rules compliance (R1–R8), final
- **R1** Model, voice, speed unchanged: same `kokoro-v1_0.pth`, `DEFAULT_VOICE = 'af_heart'`, `DEFAULT_SPEED = 1.0`
  (`src/tts_engine.py`). Source mode only gained a local path to the same file (Phase 0). Emphasis slows only the
  emphasized words, inside the same model pass; the default speed is unchanged.
- **R2** `pipe_listener.py` and `mcp_tts_server/` untouched by every commit, the follow-up sessions' included:
  `git log 0018ba1..HEAD -- src/pipe_listener.py mcp_tts_server` is empty. The worker's July D2 skip/notify
  behaviour is kept (`tests/test_worker.py`).
- **R3** Time to first audio not worse: v1.1.0 vs final −76%, −60%, −77% (`tests/phase4/render/r3.json`). With
  emphasis on, released 1.2.0 vs master: worst +6.4% (`tests/emphasis/r3_emphasis_on.json`), after fixing a 2.7 s
  first-read regression in the emphasis code. Measured +12% on one passage at the Phase 1–2 checkpoints; found
  with the stronger A/B and resolved in Phase 3.
- **R4** No dropped words: the split step keeps every word (`test_no_words_lost`); misaki gives every spoken word
  phonemes (`test_every_word_gets_phonemes`); renders show 0 silent words. Phase 1 found 2 words that v1.1.0
  already lost, plus the lost "zero" of H2; all fixed. Deliberately not spoken: code-block contents and the rows
  of tables with 10 or more data rows (brief and Paul's rule).
- **R5** Screen text never changed: `test_screen_text_unchanged`. Normalization, the pronunciation list and
  emphasis only build the spoken copy.
- **R6** Every two-way reading was asked: 11 questions on 2026-10-17 (§Phase 2 R6 decisions, §Phase 4 #27).
  Standard readings I chose without asking are listed under Phase 2.
- **R7** No installer build before Paul passed Phase 4. The 1.2.0 build ran in Phase 5, after his pass, and Paul
  published it himself. No installer exists yet for the post-release work on master.
- **R8** A commit at each gate: `ce7177d` (0), `499fc3b` (1), `62d5cab` (2), `2478f8f` (3), `b2c866d`/`4f44430`/`0fa1c5d`
  (4), `711490e`/`58d1251`/`77e6432` (5), `33fe4cd` (review fix). I pushed nothing; Paul pushed through `b57abfc`.

## Open issues
1. **Paul's uncommitted MCP edits are gone from disk** (`mcp_tts_server/install_config.py`, plugin `SKILL.md`).
   They were reverted after the 1.2.0 build by someone other than me, and no commit or stash holds them. Paul
   chose not to restore them ("just commit the current fixed version"). A byte-exact copy is in this session's
   scratchpad (`paul_mcp_edits_backup/`), which is temporary.
2. **R3 with emphasis on is not fully resolved.** Every median is within +10%, but some 95% intervals reach past it
   (up to +21% on passage 16, which is noisy on this machine). More rounds would narrow them.
3. **Emphasis approval:** commit `8061bf8` states that Paul approved emphasis on by default after listening. I did
   not verify that in the follow-up session.
4. Device-mode harness hang (Phase 0): not reproduced outside the harness, not diagnosed.
5. Live playback adds about 0.11 s per chunk on Paul's Bluetooth headset (a separate `sd.play()` per chunk). The fix
   would be a continuous output stream in `audio_player.py`.
6. Paul's PC plays through the headset's hands-free profile (narrowband audio).
7. Starting a new read while one plays waits for the old chunk's synthesis to finish (likely cause of passage 16's
   higher TTFA; not verified).
8. `src/main.py` (terminal fallback) gets the new splitter but not the normalizer, pauses or emphasis.
9. Python is 3.10.11 on this machine; the brief's style rule says 3.11 (the code avoids 3.11-only features).
10. The emphasis and lexicon listening WAVs exist only in the side worktrees (`.claude/worktrees/…`), which the app
    may clean up.
---

## Phase 5 — Release build (2026-10-17)

- **Version 1.2.0** in `installer/setup.iss`, `src/dialogs.py`, `build.bat`; `version_info.txt` to 1.2.0.0
  (it was still 1.0.0.0). `naturalvoicetts.spec` lists `normalizer`, `pauses`, `num2words`. README: v1.2.0
  link, "What's new in 1.2.0", local model folder, test command, build note. Commit `711490e`.
  Release notes: `release_notes/1.2.0.md`.
- **Built from master without the side branches**, as Paul didn't ask to merge them: the pronunciation list
  (`claude/jovial-hypatia-0d6e6d`) and the emphasis research (`claude/angry-engelbart-71f331`).
- **Two hazards, handled:**
  1. PyInstaller replaces `dist/NaturalVoiceTTS/`, which held the only local copy of the model, and
     `build.bat` copies the model back from the HF cache, which had none. Before building, I copied the model into
     `%USERPROFILE%\.cache\huggingface\hub\models--hexgrad--Kokoro-82M\snapshots\local-from-dist\`
     (29 files, SHA-256 identical). The build found it there.
  2. `build.bat` copies the working-tree `mcp_tts_server/` into the installer. Paul chose to ship the
     committed versions, so his two uncommitted files were stashed for the build and then restored. Git
     rewrote their line endings on restore (LF to CRLF), so I put back the exact original bytes from a
     backup copy; the SHA-256 now matches the pre-build hash.
- **Build:** `build.log`, started 23:19:45, BUILD COMPLETE. `dist\NaturalVoiceTTS_Setup_1.2.0.exe`,
  1,885,275,055 bytes (under GitHub's 2 GiB asset limit).
- **Checked in the build:** the model in `dist` matches the protected copy (config, `.pth`, voices; 27 voices);
  the bundled `mcp_server` files are byte-identical to HEAD (`install_config.py`, plugin `SKILL.md`, `server.py`);
  the frozen exe's archive contains `normalizer`, `pauses`, `num2words`, `text_processor`, `tts_engine`,
  `misaki.en`, `kokoro.pipeline`.
- **Launch test, PASS** (Paul quit the installed app first). `dist\NaturalVoiceTTS\NaturalVoiceTTS.exe` reached
  "Ready!" in 10 s (`%APPDATA%\NaturalVoiceTTS\app.log`, 23:51:20 to 23:51:29): bundled espeak-ng, Torch 2.6.0+cu124
  on the GTX 1650, bundled model, pipe listener up. A test sentence sent through the named pipe
  (`test_pipe.py`, the MCP path): `header=101 bytes, received=101 bytes`, read as **1 sentence** (no split at
  "Dr."), spoken copy "…version 1 point 2 point 0, and Doctor…", played, `Finished reading` with no skips or errors.
  Whether it sounded right is for Paul to confirm; the log shows it played. The first read after launch took about 2 s to start (cold GPU, first synthesis after load). The
  48 "Hidden import not found" PyInstaller messages (`munch`, `torch.distributed._shard.checkpoint.*`)
  caused no error at startup or on that read. The test instance was then closed; no app process left running.
- `src/main.py` (terminal fallback) still runs with the new splitter but not the normalizer or pauses.
---

## After the release: review of the merged follow-up sessions (2026-10-22)

The pronunciation list (`b18f35a`, Paul's note #8) and spoken emphasis (`868153a`, note #13; switched on by
default in `8061bf8`) were merged onto master after v1.2.0 was published. **They are not in the 1.2.0 installer**
(the `v1.2.0` tag is at `b57abfc`; the GitHub asset is the 1,885,275,055-byte build tested above).

Review findings:
- **Sound:** 345 tests passed as merged. R2 holds (no change to `mcp_tts_server/` or `pipe_listener.py`).
  `emphasis.forward()` matches kokoro 0.9.4's `forward_with_tokens` line for line apart from the two intended
  changes (per-phoneme speed with span-aware rounding, scaled F0). Pause gate with emphasis on: 104/104
  (`tests/emphasis/passages_on/pauses.json`). An emphasized sentence costs ~7% more to synthesize
  (`tests/emphasis/synth_cost.json`).
- **Regression found and fixed:** with emphasis on, the first text after startup containing an ALL-CAPS word
  took **2,726 ms** to prepare instead of 3.7 ms. `emphasis._golds()` built a second copy of misaki's
  178,646-entry dictionary (2.69 s). Neither R3 run had seen it: the emphasis R3 (`tests/emphasis/r3.json`)
  ran while emphasis was still off, and R3 takes medians of warm runs. **Fix:** `_golds()` now reuses the
  running pipeline's own US dictionary (`pipeline.g2p.lexicon.golds`), and loads a copy once only when there
  is no pipeline. After the fix, with Kokoro loaded, the first `prepare_speech()` took **8.4 ms**, and the dictionary
  is the pipeline's own object. Tests: `test_golds_reuses_the_pipeline_dictionary`,
  `test_golds_ignores_a_british_pipeline`.
- **R3 with emphasis on** (`tests/emphasis/r3_emphasis_on.json`; released 1.2.0 `b57abfc` vs master with the
  fix; ABBA, 6 rounds × 5 runs; both sides timed with the current `measure_ttfa.py`):

  | Passage | 1.2.0 | Now | Change (95% CI) |
  |---|---|---|---|
  | `ttfa/emphasis_first.txt` (emphasized first chunk: "Important", "NOT") | 0.469 s | 0.499 s | +6.4% (−20.0% to +11.3%) |
  | 17 July regression | 0.135 s | 0.134 s | −1.0% (−5.5% to +4.6%) |
  | 16 `speak` call | 0.282 s | 0.284 s | +0.6% (−11.6% to +21.2%) |
  | 01 markdown | 0.117 s | 0.122 s | +4.3% (−1.4% to +9.3%) |

  **Pass** by the median rule (worst +6.4%, in line with the 7% synthesis cost). It is not fully resolved,
  because some confidence intervals reach past +10%. First read after startup (run 1 of each process, emphasized
  passage): 0.238–0.264 s before, 0.254–0.296 s now, so the 2.7 s delay is gone. That passage's later runs are
  slower than its first on both sides, which points to the harness, not the code.
- **Corrected:** `emphasis.py` comments claimed "about 12% longer" and "+1.6 semitones". The measured effect
  (FINDINGS.md) is about +20% span length, +8% pitch and +1.8 dB; README and comments now give the measured values.
- **README:** a "Coming in the next release" section; the pronunciation list and spoken emphasis are marked as
  not in the 1.2.0 installer. Spoken emphasis is now documented, including how to turn it off.
- **Minor:** `emphasis` added to the spec's source-module list (it was bundled anyway through the normalizer's
  import). The render harness doesn't record emphasized chunks' Kokoro segments. R4 for their words is still
  covered by `test_every_word_gets_phonemes`, which runs the same misaki G2P.
- **Paul's uncommitted MCP edits** (`install_config.py`, plugin `SKILL.md`) are no longer on disk. The working
  tree matches the July commit, and no commit or stash holds them. Who reverted them is not known. A byte-exact
  copy from before the Phase 5 build is in this session's scratchpad (`paul_mcp_edits_backup/`).
- Not verified by me: that Paul approved emphasis on by default (it is stated in `8061bf8`'s message).
