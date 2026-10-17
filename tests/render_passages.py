"""Render every passage in tests/passages/ the way the tray app speaks it.

For each passage: split_sentences() -> app._synthesize_sentence() per chunk,
audio joined back to back (device gaps between chunks are measured separately
by measure_ttfa.py). Writes one WAV and one JSON per passage, plus a summary.

Usage:
    python tests/render_passages.py --out tests/baseline
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np

import harness


def render(out_dir: Path, only: list[str] | None = None) -> dict:
    """Render passages into out_dir/wav and out_dir/meta; return the summary."""
    harness.setup_logging()
    tts_engine = harness.load_engine()
    recorder = harness.install_recorder(tts_engine)
    import app
    from text_processor import split_sentences

    voice, speed = tts_engine.DEFAULT_VOICE, tts_engine.DEFAULT_SPEED
    summary = {'env': harness.env_info(), 'voice': voice, 'speed': speed, 'passages': []}

    for entry in harness.load_manifest():
        if only and entry['id'] not in only:
            continue
        chunks = split_sentences(entry['text'])
        sentences, audios, skipped = [], [], 0
        for chunk in chunks:
            recorder.records.clear()
            t0 = time.perf_counter()
            audio = app._synthesize_sentence(tts_engine, chunk, voice, speed)
            synth_s = time.perf_counter() - t0
            segments = []
            for rec in recorder.records:
                seg = {k: rec[k] for k in ('graphemes', 'phonemes', 'samples')}
                if rec['audio'] is not None and len(rec['audio']):
                    lead, trail = harness.edge_silence_ms(rec['audio'])
                    seg.update(ms=round(rec['samples'] / harness.SAMPLE_RATE * 1000, 1),
                               lead_ms=lead, trail_ms=trail,
                               pauses=harness.internal_pauses(rec['audio']))
                segments.append(seg)
            if audio is None:
                skipped += 1
            else:
                audios.append(np.asarray(audio, dtype=np.float32))
            sentences.append({'text': chunk, 'synth_s': round(synth_s, 3),
                              'ms': 0 if audio is None else round(len(audio) / harness.SAMPLE_RATE * 1000, 1),
                              'skipped': audio is None, 'kokoro_segments': segments})

        full = np.concatenate(audios) if audios else np.zeros(1, dtype=np.float32)
        sha = harness.write_wav(out_dir / 'wav' / f"{entry['id']}.wav", full)
        meta = {'id': entry['id'], 'category': entry['category'], 'origin': entry['origin'],
                'chunks': len(chunks), 'skipped': skipped,
                'kokoro_segments': sum(len(s['kokoro_segments']) for s in sentences),
                'duration_s': round(len(full) / harness.SAMPLE_RATE, 2),
                'synth_s': round(sum(s['synth_s'] for s in sentences), 2),
                'wav_sha256': sha, 'sentences': sentences}
        (out_dir / 'meta').mkdir(parents=True, exist_ok=True)
        (out_dir / 'meta' / f"{entry['id']}.json").write_text(
            json.dumps(meta, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        summary['passages'].append({k: v for k, v in meta.items() if k != 'sentences'})
        print(f"{entry['id']}: {len(chunks)} chunks, {meta['kokoro_segments']} kokoro segments, "
              f"{meta['duration_s']} s audio, {skipped} skipped")

    (out_dir / 'render_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=harness.REPO_ROOT / 'tests' / 'baseline')
    parser.add_argument('--only', nargs='*', help='passage ids to render (default: all)')
    args = parser.parse_args()
    summary = render(args.out, args.only)
    total = sum(p['duration_s'] for p in summary['passages'])
    print(f"Rendered {len(summary['passages'])} passages, {total:.1f} s of audio -> {args.out}")


if __name__ == '__main__':
    main()
