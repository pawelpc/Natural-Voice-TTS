"""Text preprocessing: cleanup and sentence splitting for TTS pipeline.

Splitting works in two steps:
1. Group lines into blocks: fenced code, headings, table rows, rules, list
   items, quotes and paragraphs. Hard-wrapped lines (PDF, email) are joined.
2. Split each prose block into sentences. Abbreviations, initials, decimals,
   versions and ellipses inside a sentence are not treated as sentence ends.
   When a case is ambiguous the splitter keeps the text together: Kokoro reads
   an inner period correctly, while a wrong split adds a full sentence pause.
"""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# --- Block structure (markdown-aware) ---
FENCE_RE = re.compile(r'^\s*(```|~~~)')
HEADING_RE = re.compile(r'^\s{0,3}#{1,6}\s')
RULE_RE = re.compile(r'^\s{0,3}(?:[-*_]\s*){3,}$')
TABLE_ROW_RE = re.compile(r'^\s*\|')
LIST_ITEM_RE = re.compile(r'^\s*(?:[-*+•]|\d{1,3}[.)])\s+')
QUOTE_RE = re.compile(r'^\s*>')
EMPTY_QUOTE_RE = re.compile(r'^\s*>\s*$')               # paragraph break inside a quote
BOLD_LINE_RE = re.compile(r'^\s*\*\*[^*]+\*\*[^\w*]*$')  # "**1. Installer rebuilt** ✅" acts as a heading

# Blocks spoken as one chunk, never split into sentences.
ATOMIC_BLOCKS = frozenset({'code', 'heading', 'table_row', 'rule'})

# --- Sentence boundaries ---
# End punctuation, then closing quotes/brackets/markdown emphasis, then whitespace.
BOUNDARY_RE = re.compile(r'([.!?…]+)(["\'”’)\]*_`]*)(\s+)')
OPENERS = '"\'“‘([*_`'
DOTTED_ACRONYM_RE = re.compile(r'(?:[A-Za-z]\.)+[A-Za-z]')  # "U.S", "p.m" (final dot not included)
ENUMERATOR_RE = re.compile(r'\d{1,3}')                      # "**1." at the start of a block
OPERATOR_TOKENS = frozenset('+-−×*/=&<>≤≥')                  # "A + B." is a variable, not an initial
HAS_WORD_RE = re.compile(r'\w')

# Never end a sentence: titles and Latin abbreviations that always lead into more text.
NON_FINAL_ABBREVIATIONS = frozenset({
    'mr', 'mrs', 'ms', 'mx', 'dr', 'prof', 'st', 'mt', 'rev', 'hon', 'gen', 'col', 'capt',
    'cmdr', 'lt', 'sgt', 'gov', 'sen', 'rep', 'e.g', 'i.e', 'vs', 'cf', 'approx', 'viz',
})
# Don't end a sentence when a number follows ("No. 7", "Fig. 3", "Jan. 5").
BEFORE_NUMBER_ABBREVIATIONS = frozenset({
    'no', 'nos', 'vol', 'vols', 'p', 'pp', 'fig', 'figs', 'eq', 'eqs', 'ch', 'sec', 'art', 'ref',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec',
})
# Often end a sentence, often don't ("etc.", "Inc.", "U.S.", "p.m.", initials). Split
# only when the next word is a typical sentence opener.
MAY_END_ABBREVIATIONS = frozenset({
    'etc', 'inc', 'ltd', 'co', 'corp', 'jr', 'sr', 'al', 'mon', 'tue', 'tues', 'thu', 'thur',
    'thurs', 'fri',
})
SENTENCE_OPENERS = frozenset({
    'a', 'an', 'the', 'this', 'that', 'these', 'those', 'it', "it's", 'its', 'i', "i'm", "i'll",
    "i've", 'we', "we're", 'you', 'he', 'she', 'they', "they're", 'there', "there's", 'then',
    'but', 'and', 'so', 'or', 'if', 'when', 'while', 'after', 'before', 'in', 'on', 'at', 'for',
    'to', 'with', 'as', 'my', 'our', 'your', 'his', 'her', 'their', 'what', 'why', 'how', 'who',
    'where', 'which', 'now', 'also', 'however', 'still', 'yet', 'all', 'some', 'each', 'both',
    'one', 'next', 'finally', 'here', 'please', 'see', 'note',
})


@dataclass
class Chunk:
    """One piece of text spoken as a unit, with the block it came from."""
    text: str
    block: str            # paragraph, list_item, quote, heading, table_row, rule, code
    last_in_block: bool   # True for the final chunk of its block


def clean_text(text: str) -> str:
    """Strip excess whitespace and normalize line endings."""
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Collapse multiple spaces (but preserve newlines)
    text = re.sub(r'[^\S\n]+', ' ', text)
    # Collapse 3+ newlines into 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _blocks(text: str) -> list[tuple[str, str]]:
    """Group cleaned text into (block_kind, text) pairs, in order."""
    blocks: list[tuple[str, str]] = []
    lines: list[str] = []
    kind: str | None = None
    fence: list[str] | None = None

    def flush() -> None:
        nonlocal lines, kind
        if lines:
            blocks.append((kind or 'paragraph', ' '.join(line.strip() for line in lines)))
        lines, kind = [], None

    for line in text.split('\n'):
        if fence is not None:
            fence.append(line)
            if FENCE_RE.match(line):
                blocks.append(('code', '\n'.join(fence)))
                fence = None
            continue
        if FENCE_RE.match(line):
            flush()
            fence = [line]
        elif not line.strip():
            flush()
        elif HEADING_RE.match(line) or BOLD_LINE_RE.match(line):
            flush()
            blocks.append(('heading', line.strip()))
        elif RULE_RE.match(line):
            flush()
            blocks.append(('rule', line.strip()))
        elif TABLE_ROW_RE.match(line):
            flush()
            blocks.append(('table_row', line.strip()))
        elif LIST_ITEM_RE.match(line):
            flush()
            lines, kind = [line], 'list_item'
        elif EMPTY_QUOTE_RE.match(line):
            flush()
        elif QUOTE_RE.match(line):
            if kind != 'quote':
                flush()
                kind = 'quote'
            lines.append(line)
        else:
            if kind == 'quote':
                flush()
            kind = kind or 'paragraph'
            lines.append(line)
    if fence is not None:  # unclosed fence: keep what we have
        blocks.append(('code', '\n'.join(fence)))
    flush()
    return blocks


def _is_sentence_end(before: str, punct: str, after: str) -> bool:
    """Decide whether end punctuation at this point closes a sentence.

    before: text up to the punctuation; punct: the punctuation run;
    after: text following the whitespace.
    """
    nxt = after.lstrip(OPENERS)
    if not nxt:
        return True
    if nxt[0].islower():
        return False
    if punct != '.':
        return True
    tokens = before.split()
    raw_word = tokens[-1].lstrip(OPENERS) if tokens else ''
    word = raw_word.lower()
    if len(tokens) == 1 and ENUMERATOR_RE.fullmatch(raw_word):
        return False
    if word in NON_FINAL_ABBREVIATIONS:
        return False
    if word in BEFORE_NUMBER_ABBREVIATIONS and nxt[0].isdigit():
        return False
    is_initial = (len(raw_word) == 1 and raw_word.isupper()
                  and not (len(tokens) > 1 and tokens[-2] in OPERATOR_TOKENS))
    may_end = (word in MAY_END_ABBREVIATIONS
               or DOTTED_ACRONYM_RE.fullmatch(raw_word) is not None
               or is_initial)
    if may_end:
        next_word = re.match(r"[\w']+", nxt)
        return next_word is not None and next_word.group(0).lower() in SENTENCE_OPENERS
    return True


def _split_prose(text: str, skip: int = 0) -> list[str]:
    """Split a prose block into sentences, ignoring boundaries before index `skip`."""
    sentences = []
    start = 0
    for m in BOUNDARY_RE.finditer(text, skip):
        if _is_sentence_end(text[start:m.start(1)], m.group(1), text[m.end():]):
            sentences.append(text[start:m.end(2)].strip())
            start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    # A piece with no words ("⚠️") belongs to the sentence before it.
    merged: list[str] = []
    for s in sentences:
        if merged and not HAS_WORD_RE.search(s):
            merged[-1] = f'{merged[-1]} {s}'
        else:
            merged.append(s)
    return merged


def split_chunks(text: str) -> list[Chunk]:
    """Split text into speakable chunks, keeping the block kind of each.

    Every word of the input appears in the output, in order. Blocks with no
    words (a "---" rule, a table's "|---|" row, a bare ">") are not returned,
    so the worker never gets a chunk that produces no audio.
    """
    text = clean_text(text)
    if not text:
        return []
    chunks: list[Chunk] = []
    for kind, block in _blocks(text):
        if not HAS_WORD_RE.search(block):
            continue
        if kind in ATOMIC_BLOCKS:
            pieces = [block]
        else:
            marker = LIST_ITEM_RE.match(block) if kind == 'list_item' else None
            pieces = _split_prose(block, marker.end() if marker else 0)
        for i, piece in enumerate(pieces):
            chunks.append(Chunk(piece, kind, i == len(pieces) - 1))
    return chunks


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-sized chunks for TTS processing.

    Returns non-empty stripped strings. See split_chunks() for the rules.
    """
    return [c.text for c in split_chunks(text)]


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    sample = """
    Hello there! This is a test of the sentence splitter.
    It should handle multiple sentences. Even ones with questions?

    New paragraphs should also cause splits.
    And exclamation marks too! Let's see how it works.

    Final paragraph with some trailing whitespace.
    """

    logger.info("Input text:\n%s", sample)
    sentences = split_sentences(sample)
    logger.info("Split into %d sentences:", len(sentences))
    for i, s in enumerate(sentences, 1):
        logger.info("  [%d] %s", i, s)
