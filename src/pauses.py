"""Deliberate pause lengths between and inside spoken chunks.

Kokoro pads every clip with about 0.33 s of silence before and 0.49 s after,
and its own comma pauses vary from 60 ms to over 400 ms (Phase 0, H4). This
module trims that padding and sets each pause to a fixed length chosen by the
kind of boundary, so a paragraph break sounds longer than a sentence end and a
comma is a short breath.
"""

import logging
import re
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000

# --- Pause targets (ms) ---
COMMA_PAUSE_MS = 200        # , ; : — … inside a sentence
SENTENCE_PAUSE_MS = 450     # between sentences of one paragraph
ITEM_PAUSE_MS = 550         # between list items, or between table rows
PARAGRAPH_PAUSE_MS = 800    # between paragraphs and other blocks
HEADING_PAUSE_MS = 800      # after a heading

CLAUSE_PUNCT = frozenset(',;:—…')
SENTENCE_END = '.!?…'
WORD_RE = re.compile(r'[^\W_]')

# --- Silence detection ---
FRAME_MS = 5
SILENCE_DBFS = -45.0          # frame RMS below this is silence (same threshold as the tests)
MIN_SILENT_RUN_MS = 30        # a shorter quiet stretch is not treated as Kokoro's own pause
SEARCH_SLACK_MS = 40          # look this far beyond the timestamps for the silent run
FADE_MS = 4                   # fade at an inserted cut, so splicing never clicks


@dataclass
class PauseMark:
    """Where a deliberate pause was placed in a chunk's audio (for measurement)."""
    kind: str        # comma, sentence, item, paragraph, heading
    target_ms: int
    at_ms: float     # start of the pause within the returned audio


def pause_after(chunks: list, i: int) -> tuple[str, int]:
    """Kind and length of the pause after chunk i (chunks are normalizer.Spoken)."""
    if i >= len(chunks) - 1:
        return 'end', 0
    cur, nxt = chunks[i], chunks[i + 1]
    if cur.block == 'heading':
        return 'heading', HEADING_PAUSE_MS
    if not cur.last_in_block:
        return 'sentence', SENTENCE_PAUSE_MS
    if cur.block in ('list_item', 'table_row') and nxt.block == cur.block:
        return 'item', ITEM_PAUSE_MS
    return 'paragraph', PARAGRAPH_PAUSE_MS


def _frames_db(audio: np.ndarray) -> np.ndarray:
    n = int(SAMPLE_RATE * FRAME_MS / 1000)
    frames = len(audio) // n
    if frames == 0:
        return np.array([])
    x = audio[:frames * n].reshape(frames, n).astype(np.float64)
    return 20 * np.log10(np.maximum(np.sqrt(np.mean(x * x, axis=1)), 1e-10))


def _silence(ms: float) -> np.ndarray:
    return np.zeros(int(round(SAMPLE_RATE * ms / 1000)), dtype=np.float32)


def _fade(audio: np.ndarray, at_start: bool) -> np.ndarray:
    n = min(len(audio), int(SAMPLE_RATE * FADE_MS / 1000))
    if n == 0:
        return audio
    audio = audio.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    if at_start:
        audio[:n] *= ramp
    else:
        audio[-n:] *= ramp[::-1]
    return audio


def trim_edges(audio: np.ndarray) -> np.ndarray:
    """Cut the leading and trailing silence Kokoro adds to every clip."""
    loud = np.nonzero(_frames_db(audio) > SILENCE_DBFS)[0]
    if len(loud) == 0:
        return audio[:0]
    n = int(SAMPLE_RATE * FRAME_MS / 1000)
    return audio[loud[0] * n:(loud[-1] + 1) * n]


def _longest_silent_run(db: np.ndarray, lo: int, hi: int) -> tuple[int, int] | None:
    """Longest run of silent frames within frame range [lo, hi): (start, end) or None."""
    best, start = None, None
    for f in range(max(lo, 0), min(hi, len(db))):
        if db[f] <= SILENCE_DBFS:
            start = f if start is None else start
        elif start is not None:
            if best is None or f - start > best[1] - best[0]:
                best = (start, f)
            start = None
    if start is not None and (best is None or min(hi, len(db)) - start > best[1] - best[0]):
        best = (start, min(hi, len(db)))
    if best is None:
        return None
    # The window only locates the pause; take the whole silent run, or Kokoro's
    # silence outside the window would be left on both sides of ours.
    s, e = best
    while s > 0 and db[s - 1] <= SILENCE_DBFS:
        s -= 1
    while e < len(db) and db[e] <= SILENCE_DBFS:
        e += 1
    return s, e


def set_clause_pauses(audio: np.ndarray, tokens: list | None) -> tuple[np.ndarray, list[PauseMark]]:
    """Resize the pause at each , ; : — … inside a clip to COMMA_PAUSE_MS.

    Uses Kokoro's token timestamps to find each pause. Where Kokoro left no
    silence, the pause is inserted at the quietest point between the words.
    """
    if not tokens:
        return audio, []
    n = int(SAMPLE_RATE * FRAME_MS / 1000)
    slack = int(SEARCH_SLACK_MS / FRAME_MS)
    min_run = int(MIN_SILENT_RUN_MS / FRAME_MS)
    db = _frames_db(audio)
    spots = []  # (start_sample, end_sample) of the region to replace with the target pause
    for k, tok in enumerate(tokens):
        if tok.phonemes not in CLAUSE_PUNCT or k == 0 or k == len(tokens) - 1:
            continue
        # The pause sits between two spoken words; a closing quote after "…" is not one.
        before = next((t for t in reversed(tokens[:k]) if t.phonemes and t.end_ts is not None
                       and WORD_RE.search(t.text)), None)
        after = next((t for t in tokens[k + 1:] if t.phonemes and t.start_ts is not None
                      and WORD_RE.search(t.text)), None)
        if before is None or after is None:
            continue
        lo_s, hi_s = int(before.end_ts * SAMPLE_RATE), int(after.start_ts * SAMPLE_RATE)
        if hi_s <= lo_s:
            hi_s = lo_s + n
        run = _longest_silent_run(db, lo_s // n - slack, hi_s // n + slack)
        if run and run[1] - run[0] >= min_run:
            spots.append((run[0] * n, run[1] * n))
        else:
            # No pause from Kokoro: cut at the quietest frame between the words.
            lo_f, hi_f = max(lo_s // n, 0), min(max(hi_s // n, lo_s // n + 1), len(db))
            quiet = lo_f + int(np.argmin(db[lo_f:hi_f])) if hi_f > lo_f else lo_f
            spots.append((quiet * n, quiet * n))
    if not spots:
        return audio, []
    pieces, marks, pos = [], [], 0
    out_len = 0
    for start, end in sorted(set(spots)):
        if start < pos:
            continue
        piece = audio[pos:start]
        if end == start:  # inserted into sound: fade around the cut
            piece = _fade(piece, at_start=False)
        pieces.append(piece)
        out_len += len(piece)
        marks.append(PauseMark('comma', COMMA_PAUSE_MS, out_len / SAMPLE_RATE * 1000))
        pause = _silence(COMMA_PAUSE_MS)
        pieces.append(pause)
        out_len += len(pause)
        pos = end
        if end == start:
            audio = np.concatenate([audio[:pos], _fade(audio[pos:], at_start=True)])
    pieces.append(audio[pos:])
    return np.concatenate(pieces), marks


def shape_chunk(segments: list[tuple[np.ndarray, list | None, str]], pause_kind: str,
                pause_ms: int) -> tuple[np.ndarray, list[PauseMark]]:
    """Build one chunk's audio: set clause pauses, trim Kokoro's padding, add the pause after.

    segments: (audio, tokens, graphemes) for each Kokoro segment of the chunk, in order.
    Returns the audio and where each deliberate pause sits in it.
    """
    pieces: list[np.ndarray] = []
    marks: list[PauseMark] = []
    offset = 0
    for j, (audio, tokens, graphemes) in enumerate(segments):
        audio, clause_marks = set_clause_pauses(np.asarray(audio, dtype=np.float32), tokens)
        trimmed = trim_edges(audio)
        # Trimming moves the start, so shift each mark by what was cut in front.
        cut_front_ms = _leading_cut(audio) / SAMPLE_RATE * 1000
        offset_ms = offset / SAMPLE_RATE * 1000
        for m in clause_marks:
            at = m.at_ms - cut_front_ms
            if 0 <= at <= len(trimmed) / SAMPLE_RATE * 1000:
                marks.append(PauseMark(m.kind, m.target_ms, offset_ms + at))
        pieces.append(trimmed)
        offset += len(trimmed)
        if j < len(segments) - 1:  # Kokoro split a long chunk: pause like its punctuation says
            kind, ms = ('sentence', SENTENCE_PAUSE_MS) if graphemes.rstrip()[-1:] in SENTENCE_END \
                else ('comma', COMMA_PAUSE_MS)
            marks.append(PauseMark(kind, ms, offset / SAMPLE_RATE * 1000))
            gap = _silence(ms)
            pieces.append(gap)
            offset += len(gap)
    if pause_ms > 0:
        marks.append(PauseMark(pause_kind, pause_ms, offset / SAMPLE_RATE * 1000))
        pieces.append(_silence(pause_ms))
    if not pieces:
        return np.zeros(0, dtype=np.float32), []
    return np.concatenate(pieces), marks


def _leading_cut(audio: np.ndarray) -> int:
    """Number of samples trim_edges removes from the front."""
    loud = np.nonzero(_frames_db(audio) > SILENCE_DBFS)[0]
    n = int(SAMPLE_RATE * FRAME_MS / 1000)
    return int(loud[0] * n) if len(loud) else len(audio)
