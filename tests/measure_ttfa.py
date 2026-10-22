"""Measure time to first audio (TTFA) and the gaps between spoken chunks,
using the tray app's real worker thread (app._worker).

TTFA = time from putting text on the app's queue to the first play_audio()
call. Gap = time from one play_audio() returning to the next one starting.

play_audio is replaced by a sleep for the clip's duration, so no sound is made
and the numbers exclude the sound device's own start-up time (measure that
with measure_device.py and add it).

Usage:
    python tests/measure_ttfa.py --out tests/baseline/ttfa.json
"""

import argparse
import json
import statistics
import threading
import time
from pathlib import Path

import harness

DEFAULT_PASSAGES = ['17_splitting_july_regression', '16_rhythm_speak_call', '01_markdown_what_i_did']
DEFAULT_REPEATS = 5
MAX_CHUNKS = 4  # plays per run before stopping; TTFA and early gaps are what matter


def measure(passage_ids: list[str], repeats: int, extra: dict[str, str] | None = None) -> dict:
    """Run each passage through app._worker `repeats` times and collect timings."""
    harness.setup_logging()
    tts_engine = harness.load_engine()
    import app
    import audio_player

    defaults = {'voice': tts_engine.DEFAULT_VOICE, 'speed': tts_engine.DEFAULT_SPEED}
    app.config.get = lambda key: defaults[key]  # R1: pin voice/speed, ignore the user's config file

    plays: list[dict] = []
    done = threading.Event()

    def recording_play(audio, sr: int = harness.SAMPLE_RATE) -> bool:
        start = time.perf_counter()
        time.sleep(len(audio) / sr)
        end = time.perf_counter()
        plays.append({'start': start, 'end': end, 'audio_s': len(audio) / sr})
        if len(plays) >= MAX_CHUNKS:
            audio_player.stop()  # worker sees is_stopped() and finishes the read
        return True

    real_set_status = app._set_status

    def watching_set_status(status: str) -> None:
        real_set_status(status)
        if status == 'Idle':
            done.set()

    app.play_audio = recording_play
    app._set_status = watching_set_status
    worker = threading.Thread(target=app._worker, daemon=True, name='tts-worker')
    worker.start()

    texts = {e['id']: e['text'] for e in harness.load_manifest()}
    texts.update(extra or {})  # --extra-passage texts, outside the passage set
    result = {'env': harness.env_info(), 'repeats': repeats, 'max_chunks': MAX_CHUNKS, 'passages': {}}
    for pid in passage_ids:
        runs = []
        for _ in range(repeats):
            plays.clear()
            done.clear()
            t0 = time.perf_counter()
            app._text_queue.put(texts[pid])
            if not done.wait(timeout=300):
                raise RuntimeError(f'worker did not finish {pid}')
            gaps = [plays[i + 1]['start'] - plays[i]['end'] for i in range(len(plays) - 1)]
            runs.append({'ttfa_s': plays[0]['start'] - t0 if plays else None,
                         'gaps_s': [round(g, 4) for g in gaps]})
        ttfas = [r['ttfa_s'] for r in runs]
        all_gaps = [g for r in runs for g in r['gaps_s']]
        result['passages'][pid] = {
            'ttfa_median_s': round(statistics.median(ttfas), 3),
            'ttfa_min_s': round(min(ttfas), 3), 'ttfa_max_s': round(max(ttfas), 3),
            'gap_median_s': round(statistics.median(all_gaps), 3) if all_gaps else None,
            'gap_max_s': round(max(all_gaps), 3) if all_gaps else None,
            'runs': runs,
        }
        p = result['passages'][pid]
        print(f"{pid}: TTFA median {p['ttfa_median_s']} s (min {p['ttfa_min_s']}, max {p['ttfa_max_s']}); "
              f"gap median {p['gap_median_s']} s, max {p['gap_max_s']}")
    app._text_queue.put(None)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=harness.REPO_ROOT / 'tests' / 'baseline' / 'ttfa.json')
    parser.add_argument('--passages', nargs='*', default=DEFAULT_PASSAGES)
    parser.add_argument('--repeats', type=int, default=DEFAULT_REPEATS)
    parser.add_argument('--extra-passage', type=Path, nargs='*', default=[],
                        help='text files measured first, named by file stem (not in tests/passages)')
    args = parser.parse_args()
    extra = {f.stem: f.read_text(encoding='utf-8') for f in args.extra_passage}
    result = measure(list(extra) + args.passages, args.repeats, extra)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    print(f'Saved {args.out}')


if __name__ == '__main__':
    main()
