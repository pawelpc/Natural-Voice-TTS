"""Render every passage in tests/passages/ the way the tray app speaks it.

For each passage: normalizer.prepare_speech() -> app.render_chunk() per chunk
(the same calls the worker makes, including the pauses), audio joined back to
back. Any extra delay from the sound device is measured separately
(measure_device.py). Writes one WAV and one JSON per passage, plus a summary;
the JSON lists every deliberate pause (kind, target, position) for
measure_pauses.py.

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
    from normalizer import prepare_speech

    voice, speed = tts_engine.DEFAULT_VOICE, tts_engine.DEFAULT_SPEED
    summary = {'env': harness.env_info(), 'voice': voice, 'speed': speed, 'passages': []}

    for entry in harness.load_manifest():
        if only and entry['id'] not in only:
            continue
        spoken = prepare_speech(entry['text'])
        chunks = [s.text for s in spoken]
        sentences, audios, skipped, pause_marks = [], [], 0, []
        offset_ms = 0.0
        for i, chunk in enumerate(chunks):
            recorder.records.clear()
            t0 = time.perf_counter()
            audio, marks = app.render_chunk(tts_engine, spoken, i, voice, speed)  # same as the worker
            synth_s = time.perf_counter() - t0
            pause_marks += [{'kind': m.kind, 'target_ms': m.target_ms, 'at_ms': round(offset_ms + m.at_ms, 1),
                             'chunk': i} for m in marks]
            if audio is not None:
                offset_ms += len(audio) / harness.SAMPLE_RATE * 1000
            segments = []
            for rec in recorder.records:
                seg = {k: rec[k] for k in ('graphemes', 'phonemes', 'silent_words', 'samples')}
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
        silent = [w for s in sentences for g in s['kokoro_segments'] for w in g['silent_words']]
        meta = {'id': entry['id'], 'category': entry['category'], 'origin': entry['origin'],
                'chunks': len(chunks), 'skipped': skipped, 'silent_words': silent,
                'kokoro_segments': sum(len(s['kokoro_segments']) for s in sentences),
                'duration_s': round(len(full) / harness.SAMPLE_RATE, 2),
                'synth_s': round(sum(s['synth_s'] for s in sentences), 2),
                'wav_sha256': sha, 'pauses': pause_marks, 'sentences': sentences}
        (out_dir / 'meta').mkdir(parents=True, exist_ok=True)
        (out_dir / 'meta' / f"{entry['id']}.json").write_text(
            json.dumps(meta, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        summary['passages'].append({k: v for k, v in meta.items() if k not in ('sentences', 'pauses')})
        print(f"{entry['id']}: {len(chunks)} chunks, {meta['kokoro_segments']} kokoro segments, "
              f"{meta['duration_s']} s audio, {skipped} skipped, silent words: {silent}")

    (out_dir / 'render_summary.json').write_text(
        json.dumps(summary, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=harness.REPO_ROOT / 'tests' / 'baseline')
    parser.add_argument('--only', nargs='*', help='passage ids to render (default: all)')
    parser.add_argument('--no-emphasis', action='store_true',
                        help='turn emphasis.EMPHASIS_ENABLED off (when on, emphasized chunks bypass the recorder)')
    args = parser.parse_args()
    if args.no_emphasis:
        import emphasis
        emphasis.EMPHASIS_ENABLED = False
    summary = render(args.out, args.only)
    total = sum(p['duration_s'] for p in summary['passages'])
    print(f"Rendered {len(summary['passages'])} passages, {total:.1f} s of audio -> {args.out}")


if __name__ == '__main__':
    main()
