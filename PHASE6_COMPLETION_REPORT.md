# Phase 6 Completion Report: Installer with MCP Server + Generic Paths

**Date:** 2026-05-02
**Status:** COMPLETE — all acceptance criteria met, installer tested and verified working
**Version:** 1.1.0

---

## Summary

Phase 6 bundled the MCP TTS server into the Windows installer so end users get Claude Desktop voice integration out of the box. All hardcoded user-specific paths were replaced with dynamic, install-location-relative resolution. A voice-activation skill was added to solve a deferred-tool loading issue discovered during testing.

---

## Deliverables

### Files Created

| File | Purpose |
|------|---------|
| `mcp_tts_server/install_config.py` | CLI helper that patches `%APPDATA%\Claude\claude_desktop_config.json` with the MCP server entry and installs the voice-activation skill. Supports `--remove` for clean uninstall. Uses self-locating path resolution (`os.path.dirname(__file__)`). Uses `cmd.exe /c run_server.bat` launch pattern per Phase 5 Microsoft Store Python lesson. |
| `mcp_tts_server/skill/SKILL.md` | Voice-activation skill for Claude Desktop. Triggers on "voice on", "speak your responses", "read aloud", "voice off", "stop speaking", "be quiet", etc. Calls `ToolSearch` to load deferred TTS tool schemas before invoking them — this was the fix for the MCP pipe issue. |

### Files Modified

| File | Changes |
|------|---------|
| `mcp_tts_server/README.md` | Replaced all `C:\Users\paulp\...` paths with generic `C:\Program Files\NaturalVoiceTTS\mcp_server\` examples. Added Prerequisites section (Python 3.11+, `mcp`, `pywin32`). Added `install_config.py` automatic setup section. Added Microsoft Store Python note. |
| `installer/setup.iss` | Version bumped to 1.1.0. Added `[Files]` entry for `mcp_server\*`. Added `[Tasks]` checkbox "Configure Claude Desktop" (unchecked by default). Added `[Run]` post-install entry for `install_config.py`. Added `[UninstallRun]` entry for `install_config.py --remove`. Added `__pycache__` cleanup for `mcp_server`. |
| `build.bat` | Added step 6/7: `xcopy` of `mcp_tts_server/` into `dist/NaturalVoiceTTS/mcp_server/`. Updated version references to 1.1.0. Renumbered all steps from 6 to 7. Updated title and installer output filename. |
| `src/dialogs.py` | `APP_VERSION` bumped to 1.1.0. Added "Claude Desktop Integration (MCP)" section to help text covering prerequisites, automatic/manual setup, usage instructions. Added "Claude Desktop Can't Speak" troubleshooting entry. |
| `_team-lead-instructions.md` | Appended Phase 6 session notes. |

---

## Acceptance Criteria — All Met

- [x] `install_config.py` correctly patches Claude Desktop config with the right path to `server.py`
- [x] `install_config.py` preserves existing MCP server entries in the config
- [x] `install_config.py` handles missing Claude Desktop gracefully (clear message, no crash)
- [x] `install_config.py` determines its own path dynamically (no hardcoded paths)
- [x] `install_config.py` installs voice-activation skill to `%APPDATA%\Claude\skills\`
- [x] `install_config.py --remove` cleans up both MCP config entry and skill
- [x] `installer/setup.iss` bundles `mcp_server/` directory with all MCP server files + skill
- [x] Installer offers optional "Configure Claude Desktop" checkbox (unchecked by default)
- [x] `build.bat` copies MCP server files into dist before Inno Setup runs
- [x] `mcp_tts_server/README.md` uses generic paths in all examples
- [x] No file in the project contains Paul's username or hardcoded user-specific paths
- [x] Version is 1.1.0 in setup.iss, dialogs.py, and build output references
- [x] Help dialog covers MCP setup, Claude Desktop JSON config, skill installation, and troubleshooting
- [x] Voice-activation skill correctly loads deferred TTS tools via ToolSearch
- [x] All changes committed to git

---

## Issue Discovered and Resolved

**Problem:** The MCP TTS tools (`speak`, `stop_speaking`) are registered as deferred tools in Claude Desktop, meaning their schemas aren't loaded into context by default. When a user said "voice on", Claude couldn't find the tools because it didn't know to call `ToolSearch` first.

**Solution:** Created a voice-activation skill (`mcp_tts_server/skill/SKILL.md`) that triggers on voice-related phrases and explicitly calls `ToolSearch` with `select:mcp__natural-voice-tts__speak,mcp__natural-voice-tts__stop_speaking` to load the tool schemas before using them. The skill is installed automatically by `install_config.py` to `%APPDATA%\Claude\skills\natural-voice-tts\`.

---

## Testing Performed

1. Built installer via `build.bat` — all 7 steps passed
2. Installed via `NaturalVoiceTTS_Setup_1.1.0.exe` with "Configure Claude Desktop" checked
3. Verified `install_config.py` patched Claude Desktop config correctly
4. Verified voice-activation skill was installed to `%APPDATA%\Claude\skills\`
5. Restarted Claude Desktop, started TTS tray app
6. Said "voice on" — Claude loaded tools via skill and spoke responses aloud
7. **Result: End-to-end flow working**

---

## Git Commits

1. `Phase 6: Bundle MCP server in installer, generic paths, version 1.1.0`
2. `Add voice-activation skill, update install_config.py and Help dialog for MCP/skill setup`

---

## Architecture After Phase 6

```
Installer (setup.iss)
  ├── NaturalVoiceTTS.exe          (PyInstaller frozen app)
  ├── espeak-ng/                   (phonemizer)
  ├── kokoro_model/                (weights + voices)
  └── mcp_server/
      ├── server.py                (MCP stdio relay)
      ├── run_server.bat           (cmd.exe wrapper)
      ├── install_config.py        (config + skill installer)
      ├── requirements.txt         (mcp, pywin32)
      ├── README.md                (docs)
      └── skill/
          └── SKILL.md             (voice-activation skill)

Runtime flow:
  User says "voice on" in Claude Desktop
    → Skill triggers, calls ToolSearch to load deferred tools
    → Claude calls mcp__natural-voice-tts__speak(text)
    → server.py receives via MCP stdio
    → server.py writes to \\.\pipe\NaturalVoiceTTS
    → TTS tray app synthesizes via Kokoro and plays audio
```

---

## No Remaining Work

All Phase 6 deliverables are complete and tested. The installer is ready for distribution.
