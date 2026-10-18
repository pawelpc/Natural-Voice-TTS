"""Pronunciation list: proper names and brands spoken with set phonemes.

Each entry maps a word to misaki phonemes, e.g. {"Cowork": "kˈO wˈɜɹk"}. Entries
come from the built-in list (assets/pronunciations.json) and the user's own list
(%APPDATA%\\NaturalVoiceTTS\\pronunciations.json); the user's entry wins. A file
is re-read when it changes, so an edit applies from the next message on.

apply() writes matching words in the spoken copy as misaki's phoneme markup,
"[Cowork](/kˈO wˈɜɹk/)". The screen text is never touched (R5). Matching is
whole-word, on the words about to be spoken (paths and code already read out),
in any case, unless the entry has a capital after its first letter ("iOS", "SQL"):
then only that exact spelling matches. A possessive "'s" is added to the phonemes.
"""

import json
import logging
import os
import re
import sys
import threading

from config import CONFIG_DIR

logger = logging.getLogger(__name__)

FILE_NAME = 'pronunciations.json'
if getattr(sys, 'frozen', False):
    # PyInstaller one-folder mode puts datas under _internal/
    BUILTIN_PATH = os.path.join(os.path.dirname(sys.executable), '_internal', 'assets', FILE_NAME)
else:
    BUILTIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', FILE_NAME)


def user_path() -> str | None:
    """The user's list; NVTTS_USER_LEXICON overrides it, and set empty turns it off (tests)."""
    override = os.environ.get('NVTTS_USER_LEXICON')
    if override is not None:
        return override or None
    return os.path.join(CONFIG_DIR, FILE_NAME)


# A key is one or more words (letters and digits, inner ' or -) separated by single spaces.
WORD = r"[^\W_](?:[\w'’-]*[^\W_])?"
KEY_RE = re.compile(rf'{WORD}(?: {WORD})*')
# Phonemes may not contain what would end misaki's markup early.
BAD_PHONEME_CHARS = frozenset('[]()/\n\r')
MARKUP_RE = re.compile(r'\[[^\]]*\]\(/[^)]*/\)')
STRESS_AND_LENGTH = 'ˈˌː'
SIBILANTS, VOICELESS = 'szʃʒʧʤ', 'ptkfθ'


def exact_case(key: str) -> bool:
    """An entry with a capital inside a word ("iOS", "SQL") matches only as written."""
    return any(c.isupper() for word in key.split(' ') for c in word[1:])


def _canonical(key: str) -> str:
    return key if exact_case(key) else key.lower()


def _possessive(phonemes: str) -> str:
    """Add "'s": "ᵻz" after a hissing sound, "s" after a voiceless one, else "z"."""
    last = phonemes.rstrip(STRESS_AND_LENGTH + ' ')[-1:]
    if last in SIBILANTS:
        return phonemes + 'ᵻz'
    return phonemes + ('s' if last in VOICELESS else 'z')


def parse(data, source: str) -> dict[str, tuple[str, str]]:
    """Valid entries of one list as {canonical key: (key, phonemes)}; bad ones are logged and skipped."""
    if not isinstance(data, dict):
        logger.warning("Pronunciation list %s is not a JSON object; ignored", source)
        return {}
    out = {}
    for key, phonemes in data.items():
        if not isinstance(phonemes, str):
            logger.warning("Pronunciation %r in %s is not a string; skipped", key, source)
            continue
        key, phonemes = ' '.join(key.split()), phonemes.strip()
        if phonemes.startswith('/') and phonemes.endswith('/') and len(phonemes) > 1:
            phonemes = phonemes[1:-1].strip()
        if not KEY_RE.fullmatch(key):
            logger.warning("Pronunciation key %r in %s is not a word; skipped", key, source)
        elif not phonemes or BAD_PHONEME_CHARS & set(phonemes):
            logger.warning("Pronunciation %r in %s has empty or unusable phonemes %r; skipped",
                           key, source, phonemes)
        else:
            out[_canonical(key)] = (key, phonemes)
    return out


def _read(path: str) -> dict[str, tuple[str, str]]:
    try:
        with open(path, encoding='utf-8-sig') as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logger.warning("Could not read pronunciation list %s: %s", path, e)
        return {}
    return parse(data, path)


class Lexicon:
    """A merged set of entries and the one regex that finds them."""

    def __init__(self, entries: dict[str, tuple[str, str]]) -> None:
        self.entries = entries
        self.pattern = None
        if not entries:
            return
        alternatives = []
        for key in sorted((k for k, _ in entries.values()), key=len, reverse=True):  # "Claude Code" first
            words = r'\s+'.join(re.escape(w) for w in key.split(' '))
            alternatives.append(words if exact_case(key) else f'(?i:{words})')
        self.pattern = re.compile(rf"(?<!\w)(?P<word>{'|'.join(alternatives)})(?P<poss>['’]s)?(?!\w)")

    def _markup(self, m: re.Match) -> str:
        word = ' '.join(m.group('word').split())
        entry = self.entries.get(word) or self.entries.get(word.lower())
        if entry is None:
            return m.group(0)
        phonemes = entry[1]
        if m.group('poss'):
            word, phonemes = word + m.group('poss'), _possessive(phonemes)
        return f'[{word}](/{phonemes}/)'

    def apply(self, text: str) -> str:
        if self.pattern is None:
            return text
        parts = MARKUP_RE.split(text)  # leave markup that is already there alone
        marks = MARKUP_RE.findall(text)
        out = [self.pattern.sub(self._markup, parts[0])]
        for mark, part in zip(marks, parts[1:]):
            out += [mark, self.pattern.sub(self._markup, part)]
        return ''.join(out)


_lock = threading.Lock()
_stamp: tuple | None = None
_current = Lexicon({})


def _mtime(path: str | None) -> float | None:
    try:
        return os.stat(path).st_mtime if path else None
    except OSError:
        return None


def current() -> Lexicon:
    """The merged lexicon, re-read when either file was added, changed or removed."""
    global _stamp, _current
    paths = (BUILTIN_PATH, user_path())
    stamp = (paths, tuple(_mtime(p) for p in paths))
    with _lock:
        if stamp != _stamp:
            merged = _read(paths[0])
            if paths[1]:
                merged.update(_read(paths[1]))
            _current, _stamp = Lexicon(merged), stamp
            logger.info("Pronunciation list: %d entries", len(merged))
        return _current


def apply(text: str) -> str:
    """Write listed words in spoken text as phoneme markup: "Cowork" -> "[Cowork](/kˈO wˈɜɹk/)"."""
    return current().apply(text)
