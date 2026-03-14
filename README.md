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
| `Ctrl+Shift+Win+R` | Read selected text |
| `Ctrl+Shift+Win+S` | Stop reading |
| `Ctrl+Shift+Win+P` | Pause / Resume |

1. Select text in any application (browser, editor, PDF viewer, etc.)
2. Press `Ctrl+Shift+Win+R` — the text is copied and read aloud
3. Press `Ctrl+Shift+Win+S` to stop or `Ctrl+Shift+Win+P` to pause/resume

## Troubleshooting

**"espeak-ng not found"** — Install espeak-ng from the link above, or set environment variables manually:
```
set PHONEMIZER_ESPEAK_LIBRARY=C:\Program Files\eSpeak NG\libespeak-ng.dll
set PHONEMIZER_ESPEAK_PATH=C:\Program Files\eSpeak NG\espeak-ng.exe
```

**"CUDA not available"** — Ensure NVIDIA drivers are up to date and PyTorch was installed with the CUDA index URL shown above. The app will fall back to CPU with a warning.

**"keyboard" requires admin** — If global hotkeys don't work, try running the terminal as Administrator.

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
assets/
  icon.ico          — System tray icon
```
