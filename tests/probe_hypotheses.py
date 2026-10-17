"""Phase 0 evidence for hypotheses H1-H4 (see _prosody-brief.md).

H1  split_sentences() breaks after abbreviations, initials and decimals.
H2  tts_engine.SPLIT_PATTERN splits inside tokens ("3.5", "v1.1.0", "app.py")
    and strips the end punctuation before Kokoro sees the text.
H3  No normalization step: markdown, paths, URLs, units, times reach misaki raw.
H4  Nothing controls pause length; gaps are whatever the audio contains.

Reads the baseline render (meta/, ttfa.json, device_overhead.json) for H4,
so run render_passages.py, measure_ttfa.py and measure_device.py first.

Usage:
    python tests/probe_hypotheses.py --baseline tests/baseline
"""

import argparse
import json
import statistics
from pathlib import Path

import numpy as np

import harness

H1_CASES = [
    'Dr. Smith arrived late.',
    'Use a short tool, e.g. this one, for the job.',
    'The U.S. Army left the base.',
    'Mr. and Mrs. Jones came at 5 p.m. today.',
    'J. R. R. Tolkien wrote the book.',
    'Version 3.5 is out now.',
    'It ended... then it began again.',
]

H2_CASES = [
    'Upgrade to v1.1.0 now.',
    'Pi is 3.5 or so.',
    'Open app.py today.',
    'Are you sure?',
    'Stop right there!',
    'This line\nwraps in the middle.',
]

H2_QUESTIONS = ['Are you sure?', 'Is it ready yet?', 'Did you see that?']

H3_CASES = [
    '**Bold** text here.',
    '# Release Notes',
    'Use `split_sentences()` here.',
    '- espeak-ng installed',
    'Open src/app.py now.',
    'Open C:\\Users\\paul\\notes.txt now.',
    'Visit https://github.com/pawelpc/Natural-Voice-TTS today.',
    'Email paul@example.com today.',
    'It is 25 mm thick and weighs 1.2 kg.',
    'Meet at 14:30 on 2026-10-17.',
    'About ~50% → done.',
    'Louis XVI ruled France.',
    'See [the README](https://example.com/readme) first.',
    '| File | How it is packaged |',
    'Run `e3f15ec..bba2200` now.',
]

F0_MIN, F0_MAX = 70.0, 400.0
F0_FRAME_MS = 40
F0_HOP_MS = 10
F0_VOICED_CORR = 0.5
F0_TAIL_MS = 200


def h1(split_sentences) -> list[dict]:
    return [{'input': s, 'chunks': split_sentences(s), 'wrong_split': len(split_sentences(s)) > 1}
            for s in H1_CASES]


def run_pipeline(pipeline, text: str, split_pattern) -> list[dict]:
    import tts_engine
    out = []
    for r in pipeline(text, voice=tts_engine.DEFAULT_VOICE, speed=tts_engine.DEFAULT_SPEED,
                      split_pattern=split_pattern):
        out.append({'graphemes': r.graphemes, 'phonemes': r.phonemes,
                    'audio': None if r.audio is None else np.asarray(r.audio, dtype=np.float32)})
    return out


def h2(pipeline, split_pattern: str) -> list[dict]:
    rows = []
    for s in H2_CASES:
        cur = run_pipeline(pipeline, s, split_pattern)
        ref = run_pipeline(pipeline, s, r'\n+')  # Kokoro's own default
        rows.append({
            'input': s,
            'current_segments': [{'graphemes': c['graphemes'], 'phonemes': c['phonemes']} for c in cur],
            'kokoro_default_segments': [{'graphemes': c['graphemes'], 'phonemes': c['phonemes']} for c in ref],
            'current_last_phoneme': cur[-1]['phonemes'][-1:] if cur else '',
            'kokoro_default_last_phoneme': ref[-1]['phonemes'][-1:] if ref else '',
        })
    return rows


def f0_track(audio: np.ndarray, sr: int = harness.SAMPLE_RATE) -> list[float | None]:
    """Autocorrelation pitch per hop; None for unvoiced frames."""
    n, hop = int(sr * F0_FRAME_MS / 1000), int(sr * F0_HOP_MS / 1000)
    lo, hi = int(sr / F0_MAX), int(sr / F0_MIN)
    track = []
    for start in range(0, len(audio) - n, hop):
        x = audio[start:start + n].astype(np.float64)
        x = x - x.mean()
        energy = np.dot(x, x)
        if energy < 1e-4:
            track.append(None)
            continue
        ac = np.correlate(x, x, 'full')[n - 1:]
        lag = lo + int(np.argmax(ac[lo:hi]))
        track.append(sr / lag if ac[lag] / energy > F0_VOICED_CORR else None)
    return track


def final_pitch_change(audio: np.ndarray) -> dict:
    """Median F0 over the last F0_TAIL_MS of voicing vs the 400 ms before it."""
    track = f0_track(audio)
    voiced = [(i, f) for i, f in enumerate(track) if f is not None]
    if len(voiced) < 10:
        return {'tail_hz': None, 'before_hz': None, 'change_pct': None}
    last = voiced[-1][0]
    tail_frames = F0_TAIL_MS // F0_HOP_MS
    tail = [f for i, f in voiced if i > last - tail_frames]
    before = [f for i, f in voiced if last - tail_frames - 40 < i <= last - tail_frames]
    t, b = statistics.median(tail), statistics.median(before) if before else None
    return {'tail_hz': round(t, 1), 'before_hz': None if b is None else round(b, 1),
            'change_pct': None if b is None else round((t - b) / b * 100, 1)}


def h2_questions(pipeline, split_pattern: str, out_dir: Path) -> list[dict]:
    rows = []
    for i, q in enumerate(H2_QUESTIONS, 1):
        row = {'input': q}
        for label, pattern in (('current', split_pattern), ('kokoro_default', r'\n+')):
            segs = run_pipeline(pipeline, q, pattern)
            audio = np.concatenate([s['audio'] for s in segs if s['audio'] is not None])
            harness.write_wav(out_dir / f'h2_question{i}_{label}.wav', audio)
            row[label] = {'phonemes': ' | '.join(s['phonemes'] for s in segs), **final_pitch_change(audio)}
        rows.append(row)
    return rows


def h3(pipeline) -> list[dict]:
    rows = []
    for s in H3_CASES:
        ps, tokens = pipeline.g2p(s)
        rows.append({'input': s, 'phonemes': ps,
                     'tokens': [[t.text, t.phonemes] for t in tokens]})
    return rows


def h4(baseline: Path) -> dict:
    """Silence at each boundary type in the baseline render, plus live worker gaps."""
    from text_processor import clean_text
    kinds: dict[str, list[float]] = {'within_chunk_kokoro_split': [], 'between_chunks_same_paragraph': [],
                                     'between_chunks_new_paragraph': [], 'internal_pause': []}
    for meta_path in sorted((baseline / 'meta').glob('*.json')):
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        text = clean_text((harness.PASSAGES_DIR / f"{meta['id']}.txt").read_text(encoding='utf-8'))
        pos, prev_tail = 0, None
        for sent in meta['sentences']:
            segs = [g for g in sent['kokoro_segments'] if 'lead_ms' in g]
            at = text.find(sent['text'], pos)
            between = text[pos:at] if at >= 0 else ''
            pos = at + len(sent['text']) if at >= 0 else pos
            for j, g in enumerate(segs):
                if j == 0 and prev_tail is not None:
                    key = 'between_chunks_new_paragraph' if '\n\n' in between else 'between_chunks_same_paragraph'
                    kinds[key].append(prev_tail + g['lead_ms'])
                elif j > 0:
                    kinds['within_chunk_kokoro_split'].append(segs[j - 1]['trail_ms'] + g['lead_ms'])
                kinds['internal_pause'].extend(p['ms'] for p in g['pauses'])
            if segs:
                prev_tail = segs[-1]['trail_ms']

    def stats(v: list[float]) -> dict:
        if not v:
            return {'n': 0}
        return {'n': len(v), 'min_ms': min(v), 'median_ms': statistics.median(v), 'max_ms': max(v),
                'p10_ms': float(np.percentile(v, 10)), 'p90_ms': float(np.percentile(v, 90))}

    ttfa = json.loads((baseline / 'ttfa.json').read_text(encoding='utf-8'))
    device = json.loads((baseline / 'device_overhead.json').read_text(encoding='utf-8'))
    return {'audio_silence_by_boundary': {k: stats(v) for k, v in kinds.items()},
            'worker_gaps': {pid: {k: v for k, v in r.items() if k != 'runs'} for pid, r in ttfa['passages'].items()},
            'device_overhead': {k: v for k, v in device.items() if k != 'rows'}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--baseline', type=Path, default=harness.REPO_ROOT / 'tests' / 'baseline')
    args = parser.parse_args()
    harness.setup_logging()
    tts_engine = harness.load_engine()
    from text_processor import split_sentences
    pipeline = tts_engine.get_pipeline()

    evidence = {
        'env': harness.env_info(),
        'split_pattern': tts_engine.SPLIT_PATTERN,
        'H1': h1(split_sentences),
        'H2': h2(pipeline, tts_engine.SPLIT_PATTERN),
        'H2_questions': h2_questions(pipeline, tts_engine.SPLIT_PATTERN, args.baseline / 'probe'),
        'H3': h3(pipeline),
        'H4': h4(args.baseline),
    }
    out = args.baseline / 'hypotheses.json'
    out.write_text(json.dumps(evidence, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Saved {out}')


if __name__ == '__main__':
    main()
