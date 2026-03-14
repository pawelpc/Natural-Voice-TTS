"""Audio playback with stop, pause, and resume controls using sounddevice."""

import threading
import logging
import time

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000
POLL_INTERVAL = 0.05  # 50ms

# Threading events for playback control
_stop_event = threading.Event()
_pause_event = threading.Event()
_pause_event.set()  # Not paused initially
_lock = threading.Lock()


def play_audio(audio: np.ndarray, sr: int = SAMPLE_RATE) -> bool:
    """Play an audio array through the default output device.

    Blocks until playback completes, is stopped, or errors.
    Respects stop and pause events.

    Returns True if playback completed normally, False if stopped.
    """
    if _stop_event.is_set():
        return False

    try:
        sd.play(audio, samplerate=sr)
    except sd.PortAudioError as e:
        logger.error("Audio device error: %s. Check your sound output settings.", e)
        return False
    except Exception:
        logger.exception("Failed to start audio playback")
        return False

    # Poll until playback finishes, checking stop/pause
    while sd.get_stream().active:
        if _stop_event.is_set():
            sd.stop()
            return False

        if not _pause_event.is_set():
            # Paused: stop current playback, wait for resume
            sd.stop()
            _pause_event.wait()  # Block until resumed or stopped
            if _stop_event.is_set():
                return False
            # Resume: replay from where we left off is not trivial with sd.play,
            # so we accept the tradeoff of restarting the current chunk
            # In practice, chunks are short sentences so this is acceptable
            try:
                sd.play(audio, samplerate=sr)
            except sd.PortAudioError as e:
                logger.error("Audio device error on resume: %s", e)
                return False
            except Exception:
                logger.exception("Failed to resume audio playback")
                return False

        time.sleep(POLL_INTERVAL)

    return True


def stop():
    """Stop all audio playback immediately."""
    with _lock:
        _stop_event.set()
        _pause_event.set()  # Unblock any pause wait
        sd.stop()
    logger.info("Playback stopped")


def pause():
    """Pause audio playback."""
    with _lock:
        _pause_event.clear()
    logger.info("Playback paused")


def resume():
    """Resume audio playback."""
    with _lock:
        _pause_event.set()
    logger.info("Playback resumed")


def toggle_pause():
    """Toggle between paused and playing states."""
    with _lock:
        if _pause_event.is_set():
            _pause_event.clear()
            logger.info("Playback paused")
        else:
            _pause_event.set()
            logger.info("Playback resumed")


def reset():
    """Reset playback state for a new reading session."""
    with _lock:
        _stop_event.clear()
        _pause_event.set()


def is_stopped() -> bool:
    """Check if stop has been requested."""
    return _stop_event.is_set()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    # Generate a 2-second test tone (440 Hz sine wave)
    duration = 2.0
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    logger.info("Playing 2-second test tone (440 Hz)...")
    logger.info("Press Ctrl+C to stop")

    try:
        completed = play_audio(tone)
        if completed:
            logger.info("Playback completed normally")
        else:
            logger.info("Playback was stopped")
    except KeyboardInterrupt:
        stop()
        logger.info("Interrupted by user")
