"""Phase 2 gate: speech normalization (src/normalizer.py).

Run: python -m pytest tests -q
"""

import re

import pytest

import harness  # puts src/ on sys.path
from normalizer import normalize_inline, prepare_speech
from text_processor import clean_text

EXPECTED_DIR = harness.PASSAGES_DIR / 'expected_spoken'
PASSAGES = {e['id']: e['text'] for e in harness.load_manifest()}
WORD_RE = re.compile(r'[^\W_]')

INLINE_CASES = [
    # R6 decisions (Paul, 2026-10-17)
    ('Dr. Smith lives on Oak Dr. near Main St. and St. Mary\'s.',
     "Doctor Smith lives on Oak Drive near Main Street and Saint Mary's."),
    ('~~old text~~ stays', 'begin strike old text end strike stays'),
    ('Done ✅ but ⚠️ check ⏳', 'Done check mark but warning check hourglass'),
    ('Visit https://github.com/pawelpc/Natural-Voice-TTS/releases today.',
     'Visit github dot com slash pawelpc slash Natural Voice TTS slash releases today.'),
    ('Open C:\\Users\\paul\\notes.txt now.', 'Open C drive, Users, paul, notes dot txt now.'),
    ('Copy it to %APPDATA%\\Claude\\skills\\ first.', 'Copy it to App Data, Claude, skills first.'),
    ('On 2026-10-17 and 10/24/2026 and Oct 3, 2026.',
     'On October 17th, 2026 and October 24th, 2026 and October 3rd, 2026.'),
    ('At 11:30, then 17:06:27, then 9:00 a.m. Then 2:30 PM.',
     'At eleven thirty, then seventeen oh six twenty seven, then nine A M. Then two thirty P M.'),
    # Phase 4 #27 (Paul's rule): two numbers with a colon read "by" when the first is over 12
    # or the second over 59; three-part times and a.m./p.m. stay clock times.
    ('The screen is 16:9, also 21:9 and 1:100.', 'The screen is 16 by 9, also 21 by 9 and 1 by 100.'),
    ('At 12:30 and 14:30, not 4:3.', 'At twelve thirty and 14 by 30, not 4:3.'),
    ('At 14:30 p.m. today.', 'At fourteen thirty P M today.'),
    # Phase 4 #31: a lone A next to an operator is the letter, via misaki's phoneme markup.
    ('Use A & B, not A + B, and A/B or A = 5.',
     'Use [A](/ˈA/) & B, not [A](/ˈA/) + B, and [A](/ˈA/)/B or [A](/ˈA/) equals 5.'),
    ('A cat sat in Plan A.', 'A cat sat in Plan A.'),
    ('Upgrade v1.2.0 and Python 3.11 and torch 2.6.0+cu124.',
     'Upgrade version 1 point 2 point 0 and Python 3 point 11 and torch 2 point 6 point 0 plus c u 124.'),
    ('Commit bba2200, range e3f15ec..bba2200.', 'Commit b b a 2 2 0 0, range e 3 f 1 5 e c to b b a 2 2 0 0.'),
    ('17:06:27 → 17:06:36', 'seventeen oh six twenty seven to seventeen oh six thirty six'),
    ('Press Ctrl+Win+T now.', 'Press Control Windows T now.'),
    ('x != y, a <= b, b >= c, 3 × 2, ~50% done', 'x not equal to y, a less than or equal to b, b greater than or '
     'equal to c, 3 times 2, about 50% done'),
    # markdown and code
    ('The **bold** and *italic* and __under__ words.', 'The bold and italic and under words.'),
    ('See [the README](https://example.com/readme) first.', 'See the README first.'),
    ('Call `split_sentences()` in `text_processor.py`.', 'Call split sentences in text processor dot py.'),
    ('Strip (`**`, `#`, backticks).', 'Strip (**, #, backticks).'),
    ('Use tts_engine.init() and `_read_exactly`.', 'Use tts engine dot init and read exactly.'),
    ('Run pip install -r requirements.txt --noconfirm', 'Run pip install dash r requirements dot txt dash dash noconfirm'),
    ('Set HF_HUB_OFFLINE=1 first.', 'Set HF HUB OFFLINE equals 1 first.'),
    ('Edit `.claude-plugin/plugin.json` and `.py` files.', 'Edit dot claude plugin slash plugin dot json and dot py files.'),
    ('Run /skill-creator now.', 'Run slash skill creator now.'),
    ('Email paul@example.com today.', 'Email paul at example dot com today.'),
    ('It uses install/reboot and km/h.', 'It uses install/reboot and km/h.'),
    # numbers, units, abbreviations
    ('It is 25 mm thick, a 1.8 GB file, 4 GB of RAM, ~12 min.',
     'It is 25 millimeters thick, a 1.8 gigabyte file, 4 gigabytes of RAM, about 12 minutes.'),
    ('A 5 V, 2 A supply at 20 °C, 12 N·m, 60 km/h, 1 s.',
     'A 5 volt, 2 amp supply at 20 degrees Celsius, 12 newton meters, 60 kilometers per hour, 1 second.'),
    ('The ratio was 0.5, not .75.', 'The ratio was 0.5, not .75.'),
    ('Pages 14–18, [1–20/20], 1/3 of them.', 'Pages 14 to 18, 1 to 20 of 20, one third of them.'),
    ('Call 555-0142.', 'Call 5 5 5, 0 1 4 2.'),
    ('Louis XVI, Henry VIII and World War II.', 'Louis the Sixteenth, Henry the Eighth and World War Two.'),
    ('Use e.g. this, i.e. that, vs. those, approx. 40, see No. 7, p. 3, pp. 4–5.',
     'Use for example this, that is that, versus those, approximately 40, see number 7, page 3, pages 4 to 5.'),
    ('Fig. 3 is #1 on Mon., Jan. 5th at 3pm.', 'Figure 3 is number 1 on Monday, January 5th at 3 P M.'),
    ('Copyright © 2026.', 'Copyright 2026.'),
    # left to misaki on purpose
    ('Costs were $4.99, 12.5%, 1st, the 1990s, Mr. and Mrs. Lee, Ph.D., U.S., etc.',
     'Costs were $4.99, 12.5%, 1st, the 1990s, Mr. and Mrs. Lee, Ph.D., U.S., etc.'),
]

BLOCK_CASES = [
    ('# Release Notes\n\n## 1. What changed', ['Release Notes.', 'One. What changed.']),
    ('Steps:\n\n1. Clone the repo\n2. Run it\n\n- a bullet', ['Steps:', 'One. Clone the repo.', 'Two. Run it.',
                                                             'a bullet.']),
    ('**1. Installer rebuilt** ✅\nIt is ready.', ['One. Installer rebuilt check mark.', 'It is ready.']),
    ('> Note: quoted.', ['Note: quoted.']),
    ('Run this:\n\n```python\nprint("hi")\n```\n\nDone.', ['Run this:', 'Code block skipped.', 'Done.']),
    ('| A | B |\n|---|---|\n| 1 | x |\n| 2 | y |',
     ['Table. A, B.', 'Row 1. 1, x.', 'Row 2. 2, y.']),
    ('| N | Sq |\n|---|---|\n' + ''.join(f'| {i} | {i * i} |\n' for i in range(1, 11)),
     ['Table. N, Sq.', '10 rows.']),
    ('---', []),
]


@pytest.mark.parametrize('text,expected', INLINE_CASES, ids=[c[0][:40] for c in INLINE_CASES])
def test_inline(text: str, expected: str) -> None:
    assert normalize_inline(text) == expected


@pytest.mark.parametrize('text,expected', BLOCK_CASES, ids=[c[0][:30] for c in BLOCK_CASES])
def test_blocks(text: str, expected: list[str]) -> None:
    assert [s.text for s in prepare_speech(text)] == expected


@pytest.mark.parametrize('pid', sorted(PASSAGES))
def test_passage_matches_expected(pid: str) -> None:
    """Gate: every passage's spoken text matches its reviewed expected-output file."""
    expected = (EXPECTED_DIR / f'{pid}.txt').read_text(encoding='utf-8').splitlines()
    assert [s.text for s in prepare_speech(PASSAGES[pid])] == expected


@pytest.mark.parametrize('pid', sorted(PASSAGES))
def test_screen_text_unchanged(pid: str) -> None:
    """R5: preparing speech never alters the screen text, and every spoken chunk comes from it."""
    text = PASSAGES[pid]
    before = str(text)
    spoken = prepare_speech(text)
    assert text == before
    screen = re.sub(r'\s+', ' ', clean_text(text))
    for s in spoken:
        for line in s.source.split('\n'):
            assert re.sub(r'\s+', ' ', line).strip() in screen, (pid, s.source)


@pytest.fixture(scope='module')
def g2p():
    """misaki G2P exactly as Kokoro uses it (no model, CPU only)."""
    import tts_engine  # noqa: F401  sets the espeak-ng paths
    from kokoro import KPipeline
    return KPipeline(lang_code=tts_engine.DEFAULT_LANG, repo_id='hexgrad/Kokoro-82M', model=False).g2p


@pytest.mark.parametrize('pid', sorted(PASSAGES))
def test_every_word_gets_phonemes(g2p, pid: str) -> None:
    """R4: no word in the spoken text is silently dropped by misaki."""
    for s in prepare_speech(PASSAGES[pid]):
        _, tokens = g2p(s.text)
        silent = [t.text for t in tokens if WORD_RE.search(t.text) and not t.phonemes]
        assert not silent, (pid, s.text, silent)
