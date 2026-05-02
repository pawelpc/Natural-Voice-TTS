"""PyInstaller runtime hook for frozen mode compatibility.

Fixes:
1. torch DLL search paths (c10.dll and CUDA dependencies)
2. CUDA library paths (cublas, cudnn, cufft, cusparse, nccl, nvrtc, etc.)
3. sys.stderr/stdout being None in windowed mode (breaks loguru)
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
    # Determine base directory
    # In PyInstaller one-folder mode, _MEIPASS points to _internal/
    base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))

    # List of directories to add to DLL search path
    dll_dirs = []

    # 1. Torch library directory (torch_cpu.dll, c10.dll, etc.)
    torch_lib = os.path.join(base, 'torch', 'lib')
    if os.path.isdir(torch_lib):
        dll_dirs.append(torch_lib)

    # 2. CUDA library directories (bundled by PyInstaller collect_all)
    cuda_lib_candidates = [
        os.path.join(base, 'torch', 'lib'),  # torch bundles some CUDA libs here
        os.path.join(base, '_internal', 'torch', 'lib'),
        os.path.join(base, 'nvidia'),  # NVIDIA package structure
        os.path.join(base, 'nvidia', 'cuda_runtime'),
        os.path.join(base, 'nvidia', 'cuda_runtime', 'bin'),
        os.path.join(base, 'nvidia', 'cublas'),
        os.path.join(base, 'nvidia', 'cublas', 'bin'),
        os.path.join(base, 'nvidia', 'cudnn'),
        os.path.join(base, 'nvidia', 'cudnn', 'bin'),
        os.path.join(base, 'nvidia', 'cufft'),
        os.path.join(base, 'nvidia', 'cufft', 'bin'),
        os.path.join(base, 'nvidia', 'cusparse'),
        os.path.join(base, 'nvidia', 'cusparse', 'bin'),
        os.path.join(base, 'nvidia', 'nccl'),
        os.path.join(base, 'nvidia', 'nccl', 'bin'),
        os.path.join(base, 'nvidia', 'nvrtc'),
        os.path.join(base, 'nvidia', 'nvrtc', 'bin'),
    ]

    for cuda_lib in cuda_lib_candidates:
        if os.path.isdir(cuda_lib):
            dll_dirs.append(cuda_lib)

    # 3. Base _internal directory (fallback for any other DLLs)
    if os.path.isdir(base):
        dll_dirs.append(base)

    # Register DLL directories and update PATH
    added_paths = []
    for dll_dir in dll_dirs:
        if dll_dir and os.path.isdir(dll_dir) and dll_dir not in added_paths:
            try:
                os.add_dll_directory(dll_dir)
                added_paths.append(dll_dir)
            except OSError as e:
                # Already added or invalid, continue
                pass

    # Update environment PATH for additional visibility
    if added_paths:
        current_path = os.environ.get('PATH', '')
        new_path = os.pathsep.join(added_paths) + os.pathsep + current_path
        os.environ['PATH'] = new_path

    # Log what was added (write to a file since stdout/stderr might be redirected)
    try:
        log_file = os.path.join(os.path.dirname(sys.executable), 'rthook_torch.log')
        with open(log_file, 'w') as f:
            f.write("PyInstaller torch runtime hook initialized\n")
            f.write(f"Base directory: {base}\n")
            f.write(f"DLL directories added ({len(added_paths)}):\n")
            for path in added_paths:
                f.write(f"  - {path}\n")
    except Exception:
        # Silently fail if logging doesn't work (sys.stdout is None)
        pass
