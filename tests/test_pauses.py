"""Phase 3: pause shaping (src/pauses.py) on synthetic audio, no model needed.

Run: python -m pytest tests -q
"""

from dataclasses import dataclass

import numpy as np
import pytest

import harness  # puts src/ on sys.path
import pauses
from normalizer import Spoken

SR = pauses.SAMPLE_RATE


def tone(ms: float, freq: float = 220.0, level: float = 0.3) -> np.ndarray:
    t = np.arange(int(SR * ms / 1000)) / SR
    return (level * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def silence(ms: float) -> np.ndarray:
    return np.zeros(int(SR * ms / 1000), dtype=np.float32)


def silent_runs_ms(audio: np.ndarray) -> list[float]:
    """Lengths of internal silent runs, measured the same way the gate does."""
    db = pauses._frames_db(audio)
    runs, start = [], None
    loud = np.nonzero(db > pauses.SILENCE_DBFS)[0]
    for f in range(loud[0], loud[-1] + 1):
        if db[f] <= pauses.SILENCE_DBFS:
            start = f if start is None else start
        elif start is not None:
            runs.append((f - start) * pauses.FRAME_MS)
            start = None
    return runs


@dataclass
class Tok:
    text: str
    phonemes: str
    start_ts: float | None
    end_ts: float | None


def spoken(block: str, last: bool) -> Spoken:
    return Spoken('x.', 'x.', block, last)


def test_pause_after_kinds() -> None:
    chunks = [spoken('heading', True), spoken('paragraph', False), spoken('paragraph', True),
              spoken('list_item', True), spoken('list_item', True), spoken('paragraph', True)]
    kinds = [pauses.pause_after(chunks, i) for i in range(len(chunks))]
    assert kinds == [('heading', pauses.HEADING_PAUSE_MS), ('sentence', pauses.SENTENCE_PAUSE_MS),
                     ('paragraph', pauses.PARAGRAPH_PAUSE_MS), ('item', pauses.ITEM_PAUSE_MS),
                     ('paragraph', pauses.PARAGRAPH_PAUSE_MS), ('end', 0)]


def test_targets_ordered() -> None:
    assert (pauses.COMMA_PAUSE_MS < pauses.SENTENCE_PAUSE_MS < pauses.ITEM_PAUSE_MS
            <= pauses.PARAGRAPH_PAUSE_MS)


def test_trim_edges() -> None:
    audio = np.concatenate([silence(330), tone(500), silence(490)])
    trimmed = pauses.trim_edges(audio)
    assert abs(len(trimmed) / SR * 1000 - 500) <= pauses.FRAME_MS


@pytest.mark.parametrize('kokoro_pause_ms', [60, 90, 420])
def test_comma_pause_resized(kokoro_pause_ms: int) -> None:
    """Kokoro's own pause at a comma (any length) becomes COMMA_PAUSE_MS."""
    audio = np.concatenate([tone(400), silence(kokoro_pause_ms), tone(400)])
    toks = [Tok('one', 'wˈʌn', 0.0, 0.4), Tok(',', ',', 0.4, 0.4 + kokoro_pause_ms / 1000),
            Tok('two', 'tˈu', 0.4 + kokoro_pause_ms / 1000, 0.8 + kokoro_pause_ms / 1000)]
    out, marks = pauses.set_clause_pauses(audio, toks)
    assert [m.kind for m in marks] == ['comma']
    assert silent_runs_ms(out) == [pytest.approx(pauses.COMMA_PAUSE_MS, abs=pauses.FRAME_MS)]


def test_comma_pause_wider_than_timestamps() -> None:
    """Kokoro's pause often starts before the timestamped comma; all of it must be replaced."""
    audio = np.concatenate([tone(400), silence(360), tone(400)])
    toks = [Tok('one', 'wˈʌn', 0.0, 0.6), Tok(',', ',', 0.6, 0.7), Tok('two', 'tˈu', 0.7, 1.16)]
    out, _ = pauses.set_clause_pauses(audio, toks)
    assert silent_runs_ms(out) == [pytest.approx(pauses.COMMA_PAUSE_MS, abs=pauses.FRAME_MS)]


def test_no_clause_pause_before_closing_quote() -> None:
    """'…' followed only by a closing quote ends the clip; no comma pause goes there."""
    audio = np.concatenate([tone(400), silence(300)])
    toks = [Tok('dash', 'dˈæʃ', 0.0, 0.4), Tok('…', '…', 0.4, 0.5), Tok('"', '”', 0.5, 0.6)]
    out, marks = pauses.set_clause_pauses(audio, toks)
    assert marks == [] and len(out) == len(audio)


def test_comma_pause_inserted_when_missing() -> None:
    """No silence at the comma: the pause is inserted between the words."""
    audio = np.concatenate([tone(400), tone(400, freq=330)])
    toks = [Tok('one', 'wˈʌn', 0.0, 0.4), Tok(',', ',', 0.4, 0.4), Tok('two', 'tˈu', 0.4, 0.8)]
    out, _ = pauses.set_clause_pauses(audio, toks)
    runs = silent_runs_ms(out)
    assert len(runs) == 1 and abs(runs[0] - pauses.COMMA_PAUSE_MS) <= 2 * pauses.FRAME_MS + pauses.FADE_MS
    assert len(out) == len(audio) + int(SR * pauses.COMMA_PAUSE_MS / 1000)


def test_shape_chunk_trims_and_adds_pause() -> None:
    audio = np.concatenate([silence(330), tone(300), silence(80), tone(300), silence(490)])
    toks = [Tok('a', 'ˈA', 0.33, 0.63), Tok(',', ',', 0.63, 0.71), Tok('b', 'bˈi', 0.71, 1.01)]
    out, marks = pauses.shape_chunk([(audio, toks, 'a, b.')], 'sentence', pauses.SENTENCE_PAUSE_MS)
    assert [m.kind for m in marks] == ['comma', 'sentence']
    total_ms = len(out) / SR * 1000
    assert total_ms == pytest.approx(300 + pauses.COMMA_PAUSE_MS + 300 + pauses.SENTENCE_PAUSE_MS,
                                     abs=2 * pauses.FRAME_MS)
    assert marks[-1].at_ms == pytest.approx(total_ms - pauses.SENTENCE_PAUSE_MS, abs=1)


def test_shape_chunk_end_has_no_trailing_pause() -> None:
    out, marks = pauses.shape_chunk([(np.concatenate([silence(300), tone(200), silence(400)]), None, 'x.')],
                                    'end', 0)
    assert marks == [] and abs(len(out) / SR * 1000 - 200) <= pauses.FRAME_MS
