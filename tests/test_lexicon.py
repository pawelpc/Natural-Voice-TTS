"""Pronunciation list (src/lexicon.py): names and brands spoken with set phonemes.

Run: python -m pytest tests -q
"""

import json
import os

import pytest

import harness  # puts src/ on sys.path; turns the user's own list off
import lexicon
from normalizer import normalize_inline, prepare_speech

COWORK = '[Cowork](/kˈO wˈɜɹk/)'


def make(entries: dict) -> lexicon.Lexicon:
    return lexicon.Lexicon(lexicon.parse(entries, 'test'))


# --- The built-in list, through the normalizer ---

@pytest.mark.parametrize('text,expected', [
    # Paul, Phase 4 listening check: "Cowork" is "Co work", not "Cow ork".
    ("That's why Cowork never sees it.", f"That's why {COWORK} never sees it."),
    ('Open cowork and COWORK.', 'Open [cowork](/kˈO wˈɜɹk/) and [COWORK](/kˈO wˈɜɹk/).'),
    ("Cowork's skills (in Cowork).", f"[Cowork's](/kˈO wˈɜɹks/) skills (in {COWORK})."),
    ('Run /create-cowork-plugin now.', 'Run slash create [cowork](/kˈO wˈɜɹk/) plugin now.'),
    ('**Cowork:** done', f'{COWORK}: done'),
    # whole words only
    ('Coworking with a coworker in MyCowork or Cowork2.', 'Coworking with a coworker in MyCowork or Cowork2.'),
])
def test_builtin_through_normalizer(text: str, expected: str) -> None:
    assert normalize_inline(text) == expected


def test_heading_and_table_cells() -> None:
    spoken = [s.text for s in prepare_speech('# Cowork\n\n| App | Use |\n|---|---|\n| Cowork | skills |')]
    assert spoken == [f'{COWORK}.', 'Table. App, Use.', f'Row 1. {COWORK}, skills.']


def test_with_emphasis(monkeypatch) -> None:
    """Emphasis markers around a listed word: the markup is written and the span covers it."""
    import emphasis
    monkeypatch.setattr(emphasis, 'EMPHASIS_ENABLED', True)
    [s] = prepare_speech('The **Cowork** skills work.')
    assert s.text == f'The {COWORK} skills work.'
    assert [s.text[a:b] for a, b in s.emphasis] == ['Cowork](/kˈO wˈɜɹk']


def test_screen_text_unchanged() -> None:
    """R5: the markup is only in the spoken copy."""
    text = 'Cowork reads skills.'
    spoken = prepare_speech(text)
    assert text == 'Cowork reads skills.'
    assert spoken[0].source == 'Cowork reads skills.'
    assert spoken[0].text == f'{COWORK} reads skills.'


# --- Matching rules ---

def test_case_rules() -> None:
    lex = make({'cowork': 'kˈO wˈɜɹk', 'iOS': 'ˌIˌOˈɛs'})
    assert lex.apply('Cowork on iOS, not ios or IOS.') == (
        '[Cowork](/kˈO wˈɜɹk/) on [iOS](/ˌIˌOˈɛs/), not ios or IOS.')


def test_longest_entry_first_and_spaces() -> None:
    lex = make({'Claude': 'klˈɔd', 'Claude Code': 'klˈɔd kˈOd'})
    assert lex.apply('Use Claude  Code and Claude.') == 'Use [Claude Code](/klˈɔd kˈOd/) and [Claude](/klˈɔd/).'


@pytest.mark.parametrize('phonemes,expected', [
    ('mˈɑɹk', 'mˈɑɹks'), ('bˈɑb', 'bˈɑbz'), ('bˈɔs', 'bˈɔsᵻz'), ('ʤˈʌʤ', 'ʤˈʌʤᵻz'), ('ɹˈA', 'ɹˈAz'),
    ('smˈɪθ', 'smˈɪθs'),
])
def test_possessive(phonemes: str, expected: str) -> None:
    """Same endings misaki gives "Mark's", "Bob's", "boss's", "judge's", "Ray's", "Smith's"."""
    assert make({'Name': phonemes}).apply("Name's") == f"[Name's](/{expected}/)"


def test_existing_markup_left_alone() -> None:
    lex = make({'A': 'ˈɑ', 'B': 'bˈi'})
    assert lex.apply('[A](/ˈA/) + B') == '[A](/ˈA/) + [B](/bˈi/)'


def test_entries_are_checked() -> None:
    entries = lexicon.parse({
        'Good': '/ɡˈʊd/',        # slashes are optional
        'Bad key!': 'bˈæd',
        'Number': 7,
        'Breaks': 'bɹˈAk)s',      # would end the markup early
        'Empty': '  ',
    }, 'test')
    assert entries == {'good': ('Good', 'ɡˈʊd')}
    assert lexicon.parse(['not', 'an', 'object'], 'test') == {}


# --- Files ---

def test_user_list_wins_and_is_reread(tmp_path, monkeypatch) -> None:
    builtin, user = tmp_path / 'builtin.json', tmp_path / 'user.json'
    builtin.write_text(json.dumps({'Cowork': 'kˈO wˈɜɹk', 'Kokoro': 'kˈOkəɹO'}), encoding='utf-8')
    monkeypatch.setattr(lexicon, 'BUILTIN_PATH', str(builtin))
    monkeypatch.setenv('NVTTS_USER_LEXICON', str(user))
    assert lexicon.apply('Kokoro in Cowork') == '[Kokoro](/kˈOkəɹO/) in [Cowork](/kˈO wˈɜɹk/)'

    user.write_text(json.dumps({'cowork': 'kˌOwˈɜɹk'}), encoding='utf-8')
    assert lexicon.apply('Kokoro in Cowork') == '[Kokoro](/kˈOkəɹO/) in [Cowork](/kˌOwˈɜɹk/)'

    user.write_text('{"Cowork": "kˈO wˈɜɹk"', encoding='utf-8')  # broken JSON: the user list is ignored
    stat = user.stat()
    os.utime(user, (stat.st_atime, stat.st_mtime + 5))
    assert lexicon.apply('Kokoro in Cowork') == '[Kokoro](/kˈOkəɹO/) in [Cowork](/kˈO wˈɜɹk/)'

    user.unlink()
    builtin.unlink()
    assert lexicon.apply('Kokoro in Cowork') == 'Kokoro in Cowork'


def test_tests_ignore_the_users_list() -> None:
    assert os.environ['NVTTS_USER_LEXICON'] == ''
    assert lexicon.user_path() is None


def _kokoro_vocab() -> set[str] | None:
    import tts_engine
    model_dir = tts_engine._get_bundled_model_dir()
    path = os.path.join(model_dir, 'config.json') if model_dir else None
    if path is None:
        try:
            from huggingface_hub import hf_hub_download
            path = hf_hub_download('hexgrad/Kokoro-82M', 'config.json', local_files_only=True)
        except Exception:
            return None
    with open(path, encoding='utf-8') as f:
        return set(json.load(f)['vocab'])


def test_builtin_list_uses_kokoro_phonemes() -> None:
    """Every built-in entry loads, and uses only phonemes Kokoro has (others would be dropped silently)."""
    with open(lexicon.BUILTIN_PATH, encoding='utf-8') as f:
        raw = json.load(f)
    entries = lexicon.parse(raw, 'builtin')
    assert len(entries) == len(raw)
    vocab = _kokoro_vocab()
    if vocab is None:
        pytest.skip('Kokoro config.json not found')
    bad = {key: set(p) - vocab - {' '} for key, p in entries.values() if set(p) - vocab - {' '}}
    assert not bad
