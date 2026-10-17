"""Measure how much time the real play_audio() adds on top of a clip's length
on this machine's default output device. Plays silence only, so nothing is heard.

The first call after idle includes opening the device; later calls show the
per-chunk cost (stream start plus the player's 50 ms polling).

Usage:
    python tests/measure_device.py --out tests/baseline/device_overhead.json
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import numpy as np

import harness

CLIP_SECONDS = [1.275, 7.6, 1.975, 1.275, 7.6, 1.975, 1.0, 1.0]  # lengths seen in the baseline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=harness.REPO_ROOT / 'tests' / 'baseline' / 'device_overhead.json')
    args = parser.parse_args()
    import sounddevice as sd
    import audio_player

    rows = []
    for secs in CLIP_SECONDS:
        clip = np.zeros(int(secs * harness.SAMPLE_RATE), dtype=np.float32)
        t0 = time.perf_counter()
        ok = audio_player.play_audio(clip)
        rows.append({'clip_s': secs, 'wall_s': round(time.perf_counter() - t0, 4), 'ok': ok})
        rows[-1]['overhead_s'] = round(rows[-1]['wall_s'] - secs, 4)
        print(rows[-1], flush=True)
    later = [r['overhead_s'] for r in rows[1:]]
    result = {'device': sd.query_devices(kind='output')['name'], 'rows': rows,
              'first_call_overhead_s': rows[0]['overhead_s'],
              'later_overhead_median_s': round(statistics.median(later), 4)}
    args.out.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(f"first call +{result['first_call_overhead_s']} s, later median +{result['later_overhead_median_s']} s "
          f"on {result['device']} -> {args.out}")


if __name__ == '__main__':
    main()
