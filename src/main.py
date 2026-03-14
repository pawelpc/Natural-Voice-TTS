"""Natural Voice TTS — Entry point for Phase 1 (MVP).

Wires together: hotkeys → clipboard grab → text processing → Kokoro TTS → audio playback.
"""

import queue
import threading
import logging
import sys

from text_processor import split_sentences
from audio_player import play_audio, stop as audio_stop, toggle_pause, reset as audio_reset, is_stopped
from hotkeys import grab_selected_text, register_hotkeys, unregister_hotkeys

logger = logging.getLogger(__name__)

# Queue for text to be read aloud
_text_queue: queue.Queue[str] = queue.Queue()


def _worker() -> None:
    """Background worker: consumes text from queue, synthesizes, and plays audio.

    Runs as a daemon thread. Implements 1-sentence lookahead to reduce gaps.
    """
    # Import tts_engine here so espeak-ng env vars are set before kokoro loads
    import tts_engine

    logger.info("TTS worker thread started")

    while True:
        # Block until text is available
        text = _text_queue.get()
        if text is None:  # Poison pill for shutdown
            break

        logger.info("Processing text (%d chars)", len(text))
        audio_reset()

        sentences = split_sentences(text)
        if not sentences:
            logger.info("No sentences to read")
            continue

        logger.info("Reading %d sentences", len(sentences))

        # Lookahead: pre-synthesize the next sentence while playing current
        pending_audio = None
        pending_label = None

        for i, sentence in enumerate(sentences):
            if is_stopped():
                logger.info("Stopped — clearing remaining sentences")
                break

            # Use lookahead audio if available, otherwise synthesize now
            if pending_audio is not None:
                current_audio = pending_audio
                current_label = pending_label
                pending_audio = None
                pending_label = None
            else:
                current_audio = _synthesize_sentence(tts_engine, sentence)
                current_label = sentence

            if current_audio is None:
                continue

            # Start synthesizing the next sentence (lookahead)
            next_sentence = sentences[i + 1] if i + 1 < len(sentences) else None
            if next_sentence and not is_stopped():
                pending_audio = _synthesize_sentence(tts_engine, next_sentence)
                pending_label = next_sentence

            # Play current sentence
            logger.info("Playing [%d/%d]: %.60s...", i + 1, len(sentences), current_label)
            completed = play_audio(current_audio)
            if not completed:
                logger.info("Playback interrupted at sentence %d/%d", i + 1, len(sentences))
                break

        logger.info("Finished reading")


def _synthesize_sentence(tts_engine, sentence: str):
    """Synthesize a single sentence, returning the audio array or None on error."""
    import numpy as np

    try:
        chunks = list(tts_engine.synthesize(sentence))
        if chunks:
            return np.concatenate([audio for _, audio in chunks])
    except Exception:
        logger.exception("Failed to synthesize: %.60s...", sentence)
    return None


def _on_read() -> None:
    """Hotkey callback: grab selected text and queue it for reading."""
    text = grab_selected_text()
    if text:
        # Stop any current reading before starting new
        audio_stop()
        # Drain the queue
        while not _text_queue.empty():
            try:
                _text_queue.get_nowait()
            except queue.Empty:
                break
        _text_queue.put(text)
    else:
        logger.info("No text selected")


def _on_stop() -> None:
    """Hotkey callback: stop reading."""
    audio_stop()
    # Drain the queue
    while not _text_queue.empty():
        try:
            _text_queue.get_nowait()
        except queue.Empty:
            break
    logger.info("Reading stopped by user")


def _on_pause() -> None:
    """Hotkey callback: toggle pause/resume."""
    toggle_pause()


def main() -> None:
    """Initialize and run the TTS application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    logger.info("=== Natural Voice TTS (Phase 1 MVP) ===")
    logger.info("Initializing TTS engine (first run may download model ~350 MB)...")

    # Pre-load the TTS engine in the main thread to catch errors early
    try:
        import tts_engine
        tts_engine.init()
    except Exception:
        logger.exception("Failed to initialize TTS engine. Check espeak-ng and CUDA setup.")
        sys.exit(1)

    logger.info("TTS engine ready")

    # Start background worker thread
    worker = threading.Thread(target=_worker, daemon=True, name='tts-worker')
    worker.start()

    # Register hotkeys
    register_hotkeys(_on_read, _on_stop, _on_pause)

    logger.info("Ready! Select text in any window and press Ctrl+Shift+Win+R to read.")
    logger.info("Ctrl+Shift+Win+S = Stop | Ctrl+Shift+Win+P = Pause/Resume")
    logger.info("Press Ctrl+C in this terminal to quit.")

    try:
        import keyboard
        keyboard.wait()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down...")
        audio_stop()
        unregister_hotkeys()
        _text_queue.put(None)  # Poison pill to stop worker
        worker.join(timeout=2)
        logger.info("Goodbye!")


if __name__ == '__main__':
    main()
