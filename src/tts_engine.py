"""Kokoro TTS engine wrapper: model loading, synthesis, GPU/CPU fallback."""

import os
import sys
import logging

logger = logging.getLogger(__name__)

# --- espeak-ng setup (MUST happen before importing kokoro) ---
if sys.platform == 'win32':
    _espeak_candidates = [
        r'C:\Program Files\eSpeak NG',
        r'C:\Program Files (x86)\eSpeak NG',
    ]
    for _path in _espeak_candidates:
        if os.path.exists(_path):
            os.environ.setdefault(
                'PHONEMIZER_ESPEAK_LIBRARY',
                os.path.join(_path, 'libespeak-ng.dll'),
            )
            os.environ.setdefault(
                'PHONEMIZER_ESPEAK_PATH',
                os.path.join(_path, 'espeak-ng.exe'),
            )
            logger.info("espeak-ng found at %s", _path)
            break
    else:
        logger.warning(
            "espeak-ng not found in standard locations. "
            "Install from https://github.com/espeak-ng/espeak-ng/releases "
            "or set PHONEMIZER_ESPEAK_LIBRARY / PHONEMIZER_ESPEAK_PATH manually."
        )

# Force Hugging Face to use cached files only (no network calls after first download)
os.environ.setdefault('HF_HUB_OFFLINE', '1')

import numpy as np
import torch
from kokoro import KPipeline

# Constants
SAMPLE_RATE = 24000
DEFAULT_VOICE = 'af_heart'
DEFAULT_SPEED = 1.0
DEFAULT_LANG = 'a'  # American English
SPLIT_PATTERN = r'[.!?\n]+'

# Module-level pipeline (initialized lazily)
_pipeline: KPipeline | None = None


def _get_device() -> str:
    """Detect best available device."""
    if torch.cuda.is_available():
        logger.info("Using GPU: %s", torch.cuda.get_device_name(0))
        return 'cuda'
    logger.warning("CUDA not available — falling back to CPU (slower)")
    return 'cpu'


def init(lang_code: str = DEFAULT_LANG) -> KPipeline:
    """Initialize the Kokoro pipeline. Call once at startup."""
    global _pipeline
    device = _get_device()
    try:
        _pipeline = KPipeline(lang_code=lang_code)
        logger.info("Kokoro pipeline initialized (lang=%s, device=%s)", lang_code, device)
    except Exception:
        logger.exception("Failed to initialize Kokoro pipeline")
        raise
    return _pipeline


def get_pipeline() -> KPipeline:
    """Return the initialized pipeline, or init with defaults."""
    if _pipeline is None:
        return init()
    return _pipeline


def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
) -> 'Generator[tuple[str, np.ndarray], None, None]':
    """Synthesize text into audio chunks.

    Yields (graphemes, audio) tuples where audio is a float32 numpy array at 24 kHz.
    """
    pipeline = get_pipeline()
    try:
        for graphemes, phonemes, audio in pipeline(
            text,
            voice=voice,
            speed=speed,
            split_pattern=SPLIT_PATTERN,
        ):
            if audio is not None and len(audio) > 0:
                yield graphemes, audio
    except Exception:
        logger.exception("Synthesis error")
        raise


if __name__ == '__main__':
    import soundfile as sf

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    test_text = "Hello! This is a test of the Kokoro text-to-speech engine. It should sound natural and clear."
    logger.info("Synthesizing test text...")

    init()
    chunks = list(synthesize(test_text))
    logger.info("Generated %d audio chunks", len(chunks))

    if chunks:
        # Concatenate all chunks and save
        all_audio = np.concatenate([audio for _, audio in chunks])
        out_path = 'test_output.wav'
        sf.write(out_path, all_audio, SAMPLE_RATE)
        logger.info("Saved to %s (%.1f seconds)", out_path, len(all_audio) / SAMPLE_RATE)
