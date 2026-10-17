# Prosody tests

Scripts that render and measure how the app speaks. They import the app's own
modules from `src/`, pin the voice to `af_heart` at speed 1.0, and load the
Kokoro model from `dist/NaturalVoiceTTS/kokoro_model` (or `NVTTS_MODEL_DIR`).

| Script | What it does | Output |
|---|---|---|
| `render_passages.py` | Speaks every passage the way the app does and saves WAVs plus what Kokoro received | `<out>/wav/*.wav` (gitignored), `<out>/meta/*.json`, `<out>/render_summary.json` |
| `measure_ttfa.py` | Runs the real `app._worker` (player replaced by a sleep), measures time to first audio and gaps between chunks | `<out>/ttfa.json` |
| `measure_device.py` | Plays silence through the real `play_audio()` to measure the sound device's added delay | `<out>/device_overhead.json` |
| `probe_hypotheses.py` | Phase 0 evidence for H1–H4 | `<out>/hypotheses.json`, `<out>/probe/*.wav` |

Passages live in `passages/` (one category each, provenance in `manifest.json`).

Phase 0 baseline, from the repo root:

```bash
python tests/render_passages.py --out tests/baseline
python tests/measure_ttfa.py --out tests/baseline/ttfa.json
python tests/measure_device.py --out tests/baseline/device_overhead.json
python tests/probe_hypotheses.py --baseline tests/baseline
```

Don't run two of these at once: they share the GPU, and that skews the timings.
