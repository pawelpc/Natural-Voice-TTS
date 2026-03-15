"""Help and About dialogs for Natural Voice TTS (tkinter)."""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

APP_VERSION = '1.0.0'
APP_NAME = 'Natural Voice TTS'

HELP_TEXT = """\
USAGE
=====

Hotkeys
-------
  Ctrl+Win+R   Read selected text aloud
  Ctrl+Win+S   Stop reading
  Ctrl+Win+P   Pause / Resume

How to Use
----------
1. Select text in any application (browser, editor, PDF viewer, etc.)
2. Press Ctrl+Win+R to read it aloud
3. Press Ctrl+Win+S to stop, or Ctrl+Win+P to pause/resume

You can also right-click the tray icon and choose "Read Clipboard" to \
read whatever is currently on your clipboard.

Tray Menu
---------
Right-click the system tray icon to access:
  - Voice: Choose from 30+ natural voices (American/British, male/female)
  - Speed: Set playback speed (0.75x to 2.0x)
  - Keyboard Shortcuts: View hotkey bindings
  - Read Clipboard / Stop / Pause-Resume: Playback controls
  - Start with Windows: Auto-launch on login
  - Help / About: This dialog and app info
  - Quit: Exit the application

Voice & Speed
-------------
Voice and speed changes take effect on the next read. Settings are saved \
automatically to %APPDATA%\\NaturalVoiceTTS\\config.json.


TROUBLESHOOTING
===============

GPU / CUDA Not Available
------------------------
If the app falls back to CPU, synthesis will be slower but still works. \
To enable GPU acceleration:
  - Ensure NVIDIA drivers are up to date
  - Reinstall PyTorch with CUDA support:
    pip install torch --index-url https://download.pytorch.org/whl/cu121

espeak-ng Not Found
-------------------
Kokoro TTS requires espeak-ng for phoneme generation. Install it from:
  https://github.com/espeak-ng/espeak-ng/releases
Install to the default location (C:\\Program Files\\eSpeak NG).

No Audio Output
---------------
  - Check that your default audio output device is working
  - Try playing audio in another application to verify
  - Restart the app after connecting/changing audio devices

Hotkeys Not Working
-------------------
  - The 'keyboard' library may require Administrator privileges
  - Try running the app as Administrator
  - Check that no other app is using the same hotkey combination


SYSTEM REQUIREMENTS
===================

  - Windows 10 or later
  - Python 3.11+ (for source installs)
  - NVIDIA GPU with 4+ GB VRAM recommended (CPU fallback available)
  - espeak-ng installed
  - ~500 MB disk space (plus ~2 GB for PyTorch with CUDA)
"""


def _run_in_tk_thread(func):
    """Run a dialog function in a dedicated thread with its own Tk mainloop."""
    def wrapper():
        thread = threading.Thread(target=func, daemon=True)
        thread.start()
    return wrapper


@_run_in_tk_thread
def show_help():
    """Show the Help dialog with usage instructions and troubleshooting."""
    root = tk.Tk()
    root.title(f'{APP_NAME} — Help')
    root.geometry('540x420')
    root.resizable(True, True)

    # Set icon if available
    _set_icon(root)

    text = scrolledtext.ScrolledText(
        root, wrap=tk.WORD, font=('Consolas', 10), padx=10, pady=10,
    )
    text.insert(tk.END, HELP_TEXT)
    text.configure(state=tk.DISABLED)
    text.pack(fill=tk.BOTH, expand=True)

    close_btn = ttk.Button(root, text='Close', command=root.destroy)
    close_btn.pack(pady=(5, 10))

    root.mainloop()


@_run_in_tk_thread
def show_about():
    """Show the About dialog with version, attribution, and license info."""
    root = tk.Tk()
    root.title(f'About {APP_NAME}')
    root.geometry('400x320')
    root.resizable(False, False)

    _set_icon(root)

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill=tk.BOTH, expand=True)

    # App name and version
    ttk.Label(
        frame, text=APP_NAME, font=('Segoe UI', 16, 'bold'),
    ).pack(pady=(0, 2))

    ttk.Label(
        frame, text=f'Version {APP_VERSION}', font=('Segoe UI', 10),
    ).pack(pady=(0, 12))

    # Description
    ttk.Label(
        frame,
        text='System-wide text-to-speech for Windows\nusing neural voice synthesis.',
        font=('Segoe UI', 10),
        justify=tk.CENTER,
    ).pack(pady=(0, 16))

    # Separator
    ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 12))

    # Kokoro attribution
    ttk.Label(
        frame,
        text='This software includes Kokoro TTS,\nlicensed under the Apache License 2.0.',
        font=('Segoe UI', 9),
        justify=tk.CENTER,
    ).pack(pady=(0, 4))

    ttk.Label(
        frame,
        text='https://github.com/hexgrad/kokoro',
        font=('Segoe UI', 9),
        foreground='#0066CC',
        cursor='hand2',
    ).pack(pady=(0, 12))

    # License reference
    ttk.Label(
        frame,
        text='See LICENSE and THIRD_PARTY_NOTICES.md\nfor full license information.',
        font=('Segoe UI', 9),
        justify=tk.CENTER,
    ).pack(pady=(0, 12))

    # Copyright
    ttk.Label(
        frame,
        text='Copyright 2025 Paul Pawelski',
        font=('Segoe UI', 9),
        foreground='#666666',
    ).pack(pady=(0, 8))

    close_btn = ttk.Button(frame, text='Close', command=root.destroy)
    close_btn.pack()

    root.mainloop()


def _set_icon(root: tk.Tk) -> None:
    """Set the window icon from the assets directory."""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    icon_path = os.path.join(base_dir, 'assets', 'icon.ico')
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(icon_path)
        except tk.TclError:
            pass
