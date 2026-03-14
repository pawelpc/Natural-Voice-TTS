"""Natural Voice TTS — System tray application.

Runs as a Windows tray app with right-click menu for voice/speed selection,
playback controls, and persistent settings.
"""

import os
import sys
import queue
import threading
import logging

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pystray
from PIL import Image

import config
from text_processor import split_sentences
from audio_player import (
    play_audio, stop as audio_stop, toggle_pause,
    reset as audio_reset, is_stopped,
)
import pyperclip
from hotkeys import grab_selected_text, register_hotkeys, unregister_hotkeys

logger = logging.getLogger(__name__)


def _notify(title: str, message: str) -> None:
    """Show a brief tray balloon notification (Windows only)."""
    try:
        if _icon is not None:
            _icon.notify(message, title)
    except Exception:
        logger.debug("Notification failed: %s - %s", title, message)


# Playback state for tooltip and menu
_status = 'Idle'
_status_lock = threading.Lock()
_text_queue: queue.Queue[str | None] = queue.Queue()
_icon: pystray.Icon | None = None


def _set_status(status: str) -> None:
    """Update the playback status and tray tooltip."""
    global _status
    with _status_lock:
        _status = status
    if _icon is not None:
        _icon.title = f'Natural Voice TTS — {status}'
    logger.info("Status: %s", status)


def _get_status() -> str:
    with _status_lock:
        return _status


# --- TTS Worker Thread ---

def _worker() -> None:
    """Background worker: synthesize and play text from the queue."""
    import tts_engine
    import numpy as np

    logger.info("TTS worker thread started")

    while True:
        text = _text_queue.get()
        if text is None:
            break

        logger.info("Processing text (%d chars)", len(text))
        audio_reset()
        _set_status('Reading...')

        sentences = split_sentences(text)
        if not sentences:
            _set_status('Idle')
            continue

        logger.info("Reading %d sentences", len(sentences))

        # Read voice/speed from config at start of each read
        voice = config.get('voice')
        speed = config.get('speed')

        pending_audio = None
        pending_label = None

        for i, sentence in enumerate(sentences):
            if is_stopped():
                break

            if pending_audio is not None:
                current_audio = pending_audio
                current_label = pending_label
                pending_audio = None
                pending_label = None
            else:
                current_audio = _synthesize_sentence(tts_engine, sentence, voice, speed)
                current_label = sentence

            if current_audio is None:
                continue

            # Lookahead
            next_sentence = sentences[i + 1] if i + 1 < len(sentences) else None
            if next_sentence and not is_stopped():
                pending_audio = _synthesize_sentence(tts_engine, next_sentence, voice, speed)
                pending_label = next_sentence

            logger.info("Playing [%d/%d]: %.60s...", i + 1, len(sentences), current_label)
            completed = play_audio(current_audio)
            if not completed:
                break

        _set_status('Idle')
        logger.info("Finished reading")


def _synthesize_sentence(tts_engine, sentence: str, voice: str, speed: float):
    """Synthesize a single sentence, returning the audio array or None."""
    import numpy as np
    try:
        chunks = list(tts_engine.synthesize(sentence, voice=voice, speed=speed))
        if chunks:
            return np.concatenate([audio for _, audio in chunks])
    except Exception:
        logger.exception("Failed to synthesize: %.60s...", sentence)
    return None


# --- Hotkey Callbacks ---

def _on_read() -> None:
    text = grab_selected_text()
    if text:
        audio_stop()
        while not _text_queue.empty():
            try:
                _text_queue.get_nowait()
            except queue.Empty:
                break
        _text_queue.put(text)
    else:
        logger.info("No text selected")
        _notify('Natural Voice TTS', 'No text selected. Highlight text first.')


def _on_stop() -> None:
    audio_stop()
    while not _text_queue.empty():
        try:
            _text_queue.get_nowait()
        except queue.Empty:
            break
    _set_status('Idle')


def _on_pause() -> None:
    toggle_pause()
    if _get_status() == 'Paused':
        _set_status('Reading...')
    elif _get_status() == 'Reading...':
        _set_status('Paused')


# --- Tray Menu Callbacks ---

def _on_menu_read(icon, item):
    """Read from clipboard (not selection) since clicking the menu loses focus."""
    text = pyperclip.paste()
    if text:
        audio_stop()
        while not _text_queue.empty():
            try:
                _text_queue.get_nowait()
            except queue.Empty:
                break
        _text_queue.put(text)
        logger.info("Reading clipboard text (%d chars)", len(text))
    else:
        logger.info("Clipboard is empty")
        _notify('Natural Voice TTS', 'Clipboard is empty. Copy some text first.')


def _on_menu_stop(icon, item):
    _on_stop()


def _on_menu_pause(icon, item):
    _on_pause()


def _on_menu_quit(icon, item):
    logger.info("Quit requested")
    audio_stop()
    unregister_hotkeys()
    _text_queue.put(None)
    icon.stop()


# --- Auto-start with Windows ---

def _get_startup_shortcut_path() -> str:
    """Return the path for the startup folder shortcut."""
    startup = os.path.join(
        os.environ.get('APPDATA', ''),
        'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup',
    )
    return os.path.join(startup, 'NaturalVoiceTTS.bat')


def _is_autostart_enabled() -> bool:
    return os.path.exists(_get_startup_shortcut_path())


def _toggle_autostart(icon, item):
    """Toggle auto-start on Windows login."""
    shortcut_path = _get_startup_shortcut_path()
    if _is_autostart_enabled():
        try:
            os.remove(shortcut_path)
            logger.info("Auto-start disabled")
            _notify('Natural Voice TTS', 'Auto-start disabled.')
        except OSError:
            logger.exception("Failed to remove startup shortcut")
    else:
        # Create a .bat file that runs app.py with the correct python
        python_exe = sys.executable
        app_path = os.path.abspath(__file__)
        try:
            with open(shortcut_path, 'w') as f:
                f.write(f'@echo off\nstart "" /min "{python_exe}" "{app_path}"\n')
            logger.info("Auto-start enabled: %s", shortcut_path)
            _notify('Natural Voice TTS', 'Auto-start enabled. App will launch on login.')
        except OSError:
            logger.exception("Failed to create startup shortcut")


def _make_voice_callback(voice_id: str):
    def callback(icon, item):
        config.set('voice', voice_id)
    return callback


def _make_speed_callback(speed: float):
    def callback(icon, item):
        config.set('speed', speed)
    return callback


def _is_voice_selected(voice_id: str):
    def check(item):
        return config.get('voice') == voice_id
    return check


def _is_speed_selected(speed: float):
    def check(item):
        return config.get('speed') == speed
    return check


# --- Menu Builder ---

def _build_menu() -> pystray.Menu:
    """Build the tray right-click menu."""
    # Voice submenus grouped by category
    voice_items = []
    for category, voices in config.VOICES.items():
        sub_items = []
        for v in voices:
            sub_items.append(
                pystray.MenuItem(
                    v,
                    _make_voice_callback(v),
                    checked=_is_voice_selected(v),
                    radio=True,
                )
            )
        voice_items.append(pystray.MenuItem(category, pystray.Menu(*sub_items)))

    # Speed submenu
    speed_items = []
    for s in config.SPEED_OPTIONS:
        label = f'{s}x'
        speed_items.append(
            pystray.MenuItem(
                label,
                _make_speed_callback(s),
                checked=_is_speed_selected(s),
                radio=True,
            )
        )

    return pystray.Menu(
        pystray.MenuItem('Voice', pystray.Menu(*voice_items)),
        pystray.MenuItem('Speed', pystray.Menu(*speed_items)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Read Clipboard', _on_menu_read),
        pystray.MenuItem('Stop', _on_menu_stop),
        pystray.MenuItem('Pause / Resume', _on_menu_pause),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            'Start with Windows',
            _toggle_autostart,
            checked=lambda item: _is_autostart_enabled(),
        ),
        pystray.MenuItem('Quit', _on_menu_quit),
    )


# --- Setup & Main ---

def _on_setup(icon: pystray.Icon) -> None:
    """Called when the tray icon is ready. Initialize TTS and hotkeys."""
    icon.visible = True

    logger.info("Initializing TTS engine...")
    try:
        import tts_engine
        tts_engine.init()
    except FileNotFoundError as e:
        msg = f"espeak-ng not found: {e}\nInstall from https://github.com/espeak-ng/espeak-ng/releases"
        logger.error(msg)
        _notify('TTS Engine Error', 'espeak-ng not found. Install it and restart.')
        icon.stop()
        return
    except Exception as e:
        msg = f"TTS engine failed to load: {e}\nCheck CUDA drivers and espeak-ng installation."
        logger.exception(msg)
        _notify('TTS Engine Error', 'Failed to load TTS model. Check logs.')
        icon.stop()
        return

    logger.info("TTS engine ready")

    # Start worker thread
    worker = threading.Thread(target=_worker, daemon=True, name='tts-worker')
    worker.start()

    # Register hotkeys
    register_hotkeys(_on_read, _on_stop, _on_pause)

    logger.info("Ready! Ctrl+Shift+Win+R = Read | Ctrl+Shift+Win+S = Stop | Ctrl+Shift+Win+P = Pause")


def main() -> None:
    """Launch the system tray application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    logger.info("=== Natural Voice TTS (Phase 2 — System Tray) ===")

    # Load config
    config.load()

    # Load icon
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'icon.ico')
    if os.path.exists(icon_path):
        image = Image.open(icon_path)
    else:
        # Fallback: generate a simple icon in memory
        image = Image.new('RGB', (64, 64), (50, 120, 220))
        logger.warning("Icon file not found at %s, using fallback", icon_path)

    global _icon
    _icon = pystray.Icon(
        name='NaturalVoiceTTS',
        icon=image,
        title='Natural Voice TTS — Idle',
        menu=_build_menu(),
    )

    # run() blocks the main thread; setup runs in a separate thread
    _icon.run(setup=_on_setup)

    logger.info("Goodbye!")


if __name__ == '__main__':
    main()
