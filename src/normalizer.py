"""Speech normalization: turn screen text into the words Kokoro should say.

The text on screen is never changed (R5); this module only builds the spoken
copy. It changes pronunciation, never meaning. Reading choices that had more
than one plausible answer were decided by Paul on 2026-10-17 (R6); see
_prosody-closing-report.md, "R6 decisions".

Entry point: prepare_speech(text) -> list[Spoken], used by the app's worker.
Things misaki already reads well are left to it: currency, ordinals, years,
percent, camelCase, "a.m.", "U.S.", "Ph.D.", "Mr.", "Mrs.", "etc.".
"""

import logging
import re
import unicodedata
from dataclasses import dataclass

from num2words import num2words

import emphasis
from text_processor import Chunk, split_chunks

logger = logging.getLogger(__name__)

# --- Block-level wording ---
CODE_BLOCK_NOTE = 'Code block skipped.'
TABLE_INTRO = 'Table.'
TABLE_ROW_LABEL = 'Row {n}.'
TABLE_ROWS_NOTE = '{n} rows.'
TABLE_MAX_READ_ROWS = 9          # up to 9 data rows are read; 10 or more are summarized
STRIKE_OPEN, STRIKE_CLOSE = 'begin strike', 'end strike'
END_PUNCT = '.!?…'

# --- Emoji names (fallback: the Unicode name) ---
EMOJI_NAMES = {
    '✅': 'check mark', '✔': 'check mark', '☑': 'check mark', '❌': 'cross mark', '✖': 'cross mark',
    '⚠': 'warning', '⏳': 'hourglass', '⌛': 'hourglass', '🚀': 'rocket', '👍': 'thumbs up',
    '👎': 'thumbs down', '🎉': 'party popper', '💡': 'light bulb', '🔥': 'fire', '📝': 'memo',
    '🔒': 'lock', '⭐': 'star', '❗': 'exclamation mark', '❓': 'question mark', '🛑': 'stop sign',
    '🔴': 'red circle', '🟢': 'green circle', '🟡': 'yellow circle', '📌': 'pin', '🐛': 'bug',
}
EMOJI_RE = re.compile('[←-⇿⌀-⏿①-⓿☀-➿⬀-⯿'
                      '\U0001f000-\U0001faff][️︎]?')
NOT_EMOJI = frozenset('→←⇒')   # arrows read as words, see SYMBOL_WORDS

# --- Units after a number ---
UNITS = {
    'mm': ('millimeter', 'millimeters'), 'cm': ('centimeter', 'centimeters'), 'km': ('kilometer', 'kilometers'),
    'm': ('meter', 'meters'), 'kg': ('kilogram', 'kilograms'), 'g': ('gram', 'grams'), 'mg': ('milligram', 'milligrams'),
    'TB': ('terabyte', 'terabytes'), 'GB': ('gigabyte', 'gigabytes'), 'MB': ('megabyte', 'megabytes'),
    'KB': ('kilobyte', 'kilobytes'), 'kB': ('kilobyte', 'kilobytes'),
    'GHz': ('gigahertz', 'gigahertz'), 'MHz': ('megahertz', 'megahertz'), 'kHz': ('kilohertz', 'kilohertz'),
    'Hz': ('hertz', 'hertz'), 'km/h': ('kilometer per hour', 'kilometers per hour'),
    'mph': ('mile per hour', 'miles per hour'), '°C': ('degree Celsius', 'degrees Celsius'),
    '°F': ('degree Fahrenheit', 'degrees Fahrenheit'), '°': ('degree', 'degrees'),
    'N·m': ('newton meter', 'newton meters'), 'Nm': ('newton meter', 'newton meters'),
    'V': ('volt', 'volts'), 'mA': ('milliamp', 'milliamps'), 'A': ('amp', 'amps'),
    'kW': ('kilowatt', 'kilowatts'), 'W': ('watt', 'watts'), 'dB': ('decibel', 'decibels'),
    'ms': ('millisecond', 'milliseconds'), 's': ('second', 'seconds'), 'sec': ('second', 'seconds'),
    'min': ('minute', 'minutes'), 'h': ('hour', 'hours'), 'hr': ('hour', 'hours'), 'hrs': ('hour', 'hours'),
    'px': ('pixel', 'pixels'),
}
# Units that are a single letter (or easily a word) need a space before them: "25 m", not "25m".
UNITS_NEED_SPACE = frozenset({'m', 'g', 'V', 'A', 'W', 'h', 's'})
# A unit followed by one of these is a plain quantity ("4 GB of RAM", "25 mm thick");
# followed by another lowercase word it's used as an adjective ("a 1.8 GB installer").
UNIT_PLURAL_NEXT = frozenset({
    'of', 'and', 'or', 'at', 'in', 'on', 'to', 'for', 'with', 'per', 'from', 'by', 'into', 'thick', 'wide',
    'long', 'tall', 'high', 'deep', 'away', 'ago', 'later', 'earlier', 'longer', 'shorter', 'faster',
    'slower', 'more', 'less', 'apart', 'each', 'total', 'so', 'is', 'are', 'was', 'were', 'be', 'been',
    'left', 'remaining', 'free', 'used', 'behind', 'ahead', 'before', 'after', 'too', 'than', 'then',
    'but', 'while', 'when', 'which', 'that', 'if', 'over', 'under', 'up', 'down', 'off', 'out', 'until',
})

# --- Abbreviations ---
ABBREVIATIONS = [  # (pattern, spoken); applied in order
    (r'\be\.g\.', 'for example'), (r'\bi\.e\.', 'that is'), (r'\bvs\.', 'versus'),
    (r'\bapprox\.', 'approximately'), (r'\bcf\.', 'compare'), (r'\bProf\.', 'Professor'),
    (r'\bJr\.', 'Junior'), (r'\bSr\.', 'Senior'), (r'\bNo\.(?=\s*\d)', 'number'),
    (r'\bVol\.(?=\s*\d)', 'volume'), (r'\bpp\.(?=\s*\d)', 'pages'), (r'\bp\.(?=\s*\d)', 'page'),
    (r'\bFigs?\.(?=\s*\d)', 'figure'), (r'#(?=\d)', 'number '),
]
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
          'October', 'November', 'December']
MONTH_ABBR = {m[:3]: m for m in MONTHS} | {'Sept': 'September'}
DAY_ABBR = {'Mon': 'Monday', 'Tue': 'Tuesday', 'Tues': 'Tuesday', 'Wed': 'Wednesday', 'Thu': 'Thursday',
            'Thur': 'Thursday', 'Thurs': 'Thursday', 'Fri': 'Friday', 'Sat': 'Saturday', 'Sun': 'Sunday'}
KEY_NAMES = {'ctrl': 'Control', 'control': 'Control', 'alt': 'Alt', 'shift': 'Shift', 'win': 'Windows',
             'cmd': 'Command', 'fn': 'Function', 'esc': 'Escape', 'del': 'Delete', 'tab': 'Tab', 'enter': 'Enter'}
# A two-part number after one of these is a version ("Python 3.11" -> "3 point 11").
VERSIONED_NAMES = frozenset({
    'version', 'release', 'python', 'pyinstaller', 'torch', 'pytorch', 'kokoro', 'misaki', 'cuda', 'node',
    'npm', 'pip', 'spacy', 'numpy', 'windows', 'macos', 'ios', 'android', 'java', 'claude', 'opus',
    'sonnet', 'haiku', 'fable', 'chrome', 'firefox', 'setup', 'espeak-ng', 'pytest', 'git',
})
FILE_EXTENSIONS = frozenset({
    'py', 'pyc', 'txt', 'md', 'json', 'jsonl', 'exe', 'bat', 'cmd', 'ps1', 'sh', 'spec', 'iss', 'log', 'pth',
    'pt', 'js', 'ts', 'tsx', 'jsx', 'html', 'css', 'yml', 'yaml', 'toml', 'cfg', 'ini', 'csv', 'wav', 'mp3',
    'dll', 'zip', 'docx', 'xlsx', 'pptx', 'pdf', 'png', 'jpg', 'svg', 'scad', 'stl', 'ico', 'lock', 'xml',
})
SYMBOL_WORDS = [  # (literal, spoken); longest first
    ('!=', ' not equal to '), ('<=', ' less than or equal to '), ('>=', ' greater than or equal to '),
    ('==', ' equals '), ('≤', ' less than or equal to '), ('≥', ' greater than or equal to '),
    ('≠', ' not equal to '), ('≈', ' approximately '), ('±', ' plus or minus '), ('×', ' times '),
    ('→', ' to '), ('⇒', ' to '), ('←', ' from '), ('©', ' copyright '), ('®', ' registered '),
    ('™', ' trademark '),
]
ROMAN_RE = re.compile(r'\b([A-Z][a-z]+) (X{0,3}(?:IX|IV|V?I{0,3}))\b(?!\w|\.\w)')
ROMAN_VALUES = {'I': 1, 'V': 5, 'X': 10}
# After these words a Roman numeral is a plain number ("World War II" -> "Two"), not a regnal one.
ROMAN_CARDINAL_AFTER = frozenset({
    'War', 'Part', 'Chapter', 'Phase', 'Type', 'Class', 'Volume', 'Act', 'Article', 'Step', 'Grade',
    'Level', 'Stage', 'Section', 'Appendix', 'Book', 'Round', 'Season', 'Episode', 'Tier', 'Category',
})

# --- Token patterns ---
LINK_RE = re.compile(r'!?\[([^\]]*)\]\(([^)]*)\)')
CODE_SPAN_RE = re.compile(r'`([^`]+)`')
STRIKE_RE = re.compile(r'~~(?=\S)(.+?)(?<=\S)~~')
EMPHASIS_RES = [
    re.compile(r'(?<![\w*])\*\*(?=\S)(.+?)(?<=\S)\*\*(?![\w*])'),
    re.compile(r'(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)'),
    re.compile(r'(?<![\w*])\*(?=[^\s*])([^*]+?)(?<=[^\s*])\*(?![\w*])'),
    re.compile(r'(?<!\w)_(?=[^\s_])([^_]+?)(?<=[^\s_])_(?!\w)'),
]
URL_RE = re.compile(r'\b(?:https?://|www\.)[^\s<>()\[\]`"]+')
EMAIL_RE = re.compile(r'\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b')
WIN_PATH_RE = re.compile(r'(?:\b[A-Za-z]:\\|%\w+%\\|\.\.\.\\|\b[\w.-]+\\)[^\s,;:()`"\']*')
POSIX_PATH_RE = re.compile(r'(?<![\w/])(?:~|\.{1,2})?/?[\w.@-]+(?:/[\w.@-]+)+/?'
                           r'|(?<![\w/])/[A-Za-z][\w.-]*'
                           r'|(?<![\w/])[\w.-]+/(?=[\s,;:)]|$)')
BARE_EXTENSION_RE = re.compile(r'(?<![\w.])\.([A-Za-z0-9]{1,5})\b(?![\w./-])')
HASH_RANGE_RE = re.compile(r'\b([0-9a-f]{7,40})\.\.\.?([0-9a-f]{7,40})\b')
HASH_RE = re.compile(r'\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b')
FILE_RE = re.compile(r'(?<![\w.])([\w-]+(?:\.[\w-]+)*)\.([A-Za-z0-9]{1,5})\b(?![\w-])')
DOTTED_CALL_RE = re.compile(r'\b([A-Za-z_]\w*)\.(?=[A-Za-z_]\w*\()')
EMPTY_PARENS_RE = re.compile(r'(?<=\w)\(\)')
SNAKE_RE = re.compile(r'\b_*([A-Za-z0-9]+(?:_+[A-Za-z0-9]+)+)_*\b|\b__?([A-Za-z0-9]+)_*\b(?=\W|$)')
CLI_FLAG_RE = re.compile(r'(?<!\S)(--?)(?=[A-Za-z])')
KEY_COMBO_RE = re.compile(r'\b((?:(?:Ctrl|Control|Alt|Shift|Win|Cmd|Fn)\+)+)(\w+)\b', re.IGNORECASE)
LOCAL_LABEL = r'(\+\w+(?:\.\w+)*)?'   # "+cu124"; a trailing sentence dot is not part of it
VERSION_V_RE = re.compile(r'\bv(\d+(?:\.\d+)+)' + LOCAL_LABEL + r'\b')
VERSION_3_RE = re.compile(r'(?<![\w.])(\d+\.\d+\.\d+(?:\.\d+)?)' + LOCAL_LABEL + r'(?![\w.]*\d)')
VERSION_2_RE = re.compile(r'\b([\w-]+) (\d+\.\d{2,})\b(?!\.\d)')
ISO_DATE_RE = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
US_DATE_RE = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b')
MONTH_DAY_RE = re.compile(r'\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?(?= \d)')
MONTH_NAME_DAY_RE = re.compile(r'\b(' + '|'.join(MONTHS) + r') (\d{1,2})\b(?![\d:]|st|nd|rd|th)')
DAY_NAME_RE = re.compile(r'\b(Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)\.(?=[\s,])')
# Two numbers with a colon that can't be a clock time read "by" (Paul, Phase 4 #27): the first
# is over 12 or the second over 59 ("16:9" -> "16 by 9", also "14:30" -> "14 by 30"). Three-part
# times ("17:06:27") and anything with a.m./p.m. stay clock times.
RATIO_RE = re.compile(r'(?<![\d:.])(\d{1,3}):(\d{1,3})(?![\d:])')
AMPM_AFTER_RE = re.compile(r'\s*[AaPp]\.?[Mm]\b')
RATIO_HOUR_MAX, RATIO_MINUTE_MAX = 12, 59
# A lone capital A next to an operator is a variable: say the letter, not the article "uh"
# (Paul, Phase 4 #31). misaki's [word](/phonemes/) markup sets the phonemes directly.
OPERATORS = r'[+\-−×*/=&<>≤≥≠]'
LETTER_A_RE = re.compile(r'(?<![\w\[.])A(?=\s?' + OPERATORS + r'\s?(?:[A-Z]\b|\d))'
                         r'|(?<=' + OPERATORS + r' )A\b(?![\w.\'])'
                         r'|(?<=' + OPERATORS + r')A\b(?![\w.\'])')
LETTER_A_SPOKEN = '[A](/ˈA/)'
TIME_RE = re.compile(r'(?<![\d:])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:])(\s*(?:[AaPp]\.?[Mm]\.?)(?![\w]))?')
AMPM_RE = re.compile(r'(?<=\d)\s?([AaPp])\.?[Mm]\b\.?')
PHONE_RE = re.compile(r'(?<![\d-])((?:\d{3}-)?\d{3}-\d{4})(?![\d-])')
FRACTION_RE = re.compile(r'(?<![\w/\[])(\d)/(\d{1,2})(?![\w/])')
COUNTER_RE = re.compile(r'\[(\d+)(?:–(\d+))?/(\d+)\]')
NUM_RANGE_RE = re.compile(r'(\d)\s?–\s?(?=\d)')
TILDE_RE = re.compile(r'~\s?(?=\d)')
UNIT_RE = re.compile(
    r'(?<![\w.])(\d+(?:[.,]\d+)?)(\s?)(' + '|'.join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
    + r')(?![\w/·°])')
ST_DR_RE = re.compile(r'\b(St|Dr)\.(?=\s)')


@dataclass
class Spoken:
    """One chunk as Kokoro should say it, with the screen text it came from."""
    text: str          # what is spoken
    source: str        # the screen text of this chunk
    block: str
    last_in_block: bool
    emphasis: tuple = ()   # (start, end) spans of `text` to emphasize (only with emphasis.EMPHASIS_ENABLED)


# --- Small helpers ---

def _words_for_number(n: int) -> str:
    return num2words(n).replace('-', ' ')


def _spell(token: str) -> str:
    """Character by character: "bba2200" -> "b b a 2 2 0 0"."""
    return ' '.join(token)


def _clean_name(part: str) -> str:
    """A path or identifier part read naturally: separators become spaces, dots become "dot"."""
    lead = 'dot ' if part.startswith('.') and len(part) > 1 else ''
    part = re.sub(r'[_-]+', ' ', part.lstrip('.') if lead else part)
    part = re.sub(r'(?<=\w)\.(?=\w)', ' dot ', part)
    return (lead + part).strip()


def _split_trailing(token: str) -> tuple[str, str]:
    """Separate sentence punctuation stuck to the end of a path or URL."""
    m = re.search(r'[.,;:!?]+$', token)
    return (token[:m.start()], m.group(0)) if m else (token, '')


def _ampm(matched: str, string: str, end: int) -> str:
    """ "a.m." -> "A M", keeping the final dot only where it also ends the sentence."""
    spoken = f'{matched.strip()[0].upper()} M'
    if matched.endswith('.'):
        rest = string[end:]
        if not rest.strip() or re.match(r'\s+[A-Z"“(]', rest):
            spoken += '.'
    return spoken


def _roman_to_int(s: str) -> int:
    total = 0
    for i, c in enumerate(s):
        v = ROMAN_VALUES[c]
        total += -v if i + 1 < len(s) and ROMAN_VALUES[s[i + 1]] > v else v
    return total


# --- Token readers ---

def _say_url(m: re.Match) -> str:
    url, trail = _split_trailing(m.group(0))
    url = re.sub(r'^https?://', '', url)
    url = url.rstrip('/')
    host, _, rest = url.partition('/')
    host, _, port = host.partition(':')
    spoken = ' dot '.join(_clean_name(p) for p in host.split('.'))
    if port:
        spoken += f' colon {port}'
    if rest:
        path, _, query = rest.partition('?')
        path, _, anchor = path.partition('#')
        if path:
            spoken += ' slash ' + ' slash '.join(_clean_name(p) for p in path.split('/') if p)
        if query:
            q = query.replace('=', ' equals ').replace('&', ' and ')
            spoken += ' question mark ' + _clean_name(q)
        if anchor:
            spoken += ' hash ' + _clean_name(anchor)
    return spoken + trail


def _say_email(m: re.Match) -> str:
    user, _, host = m.group(0).partition('@')
    return f"{_clean_name(user)} at {' dot '.join(host.split('.'))}"


def _say_windows_path(m: re.Match) -> str:
    path, trail = _split_trailing(m.group(0))
    parts = [p for p in path.split('\\') if p]
    spoken = []
    for i, p in enumerate(parts):
        if i == 0 and re.fullmatch(r'[A-Za-z]:', p):
            spoken.append(f'{p[0].upper()} drive')
        elif p == '...':
            continue
        elif re.fullmatch(r'%(\w+)%', p):
            name = p.strip('%')
            spoken.append('App Data' if name.upper() == 'APPDATA' else _clean_name(name))
        else:
            spoken.append(_clean_name(p))
    return ', '.join(spoken) + trail


def _looks_like_path(token: str) -> bool:
    """Tell "src/app.py" or "github.com/x" from prose like "install/reboot" or "km/h"."""
    if token.startswith('/') and len(token) > 1:
        return True
    return bool(re.search(r'[A-Za-z]\.[A-Za-z]', token) or '_' in token or token.endswith('/')
                or token.startswith(('~/', './', '../', '.')))


def _say_posix_path(m: re.Match) -> str:
    token, trail = _split_trailing(m.group(0))
    if not _looks_like_path(token):
        return m.group(0)
    lead = 'slash ' if token.startswith('/') else ''
    parts = [p for p in token.strip('/').split('/') if p]
    return lead + ' slash '.join('home' if p == '~' else _clean_name(p) for p in parts) + trail


def _say_file(m: re.Match) -> str:
    name, ext = m.group(1), m.group(2)
    if ext.lower() not in FILE_EXTENSIONS:
        return m.group(0)
    return f'{_clean_name(name)} dot {ext}'


def _say_snake(m: re.Match) -> str:
    return (m.group(1) or m.group(2)).replace('_', ' ')


def _say_key_combo(m: re.Match) -> str:
    keys = [k for k in m.group(1).split('+') if k] + [m.group(2)]
    return ' '.join(KEY_NAMES.get(k.lower(), k) for k in keys)


def _say_version(core: str, local: str | None) -> str:
    spoken = ' point '.join(core.split('.'))
    if local:
        label = re.sub(r'([A-Za-z]+)', lambda x: f' {_spell(x.group(1))} ', local[1:]).replace('.', ' point ')
        spoken += ' plus ' + re.sub(r'\s+', ' ', label).strip()
    return spoken


def _say_version_2(m: re.Match) -> str:
    if m.group(1).lower() not in VERSIONED_NAMES:
        return m.group(0)
    return f'{m.group(1)} {_say_version(m.group(2), None)}'


def _say_date(year: int, month: int, day: int, original: str) -> str:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return original
    return f'{MONTHS[month - 1]} {num2words(day, to="ordinal_num")}, {year}'


def _say_time(m: re.Match) -> str:
    hour, minute, second, ampm = int(m.group(1)), m.group(2), m.group(3), m.group(4)
    if hour > 24 or int(minute) > 59 or (second and int(second) > 59):
        return m.group(0)
    words = [_words_for_number(hour)]
    if minute == '00':
        if not ampm:
            words.append('hundred')
    elif minute.startswith('0'):
        words += ['oh', _words_for_number(int(minute))]
    else:
        words.append(_words_for_number(int(minute)))
    if second:
        if second.startswith('0'):
            words += ['oh', _words_for_number(int(second))]
        else:
            words.append(_words_for_number(int(second)))
    if ampm:
        words.append(_ampm(ampm, m.string, m.end()))
    return ' '.join(words)


def _say_ratio(m: re.Match) -> str:
    a, b = int(m.group(1)), int(m.group(2))
    if AMPM_AFTER_RE.match(m.string, m.end()) or (a <= RATIO_HOUR_MAX and b <= RATIO_MINUTE_MAX):
        return m.group(0)
    return f'{a} by {b}'


def _say_unit(m: re.Match) -> str:
    number, space, unit = m.group(1), m.group(2), m.group(3)
    if unit in UNITS_NEED_SPACE and not space:
        return m.group(0)
    one, many = UNITS[unit]
    before = m.string[:m.start()].split()
    if before and before[-1].lower() == 'about':
        before = before[:-1]
    after = re.match(r'\s+([a-z]+)\b', m.string[m.end():])
    adjective = ((before and before[-1].lower() in ('a', 'an', 'the'))
                 or (after is not None and after.group(1) not in UNIT_PLURAL_NEXT))
    return f'{number} {one if number == "1" or adjective else many}'


def _say_fraction(m: re.Match) -> str:
    a, b = int(m.group(1)), int(m.group(2))
    if not (0 < a < b <= 10):
        return m.group(0)
    if b == 2:
        return 'one half' if a == 1 else f'{_words_for_number(a)} halves'
    denom = 'quarter' if b == 4 else num2words(b, to='ordinal')
    return f"{_words_for_number(a)} {denom}{'s' if a > 1 else ''}"


def _say_counter(m: re.Match) -> str:
    a, b, total = m.group(1), m.group(2), m.group(3)
    return f'{a} to {b} of {total}' if b else f'{a} of {total}'


def _say_roman(m: re.Match) -> str:
    numeral = m.group(2)
    if len(numeral) < 2:
        return m.group(0)
    value = _roman_to_int(numeral)
    if not 2 <= value <= 39:
        return m.group(0)
    if m.group(1) in ROMAN_CARDINAL_AFTER:
        return f'{m.group(1)} {num2words(value).capitalize()}'
    return f'{m.group(1)} the {num2words(value, to="ordinal").capitalize()}'


def _say_st_dr(m: re.Match, text: str) -> str:
    """By context (R6): before a name, Saint / Doctor; after a name, Street / Drive."""
    abbr = m.group(1)
    after = text[m.end():].lstrip()
    before = text[:m.start()].rstrip()
    next_is_name = bool(re.match(r"[A-Z][\w']", after))
    prev_is_name = bool(re.search(r"[A-Z][\w']*$", before)) and not before.endswith(('.', '!', '?'))
    if next_is_name or not prev_is_name:
        return 'Saint' if abbr == 'St' else 'Doctor'
    return 'Street' if abbr == 'St' else 'Drive'


def _say_emoji(m: re.Match) -> str:
    ch = m.group(0)
    base = ch[0]
    if base in NOT_EMOJI:
        return ch
    name = EMOJI_NAMES.get(base)
    if name is None:
        try:
            name = unicodedata.name(base).lower()
        except ValueError:
            return ' '
        name = re.sub(r'\b(sign|symbol|heavy|white|black|large|medium|small)\b', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
    return f' {name} '


# --- Inline normalization ---

def normalize_inline(text: str, keep_emphasis: bool = False) -> str:
    """Normalize one chunk of prose for speech (markdown, symbols, numbers, paths).

    keep_emphasis: leave emphasis.OPEN/CLOSE markers around emphasized words.
    """
    # Markdown structure that wraps words. Code spans are protected while emphasis
    # is removed, so "`**`" or "_read_exactly" inside code isn't mistaken for markup.
    # With emphasis on, the emphasized words are kept between markers instead
    # (emphasis.OPEN/CLOSE); prepare_speech turns them into spans.
    text = LINK_RE.sub(lambda m: m.group(1), text)
    spans: list[str] = []
    text = CODE_SPAN_RE.sub(lambda m: spans.append(m.group(1)) or f'\x00{len(spans) - 1}\x00', text)
    text = STRIKE_RE.sub(lambda m: f'{STRIKE_OPEN} {m.group(1)} {STRIKE_CLOSE}', text)
    for _ in range(2):  # nested emphasis: ***x*** or **_x_**
        for pattern in EMPHASIS_RES:
            text = pattern.sub(rf'{emphasis.OPEN}\1{emphasis.CLOSE}' if keep_emphasis else r'\1', text)
    if keep_emphasis:
        text = emphasis.mark_caps(text)
    text = re.sub(r'\x00(\d+)\x00', lambda m: spans[int(m.group(1))], text)

    text = EMOJI_RE.sub(_say_emoji, text)

    # Addresses and code-like tokens, most specific first.
    text = URL_RE.sub(_say_url, text)
    text = EMAIL_RE.sub(_say_email, text)
    text = WIN_PATH_RE.sub(_say_windows_path, text)
    text = HASH_RANGE_RE.sub(lambda m: f'{_spell(m.group(1))} to {_spell(m.group(2))}', text)
    text = HASH_RE.sub(lambda m: _spell(m.group(0)), text)
    text = VERSION_V_RE.sub(lambda m: f'version {_say_version(m.group(1), m.group(2))}', text)
    text = VERSION_3_RE.sub(lambda m: _say_version(m.group(1), m.group(2)), text)
    text = VERSION_2_RE.sub(_say_version_2, text)
    text = POSIX_PATH_RE.sub(_say_posix_path, text)
    text = FILE_RE.sub(_say_file, text)
    text = BARE_EXTENSION_RE.sub(
        lambda m: f'dot {m.group(1)}' if m.group(1).lower() in FILE_EXTENSIONS else m.group(0), text)
    text = DOTTED_CALL_RE.sub(lambda m: f'{m.group(1)} dot ', text)
    text = EMPTY_PARENS_RE.sub('', text)
    text = SNAKE_RE.sub(_say_snake, text)
    text = KEY_COMBO_RE.sub(_say_key_combo, text)
    text = CLI_FLAG_RE.sub(lambda m: 'dash dash ' if m.group(1) == '--' else 'dash ', text)

    # Dates and times before plain numbers.
    text = ISO_DATE_RE.sub(lambda m: _say_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(0)), text)
    text = US_DATE_RE.sub(lambda m: _say_date(int(m.group(3)), int(m.group(1)), int(m.group(2)), m.group(0)), text)
    text = MONTH_DAY_RE.sub(lambda m: MONTH_ABBR[m.group(1)], text)
    text = MONTH_NAME_DAY_RE.sub(
        lambda m: f'{m.group(1)} {num2words(int(m.group(2)), to="ordinal_num")}' if 1 <= int(m.group(2)) <= 31
        else m.group(0), text)
    text = DAY_NAME_RE.sub(lambda m: DAY_ABBR[m.group(1)], text)
    text = RATIO_RE.sub(_say_ratio, text)
    text = TIME_RE.sub(_say_time, text)
    text = AMPM_RE.sub(lambda m: ' ' + _ampm(m.group(0), m.string, m.end()), text)

    # Numbers, units and symbols.
    text = PHONE_RE.sub(lambda m: ', '.join(_spell(g.replace('-', '')) for g in m.group(1).split('-')), text)
    text = COUNTER_RE.sub(_say_counter, text)
    text = FRACTION_RE.sub(_say_fraction, text)
    text = TILDE_RE.sub('about ', text)
    text = NUM_RANGE_RE.sub(r'\1 to ', text)
    text = UNIT_RE.sub(_say_unit, text)
    text = ROMAN_RE.sub(_say_roman, text)
    text = ST_DR_RE.sub(lambda m: _say_st_dr(m, text), text)
    for pattern, spoken in ABBREVIATIONS:
        text = re.sub(pattern, lambda m, s=spoken: s.capitalize() if m.start() == 0 else s, text)
    text = re.sub(r'(?i)\b(copyright)\s*©', r'\1', text)
    text = LETTER_A_RE.sub(LETTER_A_SPOKEN, text)
    for literal, spoken in SYMBOL_WORDS:
        text = text.replace(literal, spoken)
    text = re.sub(r'(?<=[\w)])\s*=\s*(?=[\w\[])', ' equals ', text)  # ")" / "[": after LETTER_A_SPOKEN
    text = text.replace('\\', ' ')

    # Tidy spacing left by the substitutions.
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([,.;:!?)\]”’])(?!\d)', r'\1', text)  # not " .75"
    text = re.sub(r'([(\[“‘])\s+', r'\1', text)
    return text.strip()


# --- Block-level normalization ---

def _with_end(text: str) -> str:
    """Make sure a heading or list item ends like a sentence, so Kokoro uses final intonation."""
    text = text.rstrip()
    core = text.rstrip(emphasis.MARKERS)   # an emphasis marker at the end isn't the last character
    closing, text = text[len(core):], core.rstrip()
    if text.endswith(':'):
        return text[:-1] + '.' + closing
    if text and text[-1] not in END_PUNCT and not re.search(r'[.!?…]["\'”’)]+$', text):
        return text + '.' + closing
    return text + closing


def _spoken(text: str, source: str, block: str, last_in_block: bool) -> Spoken:
    """A Spoken chunk, with any emphasis markers turned into spans of its text.

    A heading is bold as formatting, not emphasis, so it gets no spans.
    """
    plain, spans = emphasis.extract(text)
    return Spoken(plain, source, block, last_in_block, () if block == 'heading' else spans)


def _list_item(text: str, first: bool) -> str:
    """Drop a bullet; say a list number as a word with a pause ("1. Clone" -> "One. Clone")."""
    if first:
        m = re.match(r'^\s*(?:[-*+•]\s+|(\d{1,3})[.)]\s+)', text)
        if m:
            number = m.group(1)
            text = text[m.end():]
            if number:
                text = f'{num2words(int(number)).capitalize()}. {text}'
    return text


def _heading(text: str) -> str:
    """Strip "#" and bold; a numbered heading reads like a numbered list item."""
    text = re.sub(r'^\s*#{1,6}\s+', '', text)
    text = re.sub(r'^\*\*(\d{1,3}\.\s)', r'\1**', text)  # "**1. Installer**" -> "1. **Installer**"
    return _list_item(text, True) if re.match(r'\d{1,3}\.\s', text) else text


def _table(rows: list[Chunk], keep: bool) -> list[Spoken]:
    """Read a markdown table as Paul asked (R6): "Table.", header, then rows or a row count."""
    def cells(row: str) -> str:
        parts = [normalize_inline(c.strip(), keep) for c in row.strip().strip('|').split('|')]
        return ', '.join(p for p in parts if p)

    header, data = rows[0], rows[1:]
    out = [_spoken(f'{TABLE_INTRO} {_with_end(cells(header.text))}', header.text, 'table_row', not data)]
    if len(data) > TABLE_MAX_READ_ROWS:
        out[0].last_in_block = False
        out.append(Spoken(TABLE_ROWS_NOTE.format(n=len(data)), '\n'.join(r.text for r in data), 'table_row', True))
        return out
    for i, row in enumerate(data, 1):
        out.append(_spoken(f'{TABLE_ROW_LABEL.format(n=i)} {_with_end(cells(row.text))}', row.text, 'table_row',
                           i == len(data)))
    return out


def prepare_speech(text: str) -> list[Spoken]:
    """Split screen text into chunks and normalize each one for speech.

    The input string is not modified. Chunks that end up with no words are dropped.
    With emphasis.EMPHASIS_ENABLED, chunks also carry emphasis spans; a chunk keeps
    them only if its words are exactly what it says with emphasis off (a marker
    must never change a reading, e.g. "Louis **XVI**").
    """
    out = _prepare(text, keep=False)
    if not emphasis.EMPHASIS_ENABLED:
        return out
    marked = _prepare(text, keep=True)
    if len(marked) != len(out):
        logger.debug("Emphasis dropped: chunking changed for %.60s", text)
        return out
    return [m if m.text == o.text else o for m, o in zip(marked, out)]


def _prepare(text: str, keep: bool) -> list[Spoken]:
    chunks = split_chunks(text)
    out: list[Spoken] = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        if chunk.block == 'table_row':
            j = i
            while j < len(chunks) and chunks[j].block == 'table_row':
                j += 1
            out.extend(_table(chunks[i:j], keep))
            i = j
            continue
        if chunk.block == 'code':
            spoken = CODE_BLOCK_NOTE
        elif chunk.block == 'heading':
            spoken = _with_end(normalize_inline(_heading(chunk.text), keep))
        elif chunk.block == 'list_item':
            first = i == 0 or chunks[i - 1].last_in_block
            spoken = normalize_inline(_list_item(chunk.text, first), keep)
            spoken = _with_end(spoken) if chunk.last_in_block else spoken
        elif chunk.block == 'quote':
            spoken = normalize_inline(re.sub(r'^\s*>\s?', '', chunk.text), keep)
        else:
            spoken = normalize_inline(chunk.text, keep)
        if re.search(r'[^\W_]', spoken):
            out.append(_spoken(spoken, chunk.text, chunk.block, chunk.last_in_block))
        else:
            logger.debug("Dropped chunk with nothing to say: %.60s", chunk.text)
        i += 1
    return out
