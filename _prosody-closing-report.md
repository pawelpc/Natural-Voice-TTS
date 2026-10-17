# Closing Report (DRAFT): Natural Voice TTS — Speaking Flow and Text Handling

**Model:** Opus 5.5 (`claude-opus-5-5`) · **Started:** 2026-10-17
**Status:** Phase 2 gate passed. R3 is open (+12% on one passage, came in Phase 1). Phase 3 next.

| Phase | Gate | Status | Evidence |
|---|---|---|---|
| 0 Environment and baseline | source synthesis runs; 30 baseline WAVs; H1–H4 decided | **Passed** | §Phase 0 below |
| 1 Splitting | unit tests, zero wrong splits | **Passed** (R3 later found failing on passage 16) | §Phase 1 below |
| 2 Normalization | expected-output files match; R4, R5 hold | **Passed**; R3 open | §Phase 2 below |
| 3 Pauses | measured gaps within ±50 ms of targets | not started | |
| 4 Paul's listening check | Paul passes it | not started | |
| 5 Release | only after Phase 4 | not started | |

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
