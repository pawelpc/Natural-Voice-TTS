"""Emphasis prototype (src/emphasis.py, Paul's Phase 4 note #13), off by default.

Normalizer and helper tests need no model. The Kokoro tests load the local
model (NVTTS_MODEL_DIR, this repo's dist/, or the main checkout's dist/) and
are skipped when there is none. Run: python -m pytest tests -q
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

import harness  # puts src/ on sys.path
import app
import emphasis
from normalizer import Spoken, prepare_speech


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(emphasis, 'EMPHASIS_ENABLED', True)


def spans_of(markdown: str) -> list[tuple[str, list[str]]]:
    return [(c.text, [c.text[a:b] for a, b in c.emphasis]) for c in prepare_speech(markdown)]


def test_off_by_default() -> None:
    assert emphasis.EMPHASIS_ENABLED is False
    assert spans_of('I said the **red** one, and Do NOT go.') == [('I said the red one, and Do NOT go.', [])]


@pytest.mark.parametrize('markdown, spoken, spans', [
    ('I said the **red** one, not the blue one.', 'I said the red one, not the blue one.', ['red']),
    ('This step is *really* important.', 'This step is really important.', ['really']),
    ('You must __back up your files__ first.', 'You must back up your files first.', ['back up your files']),
    ('Do NOT delete it.', 'Do NOT delete it.', ['NOT']),
    ("You DON'T need it.", "You DON'T need it.", ["DON'T"]),
    ('**Bottom line:** it runs the old code.', 'Bottom line: it runs the old code.', ['Bottom line']),
    ('***Very*** nested **_this_** one.', 'Very nested this one.', ['Very', 'this']),
    # Acronyms, file names, units after a number, Roman numerals: not emphasis.
    ('The API uses the GPU and CUDA, see SKILL.md.', 'The API uses the GPU and CUDA, see SKILL dot md.', []),
    ('The IT team in the US office.', 'The IT team in the US office.', []),
    ('Built at 4:46 PM, 8 GB free.', 'Built at four forty six P M, 8 gigabytes free.', []),
    ('Louis XVI was king.', 'Louis the Sixteenth was king.', []),
    # A line in capitals is shouting, not emphasis; markers inside code are code.
    ('WARNING DO NOT TOUCH', 'WARNING DO NOT TOUCH', []),
    ('Type `**bold**` here.', 'Type **bold** here.', []),
    # Longer than EMPHASIS_MAX_WORDS: read plain.
    ('**The fix is structural, not prompt based at all.** Done.', 'The fix is structural, not prompt based at all.', []),
])
def test_spans(enabled, markdown: str, spoken: str, spans: list[str]) -> None:
    assert spans_of(markdown)[0] == (spoken, spans)


def test_heading_gets_no_emphasis(enabled) -> None:
    assert spans_of('## **Install steps**') == [('Install steps.', [])]


def test_marker_never_changes_a_reading(enabled) -> None:
    # A marker inside "Louis **XVI**" stops the Roman-numeral rule: the chunk is read plain.
    assert spans_of('Louis **XVI** was king.') == [('Louis the Sixteenth was king.', [])]


@pytest.mark.parametrize('pid', [e['id'] for e in harness.load_manifest()])
def test_passages_say_the_same_words(monkeypatch, pid: str) -> None:
    text = next(e['text'] for e in harness.load_manifest() if e['id'] == pid)
    off = [(c.text, c.block) for c in prepare_speech(text)]
    monkeypatch.setattr(emphasis, 'EMPHASIS_ENABLED', True)
    on = prepare_speech(text)
    assert [(c.text, c.block) for c in on] == off
    for c in on:
        for a, b in c.emphasis:
            assert 0 <= a < b <= len(c.text) and len(c.text[a:b].split()) <= emphasis.EMPHASIS_MAX_WORDS


def test_passages_have_no_caps_emphasis(monkeypatch) -> None:
    # Every ALL-CAPS word in the passage set is an acronym or a file name.
    monkeypatch.setattr(emphasis, 'EMPHASIS_ENABLED', True)
    for e in harness.load_manifest():
        for c in prepare_speech(e['text']):
            for a, b in c.emphasis:
                word = c.text[a:b]
                assert not (word.isupper() and len(word) > 1), (e['id'], word)


def test_extract() -> None:
    o, c = emphasis.OPEN, emphasis.CLOSE
    assert emphasis.extract('plain') == ('plain', ())
    assert emphasis.extract(f'a {o}b{c} c') == ('a b c', ((2, 3),))
    assert emphasis.extract(f'{o}{o}x{c} y{c} z') == ('x y z', ((0, 3),))   # nested: outer span
    assert emphasis.extract(f'a {c}b {o}c') == ('a b c', ())                 # unbalanced: nothing
    assert emphasis.extract(f'{o} , {c}x') == (' , x', ())                   # no letters: nothing


@dataclass
class Tok:
    text: str
    phonemes: str
    whitespace: str = ' '


def test_phoneme_mask_lines_up_with_ids() -> None:
    tks = [Tok('Do', 'dˈu'), Tok('NOT', 'nˈɑt'), Tok('go', 'ɡˈO', ''), Tok('.', '.', '')]
    vocab = {c: 1 for c in 'dˈuɑnɡtO. '}
    ps = 'dˈu nˈɑt ɡˈO.'
    mask = emphasis.phoneme_mask(ps, tks, [False, True, False, False], vocab)
    assert len(mask) == len(ps)
    assert ''.join(c for c, f in zip(ps, mask) if f) == 'nˈɑt'
    # Two emphasized words: the space between them is emphasized too.
    mask = emphasis.phoneme_mask(ps, tks, [True, True, False, False], vocab)
    assert ''.join(c for c, f in zip(ps, mask) if f) == 'dˈu nˈɑt'
    assert emphasis.phoneme_mask('something else', tks, [False] * 4, vocab) is None


def test_token_flags() -> None:
    text = 'I said the red one.'
    tks = [Tok('I', 'I'), Tok('said', 's'), Tok('the', 'ð'), Tok('red', 'r'), Tok('one', 'w', ''), Tok('.', '.', '')]
    assert emphasis.token_flags(text, tks, [(11, 14)]) == [False, False, False, True, False, False]


def test_apply_gain_ramps_and_leaves_the_rest(monkeypatch) -> None:
    monkeypatch.setattr(emphasis, 'EMPHASIS_GAIN_DB', 6.0)
    frames = np.zeros(20)
    frames[8:12] = 1
    audio = np.full(20 * emphasis.FRAME_SAMPLES, 0.1, dtype=np.float32)
    out = emphasis.apply_gain(audio, frames)
    n = emphasis.FRAME_SAMPLES
    assert np.allclose(out[:6 * n], 0.1) and np.allclose(out[14 * n:], 0.1)
    assert out[10 * n] == pytest.approx(0.1 * 10 ** (6 / 20), rel=1e-3)
    assert np.all(np.abs(np.diff(out)) < 0.01)   # eases in and out, no step


class RecordingEngine:
    def __init__(self) -> None:
        self.kwargs: list[dict] = []

    def synthesize_segments(self, text, **kwargs):
        self.kwargs.append(kwargs)
        yield text, np.full(4800, 0.2, dtype=np.float32), []


def test_render_chunk_passes_spans_only_when_there_are_some() -> None:
    engine = RecordingEngine()
    chunks = [Spoken('plain words.', 'plain words.', 'paragraph', False),
              Spoken('the red one.', 'the **red** one.', 'paragraph', True, ((4, 7),))]
    app.render_chunk(engine, chunks, 0, 'af_heart', 1.0)
    app.render_chunk(engine, chunks, 1, 'af_heart', 1.0)
    assert engine.kwargs == [{'voice': 'af_heart', 'speed': 1.0},
                             {'voice': 'af_heart', 'speed': 1.0, 'emphasis_spans': ((4, 7),)}]


# --- With the Kokoro model ------------------------------------------------------

def _model_dir() -> str | None:
    candidates = [os.environ.get('NVTTS_MODEL_DIR', ''), str(harness.REPO_ROOT / 'dist' / 'NaturalVoiceTTS' / 'kokoro_model')]
    try:  # a git worktree: the model lives in the main checkout's dist/
        common = subprocess.run(['git', 'rev-parse', '--git-common-dir'], cwd=harness.REPO_ROOT,
                                capture_output=True, text=True, check=True).stdout.strip()
        candidates.append(str((harness.REPO_ROOT / common).resolve().parent / 'dist' / 'NaturalVoiceTTS' / 'kokoro_model'))
    except (OSError, subprocess.CalledProcessError):
        pass
    return next((c for c in candidates if c and (Path(c) / 'config.json').is_file()), None)


@pytest.fixture(scope='module')
def engine():
    model_dir = _model_dir()
    if model_dir is None:
        pytest.skip('no local Kokoro model')
    os.environ['NVTTS_MODEL_DIR'] = model_dir
    return harness.load_engine()


def _plain(pipeline, text):
    _, tokens = pipeline.g2p(text)
    (gs, ps, tks), = list(pipeline.en_tokenize(tokens))
    return tokens, ps, tks


def test_forward_without_emphasis_matches_kokoro(engine) -> None:
    pipeline = engine.get_pipeline()
    text = 'Please read the whole message before you reply.'
    _, ps, tks = _plain(pipeline, text)
    pack = pipeline.load_voice('af_heart')
    mask = emphasis.phoneme_mask(ps, tks, [False] * len(tks), pipeline.model.vocab)
    _, ours, frames = emphasis.forward(pipeline.model, ps, pack[len(ps) - 1], mask, 1.0)
    kokoro = pipeline.model(ps, pack[len(ps) - 1], 1.0, return_output=True).pred_dur
    assert ours.tolist() == kokoro.tolist()
    assert not frames.any()


def test_forward_lengthens_only_the_span(engine) -> None:
    pipeline = engine.get_pipeline()
    text = 'Please read the whole message before you reply.'
    tokens, ps, tks = _plain(pipeline, text)
    flags = emphasis.token_flags(text, tks, [(16, 21)])
    mask = emphasis.phoneme_mask(ps, tks, flags, pipeline.model.vocab)
    pack = pipeline.load_voice('af_heart')
    _, plain, _ = emphasis.forward(pipeline.model, ps, pack[len(ps) - 1], [False] * len(mask), 1.0)
    _, slow, frames = emphasis.forward(pipeline.model, ps, pack[len(ps) - 1], mask, 1.0)
    m = np.array([False, *mask, False])
    assert plain.numpy()[~m].tolist() == slow.numpy()[~m].tolist()          # the rest: same durations
    ratio = slow.numpy()[m].sum() / plain.numpy()[m].sum()
    assert ratio == pytest.approx(1 / emphasis.EMPHASIS_DURATION, abs=0.12)
    assert frames.sum() == slow.numpy()[m].sum()


def test_synthesize_segments_with_spans(engine) -> None:
    text = 'Please read the whole message before you reply.'
    segs = list(engine.synthesize_segments(text, voice='af_heart', speed=1.0, emphasis_spans=((16, 21),)))
    assert len(segs) == 1
    graphemes, audio, tokens = segs[0]
    assert graphemes == text and len(audio) > 24000
    whole = next(t for t in tokens if t.text == 'whole')
    assert whole.start_ts is not None and whole.end_ts > whole.start_ts
