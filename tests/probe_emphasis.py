"""Emphasis research (Paul's Phase 4 note #13): render each option and measure it.

For a set of sentences with one emphasized span, each variant is rendered and
measured over the span and over the rest of the sentence:
duration (from Kokoro's own alignment), median F0 (YIN on the audio) and RMS.

Variants:
  base      the app today (markers stripped, nothing else)
  repeat    base again, to show how much the numbers move between two renders of the same thing
  stress    misaki stress markup on the span's words ([word](2), via apply_stress)
  split     the span as its own Kokoro call at speed 0.85, joined to its neighbours
  gain      +4 dB on the span's audio (envelope from Kokoro's alignment, 40 ms ramps)
  dur       per-phoneme speed 0.80 on the span (one Kokoro call; speed may be a tensor)
  pitch     F0 x1.12 on the span, inside the same call (Kokoro's predicted F0 curve)
  combo     dur 0.85 + F0 x1.10 + gain +2 dB, one call
  strong    dur 0.80 + F0 x1.15 + gain +3 dB, one call
  pitchgain F0 x1.12 + gain +3 dB, no slowing, one call

Then the prototype itself (src/emphasis.py) through the app's own path,
app.render_chunk(), with EMPHASIS_ENABLED off and on, from the markdown form
of each sentence: <id>_app_off.wav / <id>_app_on.wav.

Usage: python tests/probe_emphasis.py --out tests/emphasis
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402

SR = harness.SAMPLE_RATE
FRAME = 600            # one Kokoro alignment frame, in samples (25 ms)

SENTENCES = [  # (id, plain text, emphasized span as it appears in the text)
    ('red', 'I said the red one, not the blue one.', 'red'),
    ('backup', 'You must back up your files before you upgrade.', 'back up your files'),
    ('really', 'This step is really important for the build.', 'really'),
    ('not', 'Do NOT delete the config folder.', 'NOT'),
    ('whole', 'Please read the whole message before you reply.', 'whole'),
    ('faster', 'The new splitter is much faster than the old one.', 'much faster'),
    ('label', 'Bottom line: the installed app still runs the old code.', 'Bottom line'),
    ('stale', 'The frozen build is stale, so rebuild it before you test.', 'stale'),
]

MARKDOWN = {  # the same sentences as they'd arrive on screen
    'red': 'I said the **red** one, not the blue one.',
    'backup': 'You must **back up your files** before you upgrade.',
    'really': 'This step is *really* important for the build.',
    'not': 'Do NOT delete the config folder.',
    'whole': 'Please read the *whole* message before you reply.',
    'faster': 'The new splitter is **much faster** than the old one.',
    'label': '**Bottom line:** the installed app still runs the old code.',
    'stale': 'The frozen build is *stale*, so rebuild it before you test.',
}

VARIANTS = {
    'base': {},
    'repeat': {},   # base rendered again: the measurement's noise floor (Kokoro's decoder is not deterministic)
    'stress': {'stress': True},
    'split': {'split_speed': 0.85},
    'gain': {'gain_db': 4.0},
    'dur': {'dur': 0.80},
    'pitch': {'f0': 1.12},
    'combo': {'dur': 0.85, 'f0': 1.10, 'gain_db': 2.0},
    'strong': {'dur': 0.80, 'f0': 1.15, 'gain_db': 3.0},
    'pitchgain': {'f0': 1.12, 'gain_db': 3.0},
}


# --- Synthesis -----------------------------------------------------------------
# The one-call variants use the prototype's own code (src/emphasis.py) with its
# strength constants set per variant, so "combo" is exactly the prototype's default.

def render(pipeline, text: str, span_text: str, opts: dict):
    """Returns audio, (span_start_s, span_end_s), phonemes."""
    from misaki.en import apply_stress
    import pauses

    a = text.index(span_text)
    span = (a, a + len(span_text))
    voice = pipeline.load_voice('af_heart')
    if 'split_speed' in opts:
        parts = [(text[:span[0]].strip(), 1.0), (text[span[0]:span[1]], opts['split_speed']),
                 (text[span[1]:].strip(), 1.0)]
        pieces, bounds, pos, ps_all = [], [], 0, []
        for k, (part, speed) in enumerate(parts):
            if not part or not any(c.isalnum() for c in part):
                pieces.append(np.zeros(0, np.float32))  # e.g. "." alone after the span
                continue
            audio = np.concatenate([r.audio.numpy() for r in pipeline(part, voice='af_heart', speed=speed)])
            audio = pauses.trim_edges(audio)
            if k == 1:
                bounds = [pos / SR, (pos + len(audio)) / SR]
            pieces.append(audio)
            pos += len(audio)
            ps_all.append(part)
        return np.concatenate(pieces), tuple(bounds), ' | '.join(ps_all)

    import emphasis
    emphasis.EMPHASIS_DURATION = opts.get('dur', 1.0)
    emphasis.EMPHASIS_PITCH = opts.get('f0', 1.0)
    emphasis.EMPHASIS_GAIN_DB = opts.get('gain_db', 0.0)
    _, tokens = pipeline.g2p(text)
    flags = emphasis.token_flags(text, tokens, [span])
    if opts.get('stress'):
        for t, f in zip(tokens, flags):
            if f:
                t.phonemes = apply_stress(t.phonemes, 2)
    out, ps_all = [], []
    span_s, offset = None, 0
    for gs, ps, tks in pipeline.en_tokenize(tokens):
        fl = [flags[tokens.index(t)] for t in tks]
        mask = emphasis.phoneme_mask(ps, tks, fl, pipeline.model.vocab)
        audio, pred_dur, frame_mask = emphasis.forward(pipeline.model, ps, voice[len(ps) - 1], mask, 1.0)
        audio = emphasis.apply_gain(audio, frame_mask)
        on = np.nonzero(frame_mask > 0)[0]
        if len(on):
            span_s = ((offset + on[0] * FRAME) / SR, (offset + (on[-1] + 1) * FRAME) / SR)
        out.append(audio.astype(np.float32))
        offset += len(audio)
        ps_all.append(ps)
    return np.concatenate(out), span_s, ' '.join(ps_all)


# --- Measurement ------------------------------------------------------------------

def yin_f0(audio: np.ndarray, sr: int = SR, fmin: float = 70, fmax: float = 450,
           win: int = 1024, hop: int = 240, thresh: float = 0.15) -> np.ndarray:
    """YIN pitch per 10 ms hop; NaN where unvoiced or quiet."""
    tmin, tmax = int(sr / fmax), int(sr / fmin)
    n = 1 + max(0, (len(audio) - win - tmax) // hop)
    f0 = np.full(n, np.nan)
    yin_f0.aperiodicity = np.full(n, np.nan)
    for i in range(n):
        x = audio[i * hop:i * hop + win + tmax].astype(np.float64)
        frame = x[:win]
        if 20 * np.log10(np.sqrt(np.mean(frame ** 2)) + 1e-10) < -40:
            continue
        d = np.array([np.sum((frame - x[t:t + win]) ** 2) for t in range(tmax + 1)])
        cmnd = np.ones_like(d)
        cmnd[1:] = d[1:] * np.arange(1, tmax + 1) / np.maximum(np.cumsum(d[1:]), 1e-12)
        cand = np.nonzero(cmnd[tmin:] < thresh)[0]
        if not len(cand):
            continue
        t = cand[0] + tmin
        while t + 1 <= tmax and cmnd[t + 1] < cmnd[t]:
            t += 1
        if 1 <= t < tmax:  # parabolic interpolation
            a, b, c = cmnd[t - 1], cmnd[t], cmnd[t + 1]
            t = t + 0.5 * (a - c) / max(a - 2 * b + c, 1e-12)
        f0[i] = sr / t
        yin_f0.aperiodicity[i] = float(np.min(cmnd[tmin:]))
    return f0


def region_stats(audio: np.ndarray, f0: np.ndarray, ap: np.ndarray, lo: float, hi: float,
                 inside: bool) -> dict:
    t = (np.arange(len(f0)) * 240 + 512) / SR
    sel = (t >= lo) & (t < hi) if inside else (t < lo) | (t >= hi)
    voiced = f0[sel & ~np.isnan(f0)]
    aper = ap[sel & ~np.isnan(f0)]
    s = np.arange(len(audio)) / SR
    smask = (s >= lo) & (s < hi) if inside else (s < lo) | (s >= hi)
    x = audio[smask]
    frames = x[:len(x) // 240 * 240].reshape(-1, 240) if len(x) >= 240 else x.reshape(1, -1)
    db = 20 * np.log10(np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)) + 1e-10)
    loud = db[db > -45]
    return {
        'f0_median_hz': round(float(np.median(voiced)), 1) if len(voiced) else None,
        'f0_p90_hz': round(float(np.percentile(voiced, 90)), 1) if len(voiced) else None,
        'rms_db': round(float(20 * np.log10(np.sqrt(np.mean(10 ** (loud / 10))) + 1e-10)), 2) if len(loud) else None,
        'aperiodicity': round(float(np.median(aper)), 3) if len(aper) else None,  # YIN dip: lower = cleaner
        'voiced_hops': int(len(voiced)),
    }


def boundary_f0_jump(f0: np.ndarray, at: float) -> float | None:
    """|F0 change| in semitones between the last voiced hop before `at` and the first after."""
    t = (np.arange(len(f0)) * 240 + 512) / SR
    before = [v for v, x in zip(f0, t) if x < at and not np.isnan(v)][-3:]
    after = [v for v, x in zip(f0, t) if x >= at and not np.isnan(v)][:3]
    if not before or not after:
        return None
    return round(float(abs(12 * np.log2(np.median(after) / np.median(before)))), 2)


def app_renders(tts_engine, out: Path) -> list[dict]:
    """The prototype as the app runs it: prepare_speech() -> app.render_chunk(), flag off and on."""
    import importlib
    import app
    import emphasis
    from normalizer import prepare_speech
    importlib.reload(emphasis)   # the variants above changed its strength constants; back to the defaults
    rows = []
    for sid, md in MARKDOWN.items():
        row = {'sentence': sid, 'markdown': md}
        for state in (False, True):
            emphasis.EMPHASIS_ENABLED = state
            chunks = prepare_speech(md)
            audio = np.concatenate([app.render_chunk(tts_engine, chunks, i, 'af_heart', 1.0)[0]
                                    for i in range(len(chunks))])
            name = 'on' if state else 'off'
            harness.write_wav(out / 'wav' / f'{sid}_app_{name}.wav', audio)
            row[name] = {'seconds': round(len(audio) / SR, 3),
                         'spans': [c.text[a:b] for c in chunks for a, b in c.emphasis]}
        emphasis.EMPHASIS_ENABLED = False
        rows.append(row)
        print(f"app {sid:7s} off {row['off']['seconds']}s  on {row['on']['seconds']}s  spans {row['on']['spans']}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='tests/emphasis')
    args = ap.parse_args()
    out = Path(args.out)
    (out / 'wav').mkdir(parents=True, exist_ok=True)
    harness.setup_logging()
    tts_engine = harness.load_engine()
    pipeline = tts_engine.get_pipeline()

    results = []
    for sid, text, span_text in SENTENCES:
        for vname, opts in VARIANTS.items():
            audio, span_s, ps = render(pipeline, text, span_text, opts)
            harness.write_wav(out / 'wav' / f'{sid}_{vname}.wav', audio)
            f0 = yin_f0(audio)
            lo, hi = span_s
            row = {
                'sentence': sid, 'variant': vname, 'text': text, 'span_text': span_text, 'phonemes': ps,
                'total_s': round(len(audio) / SR, 3), 'span_s': round(hi - lo, 3),
                'span': region_stats(audio, f0, yin_f0.aperiodicity, lo, hi, True),
                'rest': region_stats(audio, f0, yin_f0.aperiodicity, lo, hi, False),
                'f0_jump_in_st': boundary_f0_jump(f0, lo), 'f0_jump_out_st': boundary_f0_jump(f0, hi),
            }
            results.append(row)
            print(f"{sid:7s} {vname:6s} span {row['span_s']:.3f}s F0 {row['span']['f0_median_hz']} "
                  f"RMS {row['span']['rms_db']} | rest F0 {row['rest']['f0_median_hz']} RMS {row['rest']['rms_db']}"
                  f" | jumps {row['f0_jump_in_st']} {row['f0_jump_out_st']}")

    # Change vs base, per sentence, then medians across sentences.
    summary = {}
    base = {r['sentence']: r for r in results if r['variant'] == 'base'}
    for vname in VARIANTS:
        rows = [r for r in results if r['variant'] == vname]
        def d(key, region, r):
            a, b = r[region][key], base[r['sentence']][region][key]
            return None if a is None or b is None else a - b
        def med(vals):
            vals = [v for v in vals if v is not None]
            return round(float(np.median(vals)), 2) if vals else None
        summary[vname] = {
            'span_duration_pct': med([100 * (r['span_s'] / base[r['sentence']]['span_s'] - 1) for r in rows]),
            'span_f0_pct': med([100 * d('f0_median_hz', 'span', r) / base[r['sentence']]['span']['f0_median_hz']
                                if d('f0_median_hz', 'span', r) is not None else None for r in rows]),
            'span_rms_db': med([d('rms_db', 'span', r) for r in rows]),
            'rest_f0_pct': med([100 * d('f0_median_hz', 'rest', r) / base[r['sentence']]['rest']['f0_median_hz']
                                if d('f0_median_hz', 'rest', r) is not None else None for r in rows]),
            'rest_rms_db': med([d('rms_db', 'rest', r) for r in rows]),
            'span_aperiodicity_delta': med([d('aperiodicity', 'span', r) for r in rows]),
            'f0_jump_in_st': med([r['f0_jump_in_st'] for r in rows]),
            'f0_jump_out_st': med([r['f0_jump_out_st'] for r in rows]),
        }
    app_rows = app_renders(tts_engine, out)
    (out / 'emphasis.json').write_text(json.dumps({'env': harness.env_info(), 'summary': summary,
                                                    'results': results, 'app': app_rows},
                                                   indent=1, ensure_ascii=False),
                                       encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
