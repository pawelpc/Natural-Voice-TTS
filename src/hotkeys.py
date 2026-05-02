"""Global hotkey listener and clipboard text grabbing.

Uses Win32 RegisterHotKey API with a hidden window message loop.
This works without admin privileges and properly processes WM_HOTKEY
messages in a frozen PyInstaller environment.
"""

import os
import time
import ctypes
import ctypes.wintypes
import threading
import logging
from typing import Callable, Optional

# LRESULT doesn't exist in ctypes.wintypes until Python 3.12
if not hasattr(ctypes.wintypes, 'LRESULT'):
    ctypes.wintypes.LRESULT = ctypes.c_ssize_t

import pyperclip

logger = logging.getLogger(__name__)

# Default hotkey bindings
HOTKEY_READ_LABEL = 'Ctrl+Win+T'
HOTKEY_STOP_LABEL = 'Ctrl+Win+X'
HOTKEY_PAUSE_LABEL = 'Ctrl+Win+Z'

# Debug flag from environment
HOTKEY_DEBUG = os.getenv('HOTKEY_DEBUG', '').lower() in ('1', 'true', 'yes')

# --- Win32 Constants ---

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_C = 0x43

# RegisterHotKey modifier flags
MOD_CONTROL = 0x0002
MOD_WIN = 0x0008
# MOD_NOREPEAT = 0x4000  # REMOVED: Some Windows versions don't handle this reliably

# Virtual key codes for our hotkeys
VK_T = 0x54  # Read (Talk)
VK_X = 0x58  # Stop
VK_Z = 0x5A  # Pause

# Additional virtual key codes for modifier release
VK_LWIN = 0x5B  # Left Windows key

# WM_HOTKEY message ID
WM_HOTKEY = 0x0312

# Hotkey IDs (arbitrary unique integers)
HOTKEY_ID_READ = 1
HOTKEY_ID_STOP = 2
HOTKEY_ID_PAUSE = 3


# --- Win32 SendInput structures (correct for 64-bit Windows) ---

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


# --- Win32 window class structures (WNDCLASSEXW for 64-bit) ---

# Define the proper window procedure callback type
WNDPROCTYPE = ctypes.WINFUNCTYPE(
    ctypes.wintypes.LRESULT,
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM
)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ('cbSize', ctypes.wintypes.UINT),
        ('style', ctypes.wintypes.UINT),
        ('lpfnWndProc', WNDPROCTYPE),
        ('cbClsExtra', ctypes.c_int),
        ('cbWndExtra', ctypes.c_int),
        ('hInstance', ctypes.wintypes.HANDLE),
        ('hIcon', ctypes.wintypes.HANDLE),
        ('hCursor', ctypes.wintypes.HANDLE),
        ('hbrBackground', ctypes.wintypes.HANDLE),
        ('lpszMenuName', ctypes.wintypes.LPCWSTR),
        ('lpszClassName', ctypes.wintypes.LPCWSTR),
        ('hIconSm', ctypes.wintypes.HANDLE),
    ]


# --- Module state ---
_hotkey_thread: Optional[threading.Thread] = None
_hotkey_stop_event = threading.Event()
_hotkey_hwnd: Optional[int] = None  # Handle to the hidden window (used for stopping)
_using_win32_hotkeys = False

# Store wndproc callback at module level to prevent garbage collection
_wndproc_ptr: Optional[WNDPROCTYPE] = None


def _check_admin_privileges() -> bool:
    """Check if running with admin privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _release_held_modifiers() -> None:
    """Release held Ctrl and Win modifier keys via synthetic key-up events.

    When the user presses a hotkey like Ctrl+Win+T, these modifier keys are still
    physically held down when the hotkey callback executes. If we then send Ctrl+C
    via SendInput, Windows sees Ctrl+Win+C instead of just Ctrl+C, which doesn't
    trigger a copy operation. This function injects key-up events for both the Win
    and Ctrl keys to release them synthetically, allowing subsequent Ctrl+C to work.
    """
    inputs = (INPUT * 2)()

    for i, vk in enumerate([VK_LWIN, VK_CONTROL]):
        inputs[i].type = INPUT_KEYBOARD
        inputs[i].union.ki.wVk = vk
        inputs[i].union.ki.dwFlags = KEYEVENTF_KEYUP

    sent = ctypes.windll.user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    logger.debug("SendInput released %d of 2 modifier key-ups", sent)


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
        # CRITICAL FIX: Release held modifier keys (Ctrl+Win) BEFORE sending Ctrl+C.
        # When the user presses Ctrl+Win+T hotkey, these keys are still physically held
        # when grab_selected_text() is called. If we send Ctrl+C immediately, Windows
        # sees Ctrl+Win+C instead of just Ctrl+C, which fails to copy. We must inject
        # key-up events for both modifiers to release them synthetically.
        _release_held_modifiers()
        time.sleep(0.05)

        # Clear clipboard to detect new content
        pyperclip.copy('')

        # Simulate Ctrl+C via Win32 SendInput (works from any thread)
        _send_ctrl_c()
        time.sleep(0.30)  # Wait for clipboard to update (300ms for slower apps)

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


# --- Win32 RegisterHotKey approach with hidden window (works without admin) ---

def _win32_hotkey_listener(
    on_read: Callable[[], None],
    on_stop: Callable[[], None],
    on_pause: Callable[[], None],
) -> None:
    """Background thread that creates a hidden window and registers Win32 hotkeys.

    Creates a hidden window on THIS thread to anchor the hotkey registrations
    and run a proper GetMessageW message loop. This ensures WM_HOTKEY messages
    are received correctly, even in a frozen PyInstaller environment.

    Uses RegisterHotKey — the standard Windows API for global hotkeys.
    Works WITHOUT admin privileges.
    """
    global _hotkey_hwnd, _wndproc_ptr

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Set proper return types AND argument types for Win32 functions
        # Without argtypes, ctypes defaults to c_int which truncates 64-bit handles
        user32.RegisterClassExW.restype = ctypes.wintypes.ATOM
        user32.RegisterClassExW.argtypes = [ctypes.c_void_p]

        user32.CreateWindowExW.restype = ctypes.wintypes.HWND
        user32.CreateWindowExW.argtypes = [
            ctypes.wintypes.DWORD,   # dwExStyle
            ctypes.wintypes.LPCWSTR, # lpClassName
            ctypes.wintypes.LPCWSTR, # lpWindowName
            ctypes.wintypes.DWORD,   # dwStyle
            ctypes.c_int,            # x
            ctypes.c_int,            # y
            ctypes.c_int,            # nWidth
            ctypes.c_int,            # nHeight
            ctypes.wintypes.HWND,    # hWndParent
            ctypes.wintypes.HMENU,   # hMenu
            ctypes.wintypes.HINSTANCE,  # hInstance
            ctypes.wintypes.LPARAM,  # lpParam
        ]

        user32.RegisterHotKey.restype = ctypes.wintypes.BOOL
        user32.RegisterHotKey.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.wintypes.UINT, ctypes.wintypes.UINT]

        user32.GetMessageW.restype = ctypes.wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.c_void_p, ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.UINT]

        user32.DefWindowProcW.restype = ctypes.wintypes.LRESULT
        user32.DefWindowProcW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]

        kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]

        # Simple window procedure that does nothing but dispatch GetMessage loop
        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_HOTKEY:
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        # Create and store the window procedure callback at module level to prevent GC
        _wndproc_ptr = WNDPROCTYPE(wndproc)

        # Create window class (WNDCLASSEXW for 64-bit)
        wnd_class = WNDCLASSEXW()
        wnd_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wnd_class.lpfnWndProc = _wndproc_ptr
        wnd_class.lpszClassName = "NaturalVoiceTTSHotkeyWindow"
        wnd_class.hInstance = kernel32.GetModuleHandleW(None)

        if not user32.RegisterClassExW(ctypes.byref(wnd_class)):
            logger.error("Failed to register window class (error %d)", ctypes.GetLastError())
            return

        if HOTKEY_DEBUG:
            logger.debug("Window class registered")

        # Create hidden message-only window (HWND_MESSAGE = -3)
        # Message-only windows are specifically designed for receiving messages
        # without being displayed, and are more reliable for hotkey registration
        HWND_MESSAGE = -3
        hwnd = user32.CreateWindowExW(
            0,                                    # dwExStyle
            "NaturalVoiceTTSHotkeyWindow",        # lpClassName
            "NaturalVoiceTTS Hotkey Window",       # lpWindowName
            0,                                    # dwStyle
            0, 0, 0, 0,                           # x, y, w, h
            ctypes.wintypes.HWND(HWND_MESSAGE),   # hWndParent (HWND_MESSAGE = -3)
            ctypes.wintypes.HMENU(0),             # hMenu (NULL)
            wnd_class.hInstance,                   # hInstance
            0,                                    # lpParam (NULL)
        )

        if not hwnd:
            logger.error("Failed to create hidden window (error %d)", ctypes.GetLastError())
            return

        if HOTKEY_DEBUG:
            logger.debug("Hidden window created: %s", hwnd)

        # Store hwnd globally so unregister_hotkeys() can post WM_QUIT
        _hotkey_hwnd = hwnd

        modifiers = MOD_CONTROL | MOD_WIN

        # Register all three hotkeys: Ctrl+Win+T/X/Z
        reg_read = user32.RegisterHotKey(hwnd, HOTKEY_ID_READ, modifiers, VK_T)
        reg_stop = user32.RegisterHotKey(hwnd, HOTKEY_ID_STOP, modifiers, VK_X)
        reg_pause = user32.RegisterHotKey(hwnd, HOTKEY_ID_PAUSE, modifiers, VK_Z)

        for name, label, ok in [
            ("Read", HOTKEY_READ_LABEL, reg_read),
            ("Stop", HOTKEY_STOP_LABEL, reg_stop),
            ("Pause", HOTKEY_PAUSE_LABEL, reg_pause),
        ]:
            if ok:
                logger.info("Win32 hotkey registered: %s (%s)", label, name)
            else:
                logger.error("Failed to register %s: %s (error %d)", name, label, ctypes.GetLastError())

        registered_count = sum([bool(reg_read), bool(reg_stop), bool(reg_pause)])
        logger.info("Win32 RegisterHotKey: %d of 3 hotkeys registered", registered_count)

        callbacks = {
            HOTKEY_ID_READ: on_read,
            HOTKEY_ID_STOP: on_stop,
            HOTKEY_ID_PAUSE: on_pause,
        }

        # Proper message loop using GetMessageW (blocking call)
        # This is the standard Windows message pump and properly processes WM_HOTKEY
        msg = ctypes.wintypes.MSG()
        loop_iteration = 0
        while True:
            # GetMessageW blocks until a message is available
            # Pass explicit HWND(0) (NULL) instead of None to ensure proper message filtering
            result = user32.GetMessageW(ctypes.byref(msg), ctypes.wintypes.HWND(0), 0, 0)
            loop_iteration += 1

            # Log heartbeat every 100 iterations to confirm loop is alive
            if loop_iteration % 100 == 0:
                logger.info("GetMessageW loop alive (iteration %d)", loop_iteration)

            if result <= 0:
                # GetMessageW returns 0 on WM_QUIT, -1 on error
                break

            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                # ALWAYS log WM_HOTKEY reception at INFO level (critical for debugging)
                logger.info("Win32 WM_HOTKEY received: id=%d", hotkey_id)
                cb = callbacks.get(hotkey_id)
                if cb:
                    # Run callback on a new thread to avoid blocking the message loop
                    threading.Thread(target=cb, daemon=True).start()
                else:
                    logger.warning("Received WM_HOTKEY with unknown id=%d", hotkey_id)

        # Unregister hotkeys
        if reg_read:
            user32.UnregisterHotKey(hwnd, HOTKEY_ID_READ)
        if reg_stop:
            user32.UnregisterHotKey(hwnd, HOTKEY_ID_STOP)
        if reg_pause:
            user32.UnregisterHotKey(hwnd, HOTKEY_ID_PAUSE)

        # Destroy window
        user32.DestroyWindow(hwnd)
        user32.UnregisterClassW("NaturalVoiceTTSHotkeyWindow", wnd_class.hInstance)

        _hotkey_hwnd = None
        logger.info("Win32 hotkeys unregistered")

    except Exception as e:
        logger.exception("Win32 hotkey listener thread crashed: %s", e)
        _hotkey_hwnd = None


# --- keyboard library fallback ---

def _register_keyboard_hotkeys(
    on_read: Callable[[], None],
    on_stop: Callable[[], None],
    on_pause: Callable[[], None],
) -> bool:
    """Fallback: register hotkeys using the `keyboard` library (needs admin)."""
    try:
        import keyboard as kb

        def _run_off_hook(fn):
            def wrapper():
                threading.Thread(target=fn, daemon=True).start()
            return wrapper

        kb.add_hotkey('ctrl+windows+t', _run_off_hook(on_read), suppress=False)
        kb.add_hotkey('ctrl+windows+x', _run_off_hook(on_stop), suppress=False)
        kb.add_hotkey('ctrl+windows+z', _run_off_hook(on_pause), suppress=False)

        logger.info("Fallback: keyboard library hotkeys registered (requires admin)")
        return True
    except Exception as e:
        logger.error("Fallback keyboard registration failed: %s", e)
        return False


# --- Public API ---

def register_hotkeys(
    on_read: Callable[[], None],
    on_stop: Callable[[], None],
    on_pause: Callable[[], None],
) -> None:
    """Register global hotkeys with the given callbacks.

    Primary method: Win32 RegisterHotKey API (works without admin).
    Fallback: `keyboard` library low-level hooks (needs admin).
    """
    global _hotkey_thread, _using_win32_hotkeys

    is_admin = _check_admin_privileges()
    logger.info("Admin privileges: %s", "Yes" if is_admin else "No")

    if HOTKEY_DEBUG:
        logger.info("HOTKEY_DEBUG enabled — verbose logging active")

    # Primary: Win32 RegisterHotKey (works without admin)
    logger.info("Attempting Win32 RegisterHotKey method (no admin required)...")
    _hotkey_stop_event.clear()
    _hotkey_thread = threading.Thread(
        target=_win32_hotkey_listener,
        args=(on_read, on_stop, on_pause),
        daemon=True,
        name='win32-hotkey-listener',
    )
    _hotkey_thread.start()
    _using_win32_hotkeys = True

    # Give it a moment to register
    time.sleep(0.2)

    # Check if the thread is still alive; if not, it crashed
    if not _hotkey_thread.is_alive():
        logger.error("Win32 hotkey listener thread died; attempting fallback...")
        _using_win32_hotkeys = False
        if not _register_keyboard_hotkeys(on_read, on_stop, on_pause):
            logger.error("Both Win32 and keyboard library hotkey registration failed")
            return

    logger.info("Hotkeys ready:")
    logger.info("  %s — Read selected text", HOTKEY_READ_LABEL)
    logger.info("  %s — Stop reading", HOTKEY_STOP_LABEL)
    logger.info("  %s — Pause / Resume", HOTKEY_PAUSE_LABEL)


def unregister_hotkeys() -> None:
    """Remove all registered hotkeys."""
    global _using_win32_hotkeys, _hotkey_hwnd

    if _using_win32_hotkeys:
        # Post WM_QUIT to the hotkey window to break out of GetMessageW loop
        if _hotkey_hwnd:
            try:
                ctypes.windll.user32.PostMessageW(_hotkey_hwnd, 0x0012, 0, 0)  # WM_QUIT = 0x0012
            except Exception as e:
                logger.debug("PostMessageW failed: %s", e)

        _hotkey_stop_event.set()
        if _hotkey_thread and _hotkey_thread.is_alive():
            _hotkey_thread.join(timeout=2.0)
        _using_win32_hotkeys = False
        _hotkey_hwnd = None
        logger.info("Win32 hotkeys unregistered")
    else:
        try:
            import keyboard as kb
            kb.unhook_all_hotkeys()
        except (AttributeError, Exception) as e:
            logger.debug("unhook_all_hotkeys failed (%s), trying unhook_all", e)
            try:
                import keyboard as kb
                kb.unhook_all()
            except Exception:
                pass
        logger.info("Keyboard library hotkeys unregistered")


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
    logger.info("Listening for hotkeys... Press Ctrl+C in this console to exit.")
    logger.info("INPUT struct size: %d bytes", ctypes.sizeof(INPUT))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        unregister_hotkeys()
        logger.info("Exited")
