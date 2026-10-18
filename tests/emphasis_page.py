"""Write tests/emphasis/listen.html: a local page to listen to the emphasis renders.

Reads tests/emphasis/emphasis.json (probe_emphasis.py) and the passages rendered
with render_passages.py into tests/emphasis/passages_off and passages_on.
Open the page from disk; the WAVs sit next to it (gitignored, so render first).

Usage: python tests/emphasis_page.py
"""

import html
import json
from pathlib import Path

import harness  # puts src/ on sys.path
import emphasis
from normalizer import prepare_speech

OUT = harness.REPO_ROOT / 'tests' / 'emphasis'
PASSAGES = ['01_markdown_what_i_did', '03_paths_urls_source_vs_frozen', '04_rhythm_solid_confirmation',
            '15_markdown_what_i_built']
COLUMNS = [  # (file suffix, label)
    ('app_off', 'Today (off)'), ('app_on', 'Prototype (on)'), ('strong', 'Stronger'),
    ('gain', 'Louder only'), ('dur', 'Slower only'), ('pitch', 'Higher only'),
    ('split', 'Separate call (rejected)'), ('stress', 'misaki stress (rejected)'),
]


def audio(src: str) -> str:
    return f'<audio controls preload="none" src="{html.escape(src)}"></audio>'


def main() -> None:
    data = json.loads((OUT / 'emphasis.json').read_text(encoding='utf-8'))
    rows = []
    for app_row in data['app']:
        sid = app_row['sentence']
        cells = ''.join(f'<td>{audio(f"wav/{sid}_{suffix}.wav")}</td>' for suffix, _ in COLUMNS)
        rows.append(f'<tr><th>{html.escape(app_row["markdown"])}<br><small>emphasis on: '
                    f'{html.escape(", ".join(app_row["on"]["spans"]))}</small></th>{cells}</tr>')
    head = ''.join(f'<th>{html.escape(label)}</th>' for _, label in COLUMNS)

    s = data['summary']
    measured = ''.join(
        f'<tr><td>{v}</td><td>{x["span_duration_pct"]:+.0f}%</td><td>{x["span_f0_pct"]:+.1f}%</td>'
        f'<td>{x["span_rms_db"]:+.1f} dB</td><td>{x["rest_f0_pct"]:+.1f}%</td><td>{x["rest_rms_db"]:+.2f} dB</td></tr>'
        for v, x in s.items())

    manifest = {e['id']: e['text'] for e in harness.load_manifest()}
    emphasis.EMPHASIS_ENABLED = True
    passages = []
    for pid in PASSAGES:
        spans = [c.text[a:b] for c in prepare_speech(manifest[pid]) for a, b in c.emphasis]
        passages.append(f'<tr><th>{pid}<br><small>emphasis on: {html.escape("; ".join(spans))}</small></th>'
                        f'<td>{audio(f"passages_off/wav/{pid}.wav")}</td>'
                        f'<td>{audio(f"passages_on/wav/{pid}.wav")}</td></tr>')
    emphasis.EMPHASIS_ENABLED = False

    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Emphasis listening</title>
<style>
:root {{ --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6b66; --line:#dedbd2; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1b1a; --fg:#ecebe6; --muted:#a3a29b; --line:#3a3936; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:24px 16px; }}
table {{ border-collapse:collapse; margin:12px 0 28px; }}
th, td {{ border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }}
th small {{ color:var(--muted); font-weight:normal; }}
audio {{ width:180px; }}
.wrap {{ overflow-x:auto; }}
p {{ max-width:70ch; }}
</style></head><body>
<h1>Emphasis: what to listen for</h1>
<p>Each row is one sentence. <b>Today</b> is the app as it is. <b>Prototype</b> is src/emphasis.py with its
default strength: the emphasized words are about 20% slower, 8% higher in pitch and 2 dB louder, made inside
Kokoro's single pass, so there is no join. The other columns change one thing at a time, or show the two
rejected approaches. Listen for: does the word stand out, does it sound natural, and is there any click or
break around it.</p>
<div class="wrap"><table><tr><th>Sentence</th>{head}</tr>{"".join(rows)}</table></div>
<h2>Whole passages (real messages)</h2>
<div class="wrap"><table><tr><th>Passage</th><th>Today (off)</th><th>Prototype (on)</th></tr>{"".join(passages)}</table></div>
<h2>Measured (median of 8 sentences, change vs today)</h2>
<p>"repeat" is today rendered a second time: Kokoro is not deterministic, so that row shows how much the numbers
move on their own (per sentence the pitch moves up to about ±5%).</p>
<div class="wrap"><table><tr><th>Variant</th><th>Span length</th><th>Span pitch</th><th>Span loudness</th>
<th>Rest pitch</th><th>Rest loudness</th></tr>{measured}</table></div>
</body></html>
'''
    (OUT / 'listen.html').write_text(page, encoding='utf-8')
    print(OUT / 'listen.html')


if __name__ == '__main__':
    main()
