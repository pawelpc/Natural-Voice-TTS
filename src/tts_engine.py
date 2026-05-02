"""Kokoro TTS engine wrapper: model loading, synthesis, GPU/CPU fallback."""

import os
import sys
import logging
import time

logger = logging.getLogger(__name__)

# --- espeak-ng setup (MUST happen before importing kokoro) ---
# Check for bundled espeak-ng first (PyInstaller frozen mode)
if getattr(sys, 'frozen', False):
    _base_dir = os.path.dirname(sys.executable)
    _espeak_bundled = os.path.join(_base_dir, 'espeak-ng')
    if os.path.exists(_espeak_bundled):
        os.environ.setdefault(
            'PHONEMIZER_ESPEAK_LIBRARY',
            os.path.join(_espeak_bundled, 'libespeak-ng.dll'),
        )
        os.environ.setdefault(
            'PHONEMIZER_ESPEAK_PATH',
            os.path.join(_espeak_bundled, 'espeak-ng.exe'),
        )
        logger.info("espeak-ng found in bundle at %s", _espeak_bundled)

# Fall back to system-installed espeak-ng (uses setdefault so bundled wins)
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
# In frozen mode, allow downloads for voices not bundled
if not getattr(sys, 'frozen', False):
    os.environ.setdefault('HF_HUB_OFFLINE', '1')

import numpy as np
import torch
from kokoro import KPipeline, KModel

# Constants
SAMPLE_RATE = 24000
DEFAULT_VOICE = 'af_heart'
DEFAULT_SPEED = 1.0
DEFAULT_LANG = 'a'  # American English
SPLIT_PATTERN = r'[.!?\n]+'

# Module-level pipeline (initialized lazily)
_pipeline: KPipeline | None = None


def _get_device() -> str:
    """Detect best available device. Logs full torch version and CUDA info."""
    # Log full torch version string with build info (e.g., +cu121, +cpu)
    logger.info("Torch version: %s", torch.__version__)

    # Log CUDA toolkit version if available
    if hasattr(torch.version, 'cuda') and torch.version.cuda:
        logger.info("CUDA toolkit version: %s", torch.version.cuda)
    else:
        logger.info("CUDA toolkit version: Not available")

    # Allow forcing CPU mode for debugging
    if os.environ.get('FORCE_CPU', '').lower() in ('1', 'true', 'yes'):
        logger.info("FORCE_CPU set — using CPU even if GPU is available")
        return 'cpu'

    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        logger.info("Using GPU: %s", device_name)
        return 'cuda'

    logger.warning("CUDA not available — falling back to CPU (slower)")
    # Log extra diagnostic info for frozen mode
    if getattr(sys, 'frozen', False):
        logger.warning("Running in frozen mode — check that CUDA torch was bundled (not CPU-only)")
        logger.warning("Look for c10_cuda.dll in _internal/torch/lib/")
    return 'cpu'


def _get_bundled_model_dir() -> str | None:
    """Return the bundled kokoro_model directory if running frozen."""
    if getattr(sys, 'frozen', False):
        model_dir = os.path.join(os.path.dirname(sys.executable), 'kokoro_model')
        if os.path.isdir(model_dir):
            logger.info("Found bundled model at %s", model_dir)
            return model_dir
    return None


def _benchmark_gpu() -> None:
    """Run a quick GPU benchmark to ensure CUDA is working."""
    if not torch.cuda.is_available():
        return

    try:
        logger.info("Running GPU benchmark...")
        start = time.time()

        # Create a small tensor on GPU and do a simple operation
        test_tensor = torch.randn(100, 100, device='cuda')
        result = torch.matmul(test_tensor, test_tensor)
        torch.cuda.synchronize()  # Wait for GPU computation to finish

        elapsed = time.time() - start
        logger.info("GPU benchmark completed in %.3f seconds", elapsed)

        if elapsed > 1.0:
            logger.warning("GPU benchmark was slow (%.3f s) — possible driver or CUDA issue", elapsed)
    except Exception as e:
        logger.warning("GPU benchmark failed: %s", e)


def init(lang_code: str = DEFAULT_LANG) -> KPipeline:
    """Initialize the Kokoro pipeline. Call once at startup."""
    global _pipeline
    device = _get_device()

    # Run GPU benchmark if CUDA is available
    if device == 'cuda':
        _benchmark_gpu()

    try:
        bundled = _get_bundled_model_dir()
        if bundled:
            # Frozen mode: load model from bundled files
            config_path = os.path.join(bundled, 'config.json')
            model_path = os.path.join(bundled, 'kokoro-v1_0.pth')
            logger.info("Loading bundled model: %s", model_path)
            model = KModel(
                repo_id='hexgrad/Kokoro-82M',
                config=config_path,
                model=model_path,
            )

            # CRITICAL: Explicitly move model to the correct device
            # In frozen mode, auto-detection might fail, so we force it
            model = model.to(device)
            logger.info("Model moved to device: %s", device)

            _pipeline = KPipeline(lang_code=lang_code, model=model)

            # Patch voice loading to use bundled voices directory WITH CACHING
            # The original load_single_voice is called on every synthesis call,
            # so caching prevents re-reading the .pt file from disk each sentence.
            _original_load = _pipeline.load_single_voice
            voices_dir = os.path.join(bundled, 'voices')
            _voice_cache: dict = {}

            def _patched_load(voice: str, _orig=_original_load, _vdir=voices_dir, _cache=_voice_cache):
                # Return cached voice if already loaded
                if voice in _cache:
                    logger.debug("Using cached voice: %s", voice)
                    return _cache[voice]

                local_pt = os.path.join(_vdir, f'{voice}.pt')
                if os.path.exists(local_pt):
                    logger.info("Loading bundled voice (first time): %s", local_pt)
                    result = _orig(local_pt)
                else:
                    logger.info("Voice %s not bundled, downloading from HuggingFace", voice)
                    result = _orig(voice)

                # Cache the loaded voice for subsequent calls
                _cache[voice] = result
                logger.info("Voice '%s' cached (%d voices in cache)", voice, len(_cache))
                return result

            _pipeline.load_single_voice = _patched_load
        else:
            # Source mode: let KPipeline download from HuggingFace cache
            _pipeline = KPipeline(lang_code=lang_code)

            # Try to move to device if model is accessible
            if hasattr(_pipeline, 'model') and _pipeline.model is not None:
                _pipeline.model = _pipeline.model.to(device)
                logger.info("Pipeline model moved to device: %s", device)

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
    Logs timing information to detect CPU fallback or performance issues.
    """
    pipeline = get_pipeline()
    # Use cached device knowledge instead of re-detecting each call
    is_cuda = torch.cuda.is_available()

    try:
        start_time = time.time()
        chunk_count = 0
        total_samples = 0

        for graphemes, phonemes, audio in pipeline(
            text,
            voice=voice,
            speed=speed,
            split_pattern=SPLIT_PATTERN,
        ):
            if audio is not None and len(audio) > 0:
                chunk_count += 1
                total_samples += len(audio)
                yield graphemes, audio

        elapsed = time.time() - start_time
        audio_duration = total_samples / SAMPLE_RATE if chunk_count > 0 else 0

        # Log warning if synthesis is unexpectedly slow (suggests CPU fallback)
        if is_cuda and elapsed > 2.0 and audio_duration < 10:
            logger.warning(
                "Synthesis took %.2f seconds for %.1fs audio on GPU — possible CPU fallback",
                elapsed, audio_duration
            )
        else:
            logger.debug("Synthesis: %.2fs wall time, %.1fs audio, %d chunks", elapsed, audio_duration, chunk_count)

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
