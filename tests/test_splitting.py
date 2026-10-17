"""Phase 1 gate: sentence splitting (text_processor) and Kokoro's split pattern.

Run: python -m pytest tests -q
"""

import json
import re

import pytest

import harness  # puts src/ on sys.path
from text_processor import split_chunks, split_sentences

EXPECTED_SPLITS = json.loads((harness.PASSAGES_DIR / 'expected_splits.json').read_text(encoding='utf-8'))
PASSAGES = {e['id']: e['text'] for e in harness.load_manifest()}

CASES = [
    # H1 cases from Phase 0 (each was split wrongly before)
    ('Dr. Smith arrived late.', ['Dr. Smith arrived late.']),
    ('Use a short tool, e.g. this one, for the job.', ['Use a short tool, e.g. this one, for the job.']),
    ('The U.S. Army left the base.', ['The U.S. Army left the base.']),
    ('Mr. and Mrs. Jones came at 5 p.m. today.', ['Mr. and Mrs. Jones came at 5 p.m. today.']),
    ('J. R. R. Tolkien wrote the book.', ['J. R. R. Tolkien wrote the book.']),
    ('It ended... then it began again.', ['It ended... then it began again.']),
    # abbreviations that can end a sentence
    ('We met at 5 p.m. Then we left.', ['We met at 5 p.m.', 'Then we left.']),
    ('Bring pens, paper, etc. The rest is provided.', ['Bring pens, paper, etc.', 'The rest is provided.']),
    ('He moved to the U.S. The weather was better.', ['He moved to the U.S.', 'The weather was better.']),
    ('See No. 7 on p. 14 for more.', ['See No. 7 on p. 14 for more.']),
    ('It is due Jan. 5 at noon.', ['It is due Jan. 5 at noon.']),
    ('Prof. Lee vs. Dr. Kim, cf. Table 2.', ['Prof. Lee vs. Dr. Kim, cf. Table 2.']),
    # decimals, versions, file names (no split, and nothing breaks them apart)
    ('Pi is 3.14. Upgrade to v1.2.0 now.', ['Pi is 3.14.', 'Upgrade to v1.2.0 now.']),
    ('Open app.py. It runs.', ['Open app.py.', 'It runs.']),
    # ellipses and quotes
    ('Wait… what? "Go!" he shouted.', ['Wait… what?', '"Go!" he shouted.']),
    ('She said, "Yes." Then she left.', ['She said, "Yes."', 'Then she left.']),
    ('It ended... Then it began.', ['It ended...', 'Then it began.']),
    ('Was it worth it?! Absolutely.', ['Was it worth it?!', 'Absolutely.']),
    # initials vs variables
    ('Use A + B. Then add C.', ['Use A + B.', 'Then add C.']),
    ('Contact J. Smith today.', ['Contact J. Smith today.']),
    # markdown emphasis around the end punctuation
    ('1. **App still warming up.** After a reboot it waits.', ['1. **App still warming up.**', 'After a reboot it waits.']),
    # structure: hard wraps joined, list items and headings separate
    ('This line\nwraps in the middle.', ['This line wraps in the middle.']),
    ('Check:\n\n- one\n- two\n\n1. Clone\n2. Run', ['Check:', '- one', '- two', '1. Clone', '2. Run']),
    ('# Title\nBody text here.', ['# Title', 'Body text here.']),
    ('**1. Installer rebuilt** ✅\nThe file is ready.', ['**1. Installer rebuilt** ✅', 'The file is ready.']),
    ('| a | b |\n|---|---|\n| 1 | 2 |', ['| a | b |', '| 1 | 2 |']),
    ('> one\n>\n> two', ['> one', '> two']),
    ('Before.\n\n---\n\nAfter.', ['Before.', 'After.']),
    ('It is stale. ⚠️', ['It is stale. ⚠️']),
    ('Run this:\n\n```\na. b\n\nc\n```\n\nDone.', ['Run this:', '```\na. b\n\nc\n```', 'Done.']),
    ('Line one.\r\nLine two.', ['Line one.', 'Line two.']),
    ('', []),
]


@pytest.mark.parametrize('text,expected', CASES, ids=[c[0][:40] for c in CASES])
def test_split_cases(text: str, expected: list[str]) -> None:
    assert split_sentences(text) == expected


@pytest.mark.parametrize('pid', sorted(PASSAGES))
def test_passage_splits_match_expected(pid: str) -> None:
    """Every passage splits exactly as reviewed (tests/passages/expected_splits.json)."""
    assert split_sentences(PASSAGES[pid]) == EXPECTED_SPLITS[pid]


@pytest.mark.parametrize('pid', sorted(PASSAGES))
def test_no_words_lost(pid: str) -> None:
    """R4 at the split step: every word of the input is in the chunks, in order."""
    words_in = re.findall(r'\w+', PASSAGES[pid])
    words_out = re.findall(r'\w+', ' '.join(split_sentences(PASSAGES[pid])))
    assert words_out == words_in


def test_no_wordless_chunks() -> None:
    """A chunk without words would produce no audio and a 'skipped' warning."""
    for pid, text in PASSAGES.items():
        for chunk in split_sentences(text):
            assert re.search(r'\w', chunk), (pid, chunk)


def test_chunk_blocks() -> None:
    chunks = split_chunks('# Head\n\nOne. Two.\n\n- item\n\n```\ncode\n```')
    assert [(c.block, c.last_in_block) for c in chunks] == [
        ('heading', True), ('paragraph', False), ('paragraph', True), ('list_item', True), ('code', True)]


def test_kokoro_split_pattern_keeps_punctuation() -> None:
    """The pattern handed to KPipeline must not cut tokens or drop end punctuation (H2)."""
    import tts_engine
    for text in ['Are you sure?', 'Stop right there!', 'Pi is 3.5 or so.', 'Upgrade to v1.1.0 now.',
                 'Open app.py today.']:
        assert re.split(tts_engine.SPLIT_PATTERN, text) == [text]
