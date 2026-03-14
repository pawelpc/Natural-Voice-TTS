"""Text preprocessing: cleanup and sentence splitting for TTS pipeline."""

import re
import logging

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Strip excess whitespace and normalize line endings."""
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Collapse multiple spaces (but preserve newlines)
    text = re.sub(r'[^\S\n]+', ' ', text)
    # Collapse 3+ newlines into 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-sized chunks for TTS processing.

    Splits on sentence-ending punctuation and paragraph breaks.
    Returns non-empty stripped strings.
    """
    text = clean_text(text)
    if not text:
        return []

    # Split on sentence boundaries: period, exclamation, question mark, or double newline
    parts = re.split(r'(?<=[.!?])\s+|\n{2,}', text)

    # Filter empty strings and strip whitespace
    sentences = [s.strip() for s in parts if s and s.strip()]
    return sentences


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
