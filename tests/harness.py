"""Shared helpers for the prosody test scripts: engine loading, recording what
Kokoro receives, passage loading and silence measurement.

Scripts import the app's own modules from src/ so they exercise the same code
the tray app runs. Voice and speed are pinned to the defaults (R1).
"""

import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / 'src'
PASSAGES_DIR = REPO_ROOT / 'tests' / 'passages'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
FRAME_MS = 10           # analysis frame for silence detection
SILENCE_DBFS = -45.0    # frame RMS below this counts as silence
MIN_PAUSE_MS = 60       # shortest internal silent run reported as a pause
WARMUP_TEXT = 'Warming up the engine.'
WORD_RE = re.compile(r'[^\W_]')  # a letter or digit; "_" alone is markdown, not a word


def setup_logging(level: int = logging.WARNING) -> None:
    """Quiet logging for scripts; warnings (e.g. skipped sentences) still show."""
    logging.basicConfig(level=level, format='%(levelname)s [%(name)s] %(message)s')


def load_engine():
    """Initialize tts_engine from src/ and run one warm-up synthesis."""
    import tts_engine
    tts_engine.init()
    list(tts_engine.synthesize(WARMUP_TEXT, voice=tts_engine.DEFAULT_VOICE, speed=tts_engine.DEFAULT_SPEED))
    return tts_engine


class RecordingPipeline:
    """Forwards to a KPipeline and records every segment it yields.

    Each record holds the graphemes and phonemes Kokoro actually synthesized,
    so tests can see exactly what text reached the model.
    """

    def __init__(self, pipeline) -> None:
        self._pipeline = pipeline
        self.records: list[dict] = []

    def __call__(self, *args, **kwargs):
        for result in self._pipeline(*args, **kwargs):
            audio = result.audio
            self.records.append({
                'graphemes': result.graphemes,
                'phonemes': result.phonemes,
                # Words that reached Kokoro but got no phonemes are silently not spoken (R4).
                'silent_words': [t.text for t in (result.tokens or [])
                                 if WORD_RE.search(t.text) and not t.phonemes],
                'samples': 0 if audio is None else int(len(audio)),
                'audio': None if audio is None else np.asarray(audio, dtype=np.float32),
            })
            yield result

    def __getattr__(self, name):
        return getattr(self._pipeline, name)


def install_recorder(tts_engine) -> RecordingPipeline:
    """Route tts_engine.synthesize() through a RecordingPipeline."""
    recorder = RecordingPipeline(tts_engine.get_pipeline())
    tts_engine.get_pipeline = lambda: recorder
    return recorder


def load_manifest() -> list[dict]:
    """Return passage entries from tests/passages/manifest.json, with text attached."""
    entries = json.loads((PASSAGES_DIR / 'manifest.json').read_text(encoding='utf-8'))
    for entry in entries:
        entry['text'] = (PASSAGES_DIR / f"{entry['id']}.txt").read_text(encoding='utf-8')
    return entries


def frame_dbfs(audio: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """RMS level of each FRAME_MS frame in dBFS."""
    n = int(sr * FRAME_MS / 1000)
    frames = len(audio) // n
    if frames == 0:
        return np.array([])
    x = audio[:frames * n].reshape(frames, n).astype(np.float64)
    rms = np.sqrt(np.mean(x * x, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-10))


def edge_silence_ms(audio: np.ndarray, sr: int = SAMPLE_RATE) -> tuple[float, float]:
    """Leading and trailing silence of a clip, in ms."""
    loud = np.nonzero(frame_dbfs(audio, sr) > SILENCE_DBFS)[0]
    total = len(audio) / sr * 1000
    if len(loud) == 0:
        return total, total
    lead = loud[0] * FRAME_MS
    trail = total - (loud[-1] + 1) * FRAME_MS
    return float(lead), float(max(trail, 0.0))


def internal_pauses(audio: np.ndarray, sr: int = SAMPLE_RATE, min_ms: int = MIN_PAUSE_MS) -> list[dict]:
    """Silent runs of at least min_ms between the first and last loud frame."""
    db = frame_dbfs(audio, sr)
    loud = np.nonzero(db > SILENCE_DBFS)[0]
    if len(loud) < 2:
        return []
    pauses = []
    run_start = None
    for i in range(loud[0], loud[-1] + 1):
        if db[i] <= SILENCE_DBFS:
            run_start = i if run_start is None else run_start
        elif run_start is not None:
            dur = (i - run_start) * FRAME_MS
            if dur >= min_ms:
                pauses.append({'at_ms': run_start * FRAME_MS, 'ms': dur})
            run_start = None
    return pauses


def write_wav(path: Path, audio: np.ndarray, sr: int = SAMPLE_RATE) -> str:
    """Write 16-bit PCM WAV and return its sha256."""
    import soundfile as sf
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sr, subtype='PCM_16')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def env_info() -> dict:
    """Versions and device facts recorded alongside every artifact."""
    import torch
    import kokoro
    import misaki
    return {
        'python': sys.version.split()[0],
        'torch': torch.__version__,
        'cuda_available': torch.cuda.is_available(),
        'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        'kokoro': getattr(kokoro, '__version__', '?'),
        'misaki': getattr(misaki, '__version__', '?'),
        'force_cpu': os.environ.get('FORCE_CPU', ''),
    }
