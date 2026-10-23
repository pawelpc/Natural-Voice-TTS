# Natural Voice TTS

System-wide text-to-speech for Windows using [Kokoro TTS](https://github.com/hexgrad/kokoro) (82M parameter neural engine). Select text in any application, press a hotkey, and hear it read aloud in a natural voice.

## Download & Install

**No programming required.** Just download and run the installer:

**[Download Natural Voice TTS v1.3.0](https://github.com/pawelpc/Natural-Voice-TTS/releases/latest/download/NaturalVoiceTTS_Setup_1.3.0.exe)** (~1.8 GB)

1. Click the link above to download the installer
2. Run `NaturalVoiceTTS_Setup_1.3.0.exe` — if Windows SmartScreen appears, click **More info** → **Run anyway** (the app is unsigned open-source software)
3. Follow the installer prompts (defaults are fine)
4. Launch **Natural Voice TTS** from the Start Menu

The app runs in your system tray (bottom-right of the taskbar). To use it: select any text, press **Ctrl+Win+T**, and listen.

| Hotkey | Action |
|--------|--------|
| `Ctrl+Win+T` | Read selected text |
| `Ctrl+Win+X` | Stop reading |
| `Ctrl+Win+Z` | Pause / Resume |

**Requirements:** Windows 10 or 11. An NVIDIA GPU (GTX 1650 or better) is recommended for fast synthesis; CPU mode works but is slower.

## What's new in 1.3.0

- **Pronunciation list.** Names and brands can be given exact pronunciations, for example "Cowork" as "Co work" (see [Pronunciation list](#pronunciation-list)).
- **Spoken emphasis.** Words in **bold** or *italics*, and words in ALL CAPS like "NOT" (but not acronyms like "API"), are said a little slower, higher and louder (see [Spoken emphasis](#spoken-emphasis)).

What you see on screen is never changed; only the spoken copy is.

## What's new in 1.2.0

Smoother, more natural reading:

- **Sentences split where they really end.** "Dr. Smith", "e.g.", "U.S. Army", "J. R. R. Tolkien", "3.14" and "v1.2.0" no longer break a sentence in two. Text copied from PDFs or email (with a line break in mid-sentence) reads as one sentence.
- **Natural pauses.** Each pause has a set length: short at a comma, medium at a sentence end, longer at a paragraph or heading. The long silences between sentences are gone.
- **Faster start.** The next sentence is prepared while the current one plays, so speech starts sooner (time to first audio is 60–77% shorter in testing) and there's no wait between sentences.
- **Reads markdown, code and symbols sensibly.** It says "Table" and "Row 1"; strikethrough as "begin strike … end strike"; emoji by name ("check mark"). Code blocks become "Code block skipped." Paths and URLs read naturally ("src slash app dot py"), and so do dates ("October 17th, 2026"), versions ("version 1 point 2 point 0"), units ("25 millimeters"), "16:9" ("16 by 9"), and symbols like ≥ and →.
- **No dropped words.** Some numbers and words that were silently skipped before are now spoken.

---

*The sections below are for developers who want to run from source or build the installer themselves.*

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

**Note:** The first run downloads the Kokoro model (~350 MB). This is cached automatically for future runs. Running from source can also use a local model folder instead (config.json, kokoro-v1_0.pth, voices\): set `NVTTS_MODEL_DIR` to it, or keep a previous build in `dist\NaturalVoiceTTS\kokoro_model`.

### Tests

```bash
python -m pytest tests -q
```

`tests/README.md` describes the rendering and timing scripts (sample passages, pause measurement, time-to-first-audio A/B).

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

### Pronunciation list

Names and brands the voice gets wrong can be given exact phonemes (misaki's phoneme set, the one
Kokoro uses). The app ships a built-in list in `assets\pronunciations.json`; your own entries go in
`%APPDATA%\NaturalVoiceTTS\pronunciations.json` and win over the built-in ones:

```json
{
  "Cowork": "kˈO wˈɜɹk"
}
```

A word matches whole, in any capitalization, unless the entry has a capital inside a word
(`"iOS"`, `"SQL"`): then only that spelling matches. `'s` is handled for you. Only the spoken
copy changes; the text on screen doesn't. Edits apply from the next message, no restart.

### Spoken emphasis

Words in `**bold**`, `*italics*` or `_italics_`, and ALL-CAPS words that are shouted rather than
acronyms ("NOT", "NEVER", but not "API" or "GPU"), are said a little slower, higher and louder:
measured on a test sentence, the word took about 20% longer and was about 8% higher in pitch (about
1.3 semitones) and 1.8 dB louder. This happens in Kokoro's single pass over the sentence, so there's no seam
and the rest of the sentence keeps its rhythm. Headings, spans longer than five words, and lines
written entirely in capitals are read plain. It's on by default; to turn it off, set
`EMPHASIS_ENABLED = False` in `src/emphasis.py`. The strengths are the constants beside it. How it was
chosen, with measurements: `tests/emphasis/FINDINGS.md`.

### Terminal Mode (fallback)

```bash
python src/main.py
```

### Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Win+T` | Read selected text |
| `Ctrl+Win+X` | Stop reading |
| `Ctrl+Win+Z` | Pause / Resume |

1. Select text in any application (browser, editor, PDF viewer, etc.)
2. Press `Ctrl+Win+T` — the text is copied and read aloud
3. Press `Ctrl+Win+X` to stop or `Ctrl+Win+Z` to pause/resume

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
4. Run Inno Setup to produce `dist\NaturalVoiceTTS_Setup_1.3.0.exe` (if Inno Setup is installed)

PyInstaller replaces `dist\NaturalVoiceTTS\` on every build, including its `kokoro_model` folder, and the model is then copied back from the HuggingFace cache. Make sure the cache has the model before building.

The installer installs to `C:\Program Files\NaturalVoiceTTS\` with Start Menu and optional desktop shortcuts. The uninstaller appears in "Add or Remove Programs".

**Expected size**: ~2-3 GB (PyTorch with CUDA is the largest component).

## Project Structure

```
src/
  app.py            — System tray application (primary entry point)
  main.py           — Terminal-mode entry point (fallback)
  tts_engine.py     — Kokoro TTS wrapper (model loading, synthesis)
  text_processor.py — Sentence splitting and text cleanup
  normalizer.py     — Spoken copy of the text (markdown, numbers, paths, symbols)
  lexicon.py        — Pronunciation list applied to the spoken copy
  emphasis.py       — Spoken emphasis for bold, italic and ALL-CAPS words
  pauses.py         — Pause lengths between and inside sentences
  audio_player.py   — Audio playback with stop/pause/resume
  hotkeys.py        — Global hotkey listener and clipboard grab
  config.py         — Persistent JSON settings
  dialogs.py        — Help and About tkinter dialogs
assets/
  icon.ico          — System tray icon
  pronunciations.json — Built-in pronunciation list
installer/
  setup.iss         — Inno Setup installer script
tests/              — Unit tests, sample passages, render and timing scripts
```

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

This software includes [Kokoro TTS](https://github.com/hexgrad/kokoro) by Hexgrad, licensed under the Apache License 2.0. See [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for full attribution.
