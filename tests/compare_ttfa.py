"""R3 check: compare time to first audio between two checkouts of the repo.

Runs each checkout's tests/measure_ttfa.py in alternating rounds, in ABBA
order (before/after, then after/before, ...), so slow drift on the machine
(GPU clocks, heat) and any first-or-second-in-round effect hit both sides
equally. Both load the model from this repo's dist/ folder.

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
BOOTSTRAP_ROUNDS = 5000
BOOTSTRAP_SEED = 17


def bootstrap_change_ci(before: list[float], after: list[float]) -> tuple[float, float]:
    """95% interval for the relative change in median TTFA (after vs before)."""
    import random
    rng = random.Random(BOOTSTRAP_SEED)
    changes = []
    for _ in range(BOOTSTRAP_ROUNDS):
        b = statistics.median(rng.choices(before, k=len(before)))
        a = statistics.median(rng.choices(after, k=len(after)))
        changes.append((a - b) / b)
    changes.sort()
    return changes[int(0.025 * len(changes))], changes[int(0.975 * len(changes))]


def run_once(root: Path, repeats: int, out: Path, passages: list[str] | None,
             extra: list[Path] | None = None) -> dict:
    env = dict(os.environ, NVTTS_MODEL_DIR=str(harness.REPO_ROOT / 'dist' / 'NaturalVoiceTTS' / 'kokoro_model'),
               PYTHONIOENCODING='utf-8')
    cmd = [sys.executable, str(root / 'tests' / 'measure_ttfa.py'), '--repeats', str(repeats), '--out', str(out)]
    if passages:
        cmd += ['--passages', *passages]
    if extra:
        cmd += ['--extra-passage', *[str(f.resolve()) for f in extra]]
    subprocess.run(cmd, cwd=root, env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return json.loads(out.read_text(encoding='utf-8'))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--passages', nargs='*', help='passage ids (default: measure_ttfa.py defaults)')
    parser.add_argument('--extra-passage', type=Path, nargs='*', default=[],
                        help='text files also measured (first), on both sides; needs a measure_ttfa.py that knows --extra-passage')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    samples: dict[str, dict[str, list[float]]] = {'before': {}, 'after': {}}
    sides = [('before', args.before), ('after', args.after)]
    with tempfile.TemporaryDirectory() as tmp:
        for rnd in range(args.rounds):
            # ABBA order: which side runs first alternates, so a first/second-in-round bias cancels out.
            for side, root in (sides if rnd % 2 == 0 else sides[::-1]):
                result = run_once(root.resolve(), args.repeats, Path(tmp) / f'{side}{rnd}.json', args.passages,
                                  args.extra_passage)
                for pid, p in result['passages'].items():
                    samples[side].setdefault(pid, []).extend(r['ttfa_s'] for r in p['runs'])
                print(f'round {rnd + 1} {side} done', flush=True)

    report = {'before': str(args.before), 'after': str(args.after), 'rounds': args.rounds,
              'repeats': args.repeats, 'limit': R3_LIMIT, 'passages': {}}
    worst = float('-inf')
    worst_hi = float('-inf')
    for pid in samples['before']:
        before, after = samples['before'][pid], samples['after'][pid]
        b, a = statistics.median(before), statistics.median(after)
        change = (a - b) / b
        lo, hi = bootstrap_change_ci(before, after)
        worst, worst_hi = max(worst, change), max(worst_hi, hi)
        report['passages'][pid] = {'before_median_s': round(b, 3), 'after_median_s': round(a, 3),
                                   'change_pct': round(change * 100, 1),
                                   'change_ci95_pct': [round(lo * 100, 1), round(hi * 100, 1)],
                                   'n': len(after),
                                   'before_s': [round(x, 3) for x in before],
                                   'after_s': [round(x, 3) for x in after]}
        print(f'{pid}: before {b:.3f} s, after {a:.3f} s, change {change * 100:+.1f}% '
              f'(95% CI {lo * 100:+.1f}% to {hi * 100:+.1f}%)')
    # Pass: no median got more than 10% worse. "Resolved": even the CI's upper end is within the limit.
    report['pass'] = worst <= R3_LIMIT
    report['resolved'] = worst_hi <= R3_LIMIT
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print(f"R3 {'PASS' if report['pass'] else 'FAIL'} (worst median change {worst * 100:+.1f}%, "
          f"worst CI upper end {worst_hi * 100:+.1f}%, limit +{R3_LIMIT * 100:.0f}%)")


if __name__ == '__main__':
    main()
