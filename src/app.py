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
import pauses
from normalizer import prepare_speech
from audio_player import (
    play_audio, stop as audio_stop, toggle_pause,
    reset as audio_reset, is_stopped,
)
import pyperclip
from hotkeys import grab_selected_text, register_hotkeys, unregister_hotkeys
from dialogs import show_help, show_about
import pipe_listener

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
_pipe_stop_event = threading.Event()


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

PREFETCH_CHUNKS = 2       # chunks synthesized ahead of the one playing
_READ_DONE = object()     # producer -> player: no more chunks for this read
_synth_lock = threading.Lock()  # one synthesis at a time, even across a stop and a new read


def speech_chunks(text: str) -> list[str]:
    """The chunks the worker speaks for this text, in order.

    A normalized copy for speech only: the text on screen is never changed (R5).
    """
    return [s.text for s in prepare_speech(text)]


def render_chunk(tts_engine, chunks: list, i: int, voice: str, speed: float):
    """Synthesize chunk i and shape its pauses (pauses.shape_chunk).

    Returns (audio, pause_marks); audio is None when nothing could be produced.
    """
    text = chunks[i].text
    # Emphasized words (emphasis.py, off by default) take a separate synthesis path.
    spans = chunks[i].emphasis
    extra = {'emphasis_spans': spans} if spans else {}
    try:
        with _synth_lock:
            segments = [(audio, tokens, graphemes) for graphemes, audio, tokens
                        in tts_engine.synthesize_segments(text, voice=voice, speed=speed, **extra)]
    except Exception:
        logger.exception("Failed to synthesize: %.60s...", text)
        return None, []
    if not segments:
        # No exception, but the engine produced no audio — previously a silent
        # drop. Surface it so the caller's skip is explainable in the log.
        logger.warning("Synthesis produced no audio for: %.80s", text)
        return None, []
    kind, pause_ms = pauses.pause_after(chunks, i)
    audio, marks = pauses.shape_chunk(segments, kind, pause_ms)
    if len(audio) == 0:
        logger.warning("Synthesis produced only silence for: %.80s", text)
        return None, []
    return audio, marks


def _produce(tts_engine, chunks: list, voice: str, speed: float,
             ready: queue.Queue, cancel: threading.Event) -> None:
    """Synthesize chunks in order into `ready` while earlier ones play."""
    for i in range(len(chunks)):
        if cancel.is_set():
            return
        audio, _ = render_chunk(tts_engine, chunks, i, voice, speed)
        while not cancel.is_set():
            try:
                ready.put((i, audio), timeout=0.1)
                break
            except queue.Full:
                continue
    while not cancel.is_set():
        try:
            ready.put(_READ_DONE, timeout=0.1)
            return
        except queue.Full:
            continue


def _worker() -> None:
    """Background worker: synthesize and play text from the queue.

    A producer thread synthesizes the next chunks while the current one plays,
    so the pause between sentences is the deliberate one from pauses.py, not
    the time it takes to synthesize a later sentence (Phase 0, H4).
    """
    import tts_engine

    logger.info("TTS worker thread started")

    while True:
        text = _text_queue.get()
        if text is None:
            break

        logger.info("Processing text (%d chars)", len(text))
        # Diagnostic: head/tail of the received text so a dropped tail sentence
        # is visible in the log (compare against what was sent via speak()).
        if len(text) > 200:
            logger.debug("Text head: %.100s", text)
            logger.debug("Text tail: %.100s", text[-100:])
        else:
            logger.debug("Text: %s", text)
        audio_reset()
        _set_status('Reading...')

        chunks = prepare_speech(text)
        if not chunks:
            _set_status('Idle')
            continue

        logger.info("Reading %d sentences", len(chunks))

        skipped = 0

        # Read voice/speed from config at start of each read
        voice = config.get('voice')
        speed = config.get('speed')

        ready: queue.Queue = queue.Queue(maxsize=PREFETCH_CHUNKS)
        cancel = threading.Event()
        producer = threading.Thread(
            target=_produce, args=(tts_engine, chunks, voice, speed, ready, cancel),
            daemon=True, name='tts-synth',
        )
        producer.start()
        try:
            while True:
                item = ready.get()
                if item is _READ_DONE or is_stopped():
                    break
                i, audio = item
                if audio is None:
                    # D2: a sentence produced no audio (synthesis failed or returned
                    # empty). Previously this was skipped with no trace. Log it and
                    # remember to notify Paul at the end of the read.
                    skipped += 1
                    logger.warning(
                        "Skipped sentence [%d/%d] (no audio produced): %.80s",
                        i + 1, len(chunks), chunks[i].text,
                    )
                    continue
                logger.info("Playing [%d/%d]: %.60s...", i + 1, len(chunks), chunks[i].text)
                if not play_audio(audio):
                    break
        finally:
            cancel.set()  # the producer stops after its current chunk

        _set_status('Idle')
        if skipped:
            logger.warning(
                "Finished reading — %d of %d sentence(s) skipped", skipped, len(chunks)
            )
            _notify(
                'Natural Voice TTS',
                f'{skipped} sentence(s) could not be spoken and were skipped.',
            )
        else:
            logger.info("Finished reading")


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
    _pipe_stop_event.set()  # Signal pipe listener to stop
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


def _on_menu_help(icon, item):
    show_help()


def _on_menu_about(icon, item):
    show_about()


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

    # Keyboard shortcuts submenu (display-only)
    shortcut_items = [
        pystray.MenuItem('Ctrl+Win+T — Read Selected Text', None, enabled=False),
        pystray.MenuItem('Ctrl+Win+X — Stop', None, enabled=False),
        pystray.MenuItem('Ctrl+Win+Z — Pause / Resume', None, enabled=False),
    ]

    return pystray.Menu(
        pystray.MenuItem('Voice', pystray.Menu(*voice_items)),
        pystray.MenuItem('Speed', pystray.Menu(*speed_items)),
        pystray.MenuItem('Keyboard Shortcuts', pystray.Menu(*shortcut_items)),
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
        pystray.MenuItem('Help', _on_menu_help),
        pystray.MenuItem('About', _on_menu_about),
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
    try:
        register_hotkeys(_on_read, _on_stop, _on_pause)
    except Exception:
        logger.exception("Failed to register hotkeys")

    # Start named pipe listener (allows MCP server to send text)
    _pipe_stop_event.clear()
    pipe_listener.start_pipe_listener(_text_queue, _pipe_stop_event, on_stop=_on_stop)

    logger.info("Ready! Ctrl+Win+T = Read | Ctrl+Win+X = Stop | Ctrl+Win+Z = Pause")
    logger.info("Setup complete, returning to message loop")


def main() -> None:
    """Launch the system tray application."""
    # In frozen mode, also log to a file for debugging
    handlers = [logging.StreamHandler()]
    if getattr(sys, 'frozen', False):
        log_dir = os.path.join(
            os.environ.get('APPDATA', os.path.expanduser('~')),
            'NaturalVoiceTTS',
        )
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, 'app.log')
        handlers.append(logging.FileHandler(log_path, encoding='utf-8'))

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%H:%M:%S',
        handlers=handlers,
    )

    logger.info("=== Natural Voice TTS (Phase 2 — System Tray) ===")

    # Load config
    config.load()

    # Load icon (resolve path for both frozen and source installs)
    if getattr(sys, 'frozen', False):
        # PyInstaller one-folder mode puts datas under _internal/
        base_dir = os.path.join(os.path.dirname(sys.executable), '_internal')
    else:
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    icon_path = os.path.join(base_dir, 'assets', 'icon.ico')
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
    try:
        _icon.run(setup=_on_setup)
    except Exception:
        logger.exception("Icon main loop crashed")

    logger.info("Goodbye!")


def _check_single_instance():
    """Ensure only one instance of the app runs at a time using a named mutex."""
    import ctypes
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "NaturalVoiceTTS_SingleInstance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(mutex)
        return None
    return mutex


if __name__ == '__main__':
    _mutex = _check_single_instance()
    if _mutex is None:
        sys.exit(0)
    main()
