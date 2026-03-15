"""PyInstaller runtime hook for frozen mode compatibility.

Fixes:
1. torch DLL search paths (c10.dll and dependencies)
2. sys.stderr/stdout being None in windowed mode (breaks loguru)
"""
import os
import sys

# In windowed PyInstaller mode (console=False), sys.stderr and sys.stdout
# are None. loguru crashes when it tries to add None as a logging sink.
# Redirect to devnull so loguru (used by kokoro) can initialize.
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')

if sys.platform == 'win32':
    # In PyInstaller one-folder mode, _MEIPASS points to _internal/
    base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))

    # Add torch/lib to DLL search path (where c10.dll, torch_cpu.dll, etc. live)
    torch_lib = os.path.join(base, 'torch', 'lib')
    if os.path.isdir(torch_lib):
        os.add_dll_directory(torch_lib)
        os.environ['PATH'] = torch_lib + os.pathsep + os.environ.get('PATH', '')

    # Also add the base _internal directory itself
    if os.path.isdir(base):
        os.add_dll_directory(base)
        os.environ['PATH'] = base + os.pathsep + os.environ.get('PATH', '')
