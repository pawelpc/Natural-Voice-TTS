# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Natural Voice TTS.

One-folder mode: produces dist/NaturalVoiceTTS/ with NaturalVoiceTTS.exe
plus all bundled dependencies, models, and espeak-ng.

Run with:  pyinstaller naturalvoicetts.spec
"""

import os
import sys
import site
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# --- Collect packages that need special handling ---
# collect_all properly bundles modules + data + binaries together

# spacy en_core_web_sm: must be importable AND have data files
_sm_datas, _sm_binaries, _sm_hiddenimports = collect_all('en_core_web_sm')

# language_tags: needs its JSON data directory
_lt_datas = collect_data_files('language_tags')

# espeakng_loader: needs espeak-ng-data directory
_el_datas, _el_binaries, _el_hiddenimports = collect_all('espeakng_loader')

# kokoro: transformers reads .py source at runtime
_ko_datas, _ko_binaries, _ko_hiddenimports = collect_all('kokoro')

# misaki: G2P module used by kokoro, needs data/*.json files
_mi_datas, _mi_binaries, _mi_hiddenimports = collect_all('misaki')

datas = [
    # Application assets
    ('assets/icon.ico', 'assets'),
    # License files
    ('LICENSE', '.'),
    ('NOTICE', '.'),
    ('THIRD_PARTY_NOTICES.md', '.'),
] + _sm_datas + _lt_datas + _el_datas + _ko_datas + _mi_datas

extra_binaries = _sm_binaries + _el_binaries + _ko_binaries + _mi_binaries
extra_hiddenimports = _sm_hiddenimports + _el_hiddenimports + _ko_hiddenimports + _mi_hiddenimports

a = Analysis(
    ['src/app.py'],
    pathex=['src'],
    binaries=extra_binaries,
    datas=datas,
    hiddenimports=[
        # PyTorch and CUDA
        'torch',
        'torch.utils',
        'torch.nn',
        'torch.nn.functional',
        # Kokoro TTS
        'kokoro',
        # Transformers (used by kokoro internally)
        'transformers',
        'transformers.models',
        # spaCy
        'spacy',
        'en_core_web_sm',
        # Audio
        'sounddevice',
        'soundfile',
        'scipy',
        'scipy.signal',
        # Other deps
        'munch',
        'numpy',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'keyboard',
        'pyperclip',
        # Our source modules
        'tts_engine',
        'audio_player',
        'text_processor',
        'hotkeys',
        'config',
        'dialogs',
    ] + extra_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_torch.py'],
    excludes=[
        # Reduce bundle size: exclude unused modules
        'matplotlib',
        'tkinter.test',
        # NOTE: do NOT exclude 'unittest', 'pydoc', or 'xmlrpc'
        # — torch and scipy require them at runtime
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NaturalVoiceTTS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX can cause issues with torch DLLs
    console=False,  # Windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='NaturalVoiceTTS',
)
