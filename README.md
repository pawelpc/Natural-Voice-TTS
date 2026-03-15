# Natural Voice TTS

System-wide text-to-speech for Windows using [Kokoro TTS](https://github.com/hexgrad/kokoro) (82M parameter neural engine). Select text in any application, press a hotkey, and hear it read aloud in a natural voice.

## Prerequisites

- **Python 3.11+**
- **NVIDIA GPU** with CUDA drivers (GTX 1650 or better; CPU fallback available)
- **espeak-ng** — download the Windows MSI from [espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases) and install to the default location (`C:\Program Files\eSpeak NG`)

## Setup

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install project dependencies
pip install -r requirements.txt
```

**Note:** The first run downloads the Kokoro model (~350 MB). This is cached automatically for future runs.

## Usage

### System Tray Mode (recommended)

```bash
python src/app.py
```

The app starts in the system tray. Right-click the tray icon to:
- **Voice** — choose from 30+ natural voices (American/British, male/female)
- **Speed** — set playback speed (0.75x to 2.0x)
- **Start Reading / Stop / Pause-Resume** — control playback
- **Quit** — exit the app

Settings are saved to `%APPDATA%\NaturalVoiceTTS\config.json` and persist between sessions.

### Terminal Mode (fallback)

```bash
python src/main.py
```

### Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Win+R` | Read selected text |
| `Ctrl+Win+S` | Stop reading |
| `Ctrl+Win+P` | Pause / Resume |

1. Select text in any application (browser, editor, PDF viewer, etc.)
2. Press `Ctrl+Win+R` — the text is copied and read aloud
3. Press `Ctrl+Win+S` to stop or `Ctrl+Win+P` to pause/resume

## Troubleshooting

**"espeak-ng not found"** — Install espeak-ng from the link above, or set environment variables manually:
```
set PHONEMIZER_ESPEAK_LIBRARY=C:\Program Files\eSpeak NG\libespeak-ng.dll
set PHONEMIZER_ESPEAK_PATH=C:\Program Files\eSpeak NG\espeak-ng.exe
```

**"CUDA not available"** — Ensure NVIDIA drivers are up to date and PyTorch was installed with the CUDA index URL shown above. The app will fall back to CPU with a warning.

**"keyboard" requires admin** — If global hotkeys don't work, try running the terminal as Administrator.

## Building the Installer

To package Natural Voice TTS as a standalone Windows installer:

### Prerequisites

1. All source prerequisites above (Python, CUDA, espeak-ng)
2. **PyInstaller**: `pip install pyinstaller`
3. **Inno Setup 6** (optional, for creating the installer .exe): [download](https://jrsoftware.org/isdl.php)
4. Run the app at least once from source so the Kokoro model is cached

### Build

```bash
build.bat
```

This will:
1. Run PyInstaller to create `dist\NaturalVoiceTTS\` with the bundled app
2. Copy espeak-ng binaries into the dist folder
3. Copy Kokoro model files from the HuggingFace cache
4. Run Inno Setup to produce `dist\NaturalVoiceTTS_Setup_1.0.0.exe` (if Inno Setup is installed)

The installer installs to `C:\Program Files\NaturalVoiceTTS\` with Start Menu and optional desktop shortcuts. The uninstaller appears in "Add or Remove Programs".

**Expected size**: ~2-3 GB (PyTorch with CUDA is the largest component).

## Project Structure

```
src/
  app.py            — System tray application (primary entry point)
  main.py           — Terminal-mode entry point (fallback)
  tts_engine.py     — Kokoro TTS wrapper (model loading, synthesis)
  text_processor.py — Sentence splitting and text cleanup
  audio_player.py   — Audio playback with stop/pause/resume
  hotkeys.py        — Global hotkey listener and clipboard grab
  config.py         — Persistent JSON settings
  dialogs.py        — Help and About tkinter dialogs
assets/
  icon.ico          — System tray icon
installer/
  setup.iss         — Inno Setup installer script
```

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

This software includes [Kokoro TTS](https://github.com/hexgrad/kokoro) by Hexgrad, licensed under the Apache License 2.0. See [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for full attribution.
