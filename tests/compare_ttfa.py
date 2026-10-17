"""R3 check: compare time to first audio between two checkouts of the repo.

Runs each checkout's tests/measure_ttfa.py in alternating rounds (before,
after, before, after, ...) so slow drift on the machine (GPU clocks, heat)
affects both sides equally. Both load the model from this repo's dist/ folder.

Usage:
    python tests/compare_ttfa.py --before <phase0 checkout> --after . --out tests/phase1/r3.json
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

import harness

R3_LIMIT = 0.10  # a regression of more than 10% fails (brief, R3)


def run_once(root: Path, repeats: int, out: Path) -> dict:
    env = dict(os.environ, NVTTS_MODEL_DIR=str(harness.REPO_ROOT / 'dist' / 'NaturalVoiceTTS' / 'kokoro_model'),
               PYTHONIOENCODING='utf-8')
    subprocess.run([sys.executable, str(root / 'tests' / 'measure_ttfa.py'), '--repeats', str(repeats),
                    '--out', str(out)], cwd=root, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return json.loads(out.read_text(encoding='utf-8'))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    samples: dict[str, dict[str, list[float]]] = {'before': {}, 'after': {}}
    with tempfile.TemporaryDirectory() as tmp:
        for rnd in range(args.rounds):
            for side, root in (('before', args.before), ('after', args.after)):
                result = run_once(root.resolve(), args.repeats, Path(tmp) / f'{side}{rnd}.json')
                for pid, p in result['passages'].items():
                    samples[side].setdefault(pid, []).extend(r['ttfa_s'] for r in p['runs'])
                print(f'round {rnd + 1} {side} done', flush=True)

    report = {'before': str(args.before), 'after': str(args.after), 'rounds': args.rounds,
              'repeats': args.repeats, 'limit': R3_LIMIT, 'passages': {}}
    worst = float('-inf')
    for pid in samples['before']:
        b, a = statistics.median(samples['before'][pid]), statistics.median(samples['after'][pid])
        change = (a - b) / b
        worst = max(worst, change)
        report['passages'][pid] = {'before_median_s': round(b, 3), 'after_median_s': round(a, 3),
                                   'change_pct': round(change * 100, 1), 'n': len(samples['after'][pid]),
                                   'before_s': [round(x, 3) for x in samples['before'][pid]],
                                   'after_s': [round(x, 3) for x in samples['after'][pid]]}
        print(f'{pid}: before {b:.3f} s, after {a:.3f} s, change {change * 100:+.1f}%')
    report['pass'] = worst <= R3_LIMIT
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print(f"R3 {'PASS' if report['pass'] else 'FAIL'} (worst change {worst * 100:+.1f}%, limit +{R3_LIMIT * 100:.0f}%)")


if __name__ == '__main__':
    main()
