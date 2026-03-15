"""Global hotkey listener and clipboard text grabbing."""

import time
import ctypes
import ctypes.wintypes
import threading
import logging
from typing import Callable

import keyboard
import pyperclip

logger = logging.getLogger(__name__)

# Default hotkey bindings
# Uses Ctrl+Win (without Shift) to avoid browser conflicts:
#   Ctrl+Shift+R = hard refresh in Chrome/Edge/Firefox
#   Ctrl+Shift+S = save-as in some browsers
#   Ctrl+Shift+P = private/incognito or command palette
HOTKEY_READ = 'ctrl+windows+r'
HOTKEY_STOP = 'ctrl+windows+s'
HOTKEY_PAUSE = 'ctrl+windows+p'

# --- Win32 SendInput structures (correct for 64-bit Windows) ---

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_C = 0x43


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', ctypes.wintypes.WORD),
        ('wScan', ctypes.wintypes.WORD),
        ('dwFlags', ctypes.wintypes.DWORD),
        ('time', ctypes.wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ('dx', ctypes.c_long),
        ('dy', ctypes.c_long),
        ('mouseData', ctypes.wintypes.DWORD),
        ('dwFlags', ctypes.wintypes.DWORD),
        ('time', ctypes.wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ('uMsg', ctypes.wintypes.DWORD),
        ('wParamL', ctypes.wintypes.WORD),
        ('wParamH', ctypes.wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ('mi', MOUSEINPUT),
        ('ki', KEYBDINPUT),
        ('hi', HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ('type', ctypes.wintypes.DWORD),
        ('union', INPUT_UNION),
    ]


def _send_ctrl_c() -> None:
    """Send Ctrl+C using Win32 SendInput API (thread-safe, works from any thread)."""
    inputs = (INPUT * 4)()

    for i, (vk, flags) in enumerate([
        (VK_CONTROL, 0),
        (VK_C, 0),
        (VK_C, KEYEVENTF_KEYUP),
        (VK_CONTROL, KEYEVENTF_KEYUP),
    ]):
        inputs[i].type = INPUT_KEYBOARD
        inputs[i].union.ki.wVk = vk
        inputs[i].union.ki.dwFlags = flags

    sent = ctypes.windll.user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    logger.debug("SendInput sent %d of 4 events", sent)


def grab_selected_text() -> str:
    """Grab currently selected text by simulating Ctrl+C and reading clipboard.

    Uses Win32 SendInput for reliable Ctrl+C from any thread context.
    Saves and restores the previous clipboard content.
    Returns the selected text, or empty string if nothing was captured.
    """
    # Save current clipboard
    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        old_clipboard = ''

    text = ''
    try:
        # Brief pause to let modifier keys settle after hotkey release
        time.sleep(0.05)

        # Clear clipboard to detect new content
        pyperclip.copy('')

        # Simulate Ctrl+C via Win32 SendInput (works from any thread)
        _send_ctrl_c()
        time.sleep(0.25)  # Wait for clipboard to update

        # Read new clipboard content
        text = pyperclip.paste()

        if text:
            logger.info("Grabbed %d characters from clipboard", len(text))
            return text
        else:
            logger.info("No text selected or clipboard empty")
            return ''
    finally:
        # Restore old clipboard if we didn't get new text
        if not text:
            try:
                pyperclip.copy(old_clipboard)
            except Exception:
                pass


def _run_off_hook(fn: Callable[[], None]) -> Callable[[], None]:
    """Wrap a callback so it runs on a new thread instead of the keyboard hook thread.

    This is critical because the keyboard hook thread blocks Windows message
    processing. If we call SendInput (for Ctrl+C) from the hook thread,
    the injected keystrokes can't be delivered until the hook returns — deadlock.
    Running on a separate thread lets the hook return immediately.
    """
    def wrapper():
        threading.Thread(target=fn, daemon=True).start()
    return wrapper


def register_hotkeys(
    on_read: Callable[[], None],
    on_stop: Callable[[], None],
    on_pause: Callable[[], None],
) -> None:
    """Register global hotkeys with the given callbacks.

    Callbacks are dispatched to separate threads to avoid blocking the
    keyboard hook, which would prevent SendInput from working.
    """
    keyboard.add_hotkey(HOTKEY_READ, _run_off_hook(on_read), suppress=True, trigger_on_release=True)
    keyboard.add_hotkey(HOTKEY_STOP, _run_off_hook(on_stop), suppress=True, trigger_on_release=True)
    keyboard.add_hotkey(HOTKEY_PAUSE, _run_off_hook(on_pause), suppress=True, trigger_on_release=True)

    logger.info("Hotkeys registered:")
    logger.info("  %s — Read selected text", HOTKEY_READ)
    logger.info("  %s — Stop reading", HOTKEY_STOP)
    logger.info("  %s — Pause / Resume", HOTKEY_PAUSE)


def unregister_hotkeys() -> None:
    """Remove all registered hotkeys."""
    try:
        keyboard.unhook_all_hotkeys()
    except (AttributeError, Exception) as e:
        logger.debug("unhook_all_hotkeys failed (%s), trying unhook_all", e)
        try:
            keyboard.unhook_all()
        except Exception:
            pass
    logger.info("Hotkeys unregistered")


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

    def test_read():
        text = grab_selected_text()
        if text:
            logger.info("Selected text: %s", text[:200])
        else:
            logger.info("No text selected")

    def test_stop():
        logger.info("Stop pressed")

    def test_pause():
        logger.info("Pause/Resume pressed")

    register_hotkeys(test_read, test_stop, test_pause)
    logger.info("Listening for hotkeys... Press Ctrl+C to exit.")
    logger.info("INPUT struct size: %d bytes", ctypes.sizeof(INPUT))

    try:
        keyboard.wait()
    except KeyboardInterrupt:
        unregister_hotkeys()
        logger.info("Exited")
