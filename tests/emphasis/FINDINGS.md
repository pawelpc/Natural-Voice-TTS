# Emphasis for bold, *italic* and ALL-CAPS words: findings

Paul's Phase 4 note #13. Research, then a prototype that is **off by default** (`src/emphasis.py`,
`EMPHASIS_ENABLED = False`). Date: 2026-10-17. Same model file, voice `af_heart`, default speed 1.0 (R1).

## Listen first

Open **`tests/emphasis/listen.html`** from disk in a browser. It has 8 sentences × 8 versions,
and 4 real passages played off and on. The WAVs are gitignored, so they exist only on this machine
(re-create them with the commands at the end).
Listen for three things: does the word stand out, does it still sound natural, and is there a click or a
break around it.

## Recommendation

Use **one Kokoro pass with the span changed inside it**: about 20% longer, about 8% higher in pitch,
and about 2 dB louder (the prototype's default). It's the only option that changes all three things Paul
asked for, leaves the rest of the sentence as it was, and has no join. The two other ideas in the brief
fail on evidence:
a separate call for the span breaks the sentence's melody, and misaki stress markup does almost nothing.
Turn it on only after Paul has listened. Before that, one question for him (R6): should line-start bold
labels ("**Bottom line:**", "**Fix:**") get emphasis too? Today they do.

## What was tried (8 sentences, median change vs. today)

Measured by `tests/probe_emphasis.py` (`tests/emphasis/emphasis.json`). "Span" is the emphasized words,
"rest" is everything else in the sentence. Length comes from Kokoro's own alignment. Pitch is the median F0
(YIN) on voiced audio, and loudness is RMS.

| Variant | How | Span length | Span pitch | Span loudness | Rest pitch | Rest loudness |
|---|---|---|---|---|---|---|
| repeat | today, rendered again (noise floor) | +0% | +0.3% | +0.04 dB | +0.4% | +0.06 dB |
| stress | misaki `[word](2)` stress markup | +0% | +1.2% | +0.1 dB | −0.7% | +0.05 dB |
| split | span as its own call at speed 0.85, joined | **+84%** | +6.8% | +0.5 dB | **+7.7%** | +0.6 dB |
| gain | +4 dB on the span's audio | +0% | +0.1% | **+3.7 dB** | +0.3% | +0.09 dB |
| dur | span phonemes at speed 0.80, same pass | **+27%** | +0.9% | −0.0 dB | −0.9% | +0.03 dB |
| pitch | Kokoro's F0 curve ×1.12 on the span, same pass | +0% | **+10.4%** | +0.2 dB | +0.1% | +0.03 dB |
| **combo (prototype)** | speed 0.85 + F0 ×1.10 + 2 dB, same pass | **+20%** | **+7.9%** | **+1.8 dB** | −1.4% | +0.02 dB |
| strong | speed 0.80 + F0 ×1.15 + 3 dB, same pass | +27% | +13.6% | +2.6 dB | −0.8% | +0.03 dB |
| pitchgain | F0 ×1.12 + 3 dB, no slowing | +0% | +9.5% | +2.9 dB | +0.5% | +0.03 dB |

Noise: Kokoro's decoder is not deterministic, so two renders of the same sentence differ. Per sentence, span
pitch moved by up to ±5% between two identical renders (`repeat`), so only the medians are meaningful.
The YIN "pitch jump at the span edge" measure was tried and dropped, because it moved by several semitones
between identical renders.

### Why not a separate call (the brief's second idea)
Each Kokoro call is a complete utterance, with its own start and end melody and final lengthening. The span
came out 84% longer (not the 18% that speed 0.85 asks for), the rest of the sentence rose 7.7% in pitch
because every piece restarts high, and per-sentence pitch at the span went anywhere from −20% to +22%.
You can hear it in the listening page: the sentence breaks into three phrases. It can't be tuned, because
the break comes from the call boundary itself.

### Why not misaki stress markup (the first idea)
`[word](2)` only moves a stress mark, and most content words already carry primary stress, so the phonemes
usually don't change. Measured: +0% length and +1.2% pitch, within the noise. misaki already gives an
ALL-CAPS word primary stress on its own (`NOT` → `nˈɑt`, `not` → `nˌɑt`), which is why caps words sound
slightly stronger today.

### Why the one-pass approach is clean
- **No join.** It's one forward pass and one waveform. Kokoro divides each phoneme's predicted duration by
  `speed`, and `speed` can be a per-phoneme tensor. The F0 curve is changed before the decoder, with 100 ms
  ramps, and the gain uses an envelope with 50 ms ramps, interpolated per sample (a unit test checks it never
  steps). The weights and the model file don't change.
- **The rest stays put.** Outside the span, every phoneme keeps exactly Kokoro's duration (tested). Rest
  pitch moves by less than the noise floor (−1.4% median, against ±5% between identical renders), and rest
  loudness by 0.02 dB.
- **No added roughness.** YIN aperiodicity on the span is unchanged (Δ 0.00) for every one-pass variant.
- **Alignment checked.** The audio lines up with Kokoro's alignment frames: lag 0 ms, r = 0.94 over 8
  sentences (energy curve against audio RMS). Kokoro's own `start_ts` timestamps run about 75–100 ms early
  (its "−3 frames" offset), so the gain uses the frames, not the timestamps.
- **A rounding trap, fixed.** Kokoro rounds each phoneme to whole 25 ms frames, so speed 0.85 rounded away
  on short words: "whole" stayed at 7 frames. Inside the span, durations are now rounded cumulatively, so
  the span really gets about 1/0.85 longer. Outside the span, Kokoro's own rounding is unchanged.
- **Pauses intact.** Four real passages rendered with emphasis on: 0 deliberate pauses outside ±50 ms
  (`tests/emphasis/passages_on/pauses.json`).

## What gets emphasis (prototype rules)

- `**bold**`, `__bold__`, `*italic*`, `_italic_`, nested ones too, of up to `EMPHASIS_MAX_WORDS = 5` words.
  A longer span, such as a whole bold sentence, is read plain. Headings get none, because bold there is formatting.
- **ALL CAPS:** a word misaki knows only in lower case ("NOT", "NEVER", "DON'T"). Not emphasized: words the
  dictionary has in capitals, which are acronyms misaki spells out (API, GPU, IT, US); file names (SKILL.md);
  a word right after a number (4 PM, 8 GB); Roman numerals (XVI); and a line that is all capitals (shouting,
  so there's nothing to contrast with). All 33 passages have **zero** caps emphasis, because every caps word
  in them is an acronym or a file name (tested).
- **Never changes words (R4, R5).** A chunk keeps its emphasis only if its words come out exactly as they do
  with emphasis off. A marker inside "Louis **XVI**" would stop the Roman-numeral rule, so that chunk is read
  plain. Across all 33 passages, the words with emphasis on equal the words with it off (tested), and 55
  spans are kept.

## Cost and rules
- **R1:** same model, voice and default speed. The user's speed still applies, multiplied on the span.
- **R2:** `pipe_listener.py` and `mcp_tts_server/` are untouched.
- **R3:** see the "R3" section below.
- **Off by default:** with `EMPHASIS_ENABLED = False`, chunks carry no spans, and `render_chunk` calls the
  engine exactly as before (tested). The only extra work is one `if`.
- **On:** chunks with no emphasis still take Kokoro's own pipeline. A chunk with emphasis costs the same
  single forward pass, plus a second normalization pass of the text (milliseconds).

## R3
`tests/emphasis/r3.json`: commit `0fa1c5d` against this branch, emphasis off (the default), in ABBA order,
6 rounds × 5 runs = 30 samples a side. Result: **PASS.**

| Passage | Before | After | Change (95% CI) |
|---|---|---|---|
| 17 July regression string | 0.134 s | 0.129 s | −3.8% (−6.8% to +1.8%) |
| 16 real `speak` call | 0.302 s | 0.288 s | −4.8% (−25.6% to +33.7%) |
| 01 real markdown response | 0.116 s | 0.116 s | +0.0% (−3.4% to +3.2%) |

Passage 16's interval is wide because its timings sit in two clusters, about 0.11 s and about 0.24–0.40 s,
on both sides (the same pattern as Phase 3). Its median is lower after.
Two caveats. During the run I made two cosmetic edits to the "after" checkout (renaming a variable, and the
`chunks[i].emphasis` lookup), and for a few seconds the file was half edited. All 30 "after" samples
completed. Another Claude session may have shared the GPU during the run.

**With emphasis on** (not an R3 measurement): synthesizing "You must **back up your files** before you
upgrade." took 170 ms against 159 ms plain (median of 10, alternating; `tests/emphasis/synth_cost.json`).
That's +7%, and most of it is the extra audio (+20% on four words). Only chunks that contain emphasis pay it.

## Known limits
- The prototype copies the steps of `KModel.forward_with_tokens` from kokoro 0.9.4. A kokoro upgrade needs
  a re-check. `test_forward_without_emphasis_matches_kokoro` fails if the copy drifts.
- The span gets one plateau. Real speech puts the pitch peak on the stressed syllable. Good enough to judge
  by ear. A per-syllable accent shape would be the next refinement, if Paul wants more.
- Emphasized chunks bypass the test recorder in `render_passages.py`, so their `silent_words` aren't
  recorded (the words themselves are proven equal to the plain reading).
- A bold span that crosses a sentence boundary is split by the splitter like today. Each part is
  checked on its own.

## Reproduce
```bash
python tests/probe_emphasis.py --out tests/emphasis
python tests/render_passages.py --out tests/emphasis/passages_off --only 01_markdown_what_i_did 03_paths_urls_source_vs_frozen 04_rhythm_solid_confirmation 15_markdown_what_i_built
python tests/render_passages.py --emphasis --out tests/emphasis/passages_on --only 01_markdown_what_i_did 03_paths_urls_source_vs_frozen 04_rhythm_solid_confirmation 15_markdown_what_i_built
python tests/measure_pauses.py --render tests/emphasis/passages_on --out tests/emphasis/passages_on/pauses.json
python tests/emphasis_page.py
python tests/compare_ttfa.py --before <checkout of 0fa1c5d> --after . --rounds 6 --repeats 5 --out tests/emphasis/r3.json
```
