"""Phase 3 gate: measure every deliberate pause in the rendered WAVs.

For each pause the render recorded (kind, target, position), find the silent
run in the final WAV at that position and compare its length to the target.
The detector reads only the WAV; positions come from the render metadata.

Usage:
    python tests/measure_pauses.py --render tests/phase3 --out tests/phase3/pauses.json
"""

import argparse
import json
import statistics
from pathlib import Path

import numpy as np
import soundfile as sf

import harness

TOLERANCE_MS = 50       # gate: every pause within +/-50 ms of its target
FRAME_MS = 5
SEARCH_MS = 60          # the silent run must overlap the mark within this window


def silent_run_at(db: np.ndarray, at_ms: float, target_ms: float) -> float | None:
    """Length (ms) of the silent run covering the middle of the intended pause."""
    centre = int((at_ms + target_ms / 2) / FRAME_MS)
    window = int(SEARCH_MS / FRAME_MS)
    candidates = [f for f in range(max(centre - window, 0), min(centre + window + 1, len(db)))
                  if db[f] <= harness.SILENCE_DBFS]
    if not candidates:
        return None
    f = min(candidates, key=lambda x: abs(x - centre))
    lo, hi = f, f
    while lo > 0 and db[lo - 1] <= harness.SILENCE_DBFS:
        lo -= 1
    while hi + 1 < len(db) and db[hi + 1] <= harness.SILENCE_DBFS:
        hi += 1
    return (hi - lo + 1) * FRAME_MS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--render', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    harness.FRAME_MS = FRAME_MS

    by_kind: dict[str, list[float]] = {}
    failures = []
    for meta_path in sorted((args.render / 'meta').glob('*.json')):
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        audio, sr = sf.read(str(args.render / 'wav' / f"{meta['id']}.wav"), dtype='float32')
        db = harness.frame_dbfs(audio, sr)
        for mark in meta['pauses']:
            measured = silent_run_at(db, mark['at_ms'], mark['target_ms'])
            err = None if measured is None else measured - mark['target_ms']
            by_kind.setdefault(mark['kind'], []).append(err if err is not None else float('nan'))
            if err is None or abs(err) > TOLERANCE_MS:
                failures.append({'id': meta['id'], **mark, 'measured_ms': measured, 'error_ms': err})

    summary = {}
    for kind, errs in sorted(by_kind.items()):
        ok = [e for e in errs if e == e]
        summary[kind] = {'n': len(errs), 'found': len(ok),
                         'median_error_ms': statistics.median(ok) if ok else None,
                         'max_abs_error_ms': max(abs(e) for e in ok) if ok else None,
                         'within_tolerance': sum(1 for e in ok if abs(e) <= TOLERANCE_MS)}
        s = summary[kind]
        print(f"{kind:9}: {s['within_tolerance']}/{s['n']} within ±{TOLERANCE_MS} ms, "
              f"median error {s['median_error_ms']} ms, max |error| {s['max_abs_error_ms']} ms")
    result = {'tolerance_ms': TOLERANCE_MS, 'summary': summary, 'failures': failures,
              'pass': not failures}
    args.out.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(f"{'PASS' if result['pass'] else 'FAIL'}: {len(failures)} pause(s) outside ±{TOLERANCE_MS} ms -> {args.out}")


if __name__ == '__main__':
    main()
