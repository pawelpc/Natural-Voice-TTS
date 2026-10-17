"""Build the Phase 4 listening page (tests/phase4/listening.html) from the repo's own artifacts.

Before = tests/baseline (the v1.1.0 code), After = tests/phase3 (final code). The page
expects the audio as audio/before/<id>.mp3 and audio/after/<id>.mp3 next to it; make
them with --audio-out (WAVs are gitignored, so the MP3s are not committed either).

Usage:
    python tests/phase4/build_page.py --audio-out <dir>
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / 'tests'))
import harness  # noqa: E402

MP3_COMPRESSION = 0.6  # libsndfile MP3 quality; about 64 kbit/s for 24 kHz mono


def passage_data() -> list[dict]:
    before = {p['id']: p for p in json.loads((REPO / 'tests/baseline/render_summary.json').read_text('utf-8'))['passages']}
    after = {p['id']: p for p in json.loads((REPO / 'tests/phase3/render_summary.json').read_text('utf-8'))['passages']}
    out = []
    for n, entry in enumerate(harness.load_manifest(), 1):
        pid = entry['id']
        before_meta = json.loads((REPO / 'tests/baseline/meta' / f'{pid}.json').read_text('utf-8'))
        after_chunks = (REPO / 'tests/passages/expected_spoken' / f'{pid}.txt').read_text('utf-8').splitlines()
        out.append({
            'id': pid, 'num': n, 'category': entry['category'], 'origin': entry['origin'], 'tests': entry['tests'],
            'screen': entry['text'].rstrip('\n'),
            'before_chunks': [s['text'] for s in before_meta['sentences']],
            'after_chunks': after_chunks,
            'before_s': before[pid]['duration_s'], 'after_s': after[pid]['duration_s'],
        })
    return out


def encode_audio(out_dir: Path) -> None:
    import soundfile as sf
    for side, src in (('before', REPO / 'tests/baseline/wav'), ('after', REPO / 'tests/phase3/wav')):
        (out_dir / side).mkdir(parents=True, exist_ok=True)
        for wav in sorted(src.glob('*.wav')):
            audio, sr = sf.read(str(wav), dtype='float32')
            sf.write(str(out_dir / side / f'{wav.stem}.mp3'), audio, sr, format='MP3',
                     bitrate_mode='CONSTANT', compression_level=MP3_COMPRESSION)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--audio-out', type=Path, help='also encode the MP3s into this folder')
    args = parser.parse_args()
    data = json.dumps(passage_data(), ensure_ascii=False).replace('</', '<\\/')
    page = (HERE / 'listening.template.html').read_text('utf-8').replace('/*DATA*/', data)
    (HERE / 'listening.html').write_text(page, encoding='utf-8', newline='\n')
    print(f'wrote {HERE / "listening.html"} ({len(page) // 1024} KB)')
    if args.audio_out:
        encode_audio(args.audio_out)
        print(f'encoded MP3s into {args.audio_out}')


if __name__ == '__main__':
    main()
