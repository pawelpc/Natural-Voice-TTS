# Team Lead Brief: Natural Voice TTS — Phase 6: Installer with MCP Server + Generic Paths

**Prepared by:** Manager Agent
**Date:** 2026-05-02
**Model:** Sonnet
**Prerequisite:** Phases 1-3 verified, Phase 4 (installer) complete, Phase 5 (MCP server + pipe listener) complete
**Deliverables:** Updated `installer/setup.iss`, updated `build.bat`, updated `mcp_tts_server/server.py`, new `mcp_tts_server/install_config.py` helper script, updated `mcp_tts_server/README.md`, version bump to 1.1.0, git commit

---

## Project Summary

Update the Natural Voice TTS installer to bundle the MCP TTS server so that end users get Claude Desktop integration out of the box. All hardcoded paths must be replaced with generic, install-location-relative paths so the app works on any Windows 10/11 machine.

**The key problem:** Right now `server.py` works, the pipe listener works, but:
1. The MCP server is not included in the installer — users would have to set it up manually
2. The Claude Desktop config in the README uses Paul's hardcoded path (`C:\Users\paulp\...`)
3. There's no automated way for an end user to configure Claude Desktop to find the MCP server

---

## What You're Building

### Part A: Bundle MCP Server in Installer

**Modify:** `installer/setup.iss`

Add the MCP server files to the installer so they're installed alongside the main app:

- Install `mcp_tts_server/server.py` → `{app}\mcp_server\server.py`
- Install `mcp_tts_server/run_server.bat` → `{app}\mcp_server\run_server.bat`
- Install `mcp_tts_server/requirements.txt` → `{app}\mcp_server\requirements.txt`
- Install `mcp_tts_server/README.md` → `{app}\mcp_server\README.md`
- Install new `mcp_tts_server/install_config.py` → `{app}\mcp_server\install_config.py`

Add a post-install task option (checkbox on the final screen, checked by default):
- "Configure Claude Desktop for voice output"
- When checked, runs `install_config.py` which patches the Claude Desktop config

### Part B: Generic Path Resolution

**Modify:** `mcp_tts_server/server.py`

The server itself is already path-independent (it just connects to a named pipe by name, no file paths). No changes needed to the core logic.

**Modify:** `mcp_tts_server/run_server.bat`

Currently uses `%~dp0` which is already generic (resolves to the bat file's own directory). Verify this works from the installed location. Should be fine.

**Modify:** `mcp_tts_server/README.md`

Replace Paul's hardcoded path in the Claude Desktop config example with a generic pattern:

```json
{
  "mcpServers": {
    "natural-voice-tts": {
      "command": "python",
      "args": ["C:\\Program Files\\NaturalVoiceTTS\\mcp_server\\server.py"]
    }
  }
}
```

Add a note that the path depends on where the user installed the app. Document the default location.

Also add a note about `install_config.py` — users who didn't check the box during install can run it manually.

### Part C: Claude Desktop Config Helper Script

**Create:** `mcp_tts_server/install_config.py`

A standalone Python script that automatically patches the Claude Desktop config file. This is the key to making it work for any user on any machine.

**Behavior:**
1. Locate the Claude Desktop config at `%APPDATA%\Claude\claude_desktop_config.json`
   - If the file doesn't exist, create it with just the MCP server entry
   - If the file exists, read it, add/update the `natural-voice-tts` entry under `mcpServers`, preserve all other entries
2. Determine its own installed location (the directory this script is in) to build the correct `server.py` path
3. Write the updated config
4. Print a clear success message with the path that was configured
5. If Claude Desktop is running, advise the user to restart it

**Critical design points:**
- Must work whether invoked from the installer (via `{app}\mcp_server\install_config.py`) or run manually by the user
- Must NOT clobber existing MCP server entries in the config — only add/update `natural-voice-tts`
- Must handle the case where `%APPDATA%\Claude\` doesn't exist (Claude Desktop not installed) — print a clear message and exit gracefully
- Use `os.path.dirname(os.path.abspath(__file__))` to find its own location, then construct the path to `server.py` in the same directory
- Escape backslashes properly in the JSON output

**Example output config:**
```json
{
  "mcpServers": {
    "existing-server": { "...": "..." },
    "natural-voice-tts": {
      "command": "python",
      "args": ["C:\\Program Files\\NaturalVoiceTTS\\mcp_server\\server.py"]
    }
  }
}
```

### Part D: Installer Integration

**Modify:** `installer/setup.iss`

Add a post-install run entry for the config helper:

```iss
[Tasks]
Name: "claudeconfig"; Description: "Configure Claude Desktop for voice output (requires Claude Desktop installed)"; GroupDescription: "Claude Desktop Integration"; Flags: unchecked

[Run]
Filename: "python"; Parameters: """{app}\mcp_server\install_config.py"""; StatusMsg: "Configuring Claude Desktop..."; Tasks: claudeconfig; Flags: nowait postinstall skipifsilent runhidden
```

**Note:** The checkbox should be **unchecked by default** because:
- Not all users will have Claude Desktop installed
- Not all users will have Python in their PATH (the main app is frozen via PyInstaller, but the MCP server needs system Python + `mcp` package)

Also add a [Run] entry for an uninstall step that removes the MCP config entry (or document that users should remove it manually).

### Part E: Build Script Updates

**Modify:** `build.bat`

1. Copy `mcp_tts_server/` into the dist folder before running Inno Setup:
   ```bat
   echo [X/X] Copying MCP server files...
   xcopy /E /I /Y "mcp_tts_server" "%DIST_DIR%\mcp_server" >nul
   ```

2. Update the version to 1.1.0 throughout

### Part F: Version Bump

Update version from 1.0.0 to 1.1.0 in:
- `installer/setup.iss` (`MyAppVersion`)
- `build.bat` (installer output filename, if referenced)
- `src/dialogs.py` (About dialog version string)
- Any other files that reference the version

---

## Files to Read Before Writing

1. `_team-lead-brief.md` — full project spec including Phase 4 details
2. `_team-lead-instructions.md` — code style and patterns
3. `installer/setup.iss` — current Inno Setup script
4. `build.bat` — current build pipeline
5. `mcp_tts_server/server.py` — the MCP server you're bundling
6. `mcp_tts_server/run_server.bat` — the launcher script
7. `mcp_tts_server/README.md` — current docs (has hardcoded paths)
8. `src/dialogs.py` — About dialog (version string lives here)

---

## Build Order

1. `mcp_tts_server/install_config.py` — CREATE — the config helper script (core deliverable)
2. `mcp_tts_server/README.md` — MODIFY — generic paths, document install_config.py
3. `installer/setup.iss` — MODIFY — add MCP server files, post-install task
4. `build.bat` — MODIFY — copy MCP server to dist, version bump
5. `src/dialogs.py` — MODIFY — version 1.1.0 in About dialog
6. Review all changes for hardcoded paths — grep for `paulp`, `C:\Users\paulp`, or any user-specific paths

---

## Acceptance Criteria

- [ ] `install_config.py` correctly patches Claude Desktop config with the right path to `server.py`
- [ ] `install_config.py` preserves existing MCP server entries in the config
- [ ] `install_config.py` handles missing Claude Desktop gracefully (clear message, no crash)
- [ ] `install_config.py` determines its own path dynamically (no hardcoded paths)
- [ ] `installer/setup.iss` bundles `mcp_server/` directory with all MCP server files
- [ ] Installer offers optional "Configure Claude Desktop" checkbox (unchecked by default)
- [ ] `build.bat` copies MCP server files into dist before Inno Setup runs
- [ ] `mcp_tts_server/README.md` uses generic paths in all examples
- [ ] No file in the project contains Paul's username or hardcoded user-specific paths
- [ ] Version is 1.1.0 in setup.iss, dialogs.py, and any other version references
- [ ] All changes committed to git with a descriptive message

---

## Design Constraints

1. **No hardcoded user paths**: Everything must resolve dynamically — `%APPDATA%`, `os.path.dirname(__file__)`, `{app}`, etc.
2. **Non-destructive config patching**: `install_config.py` must never delete or overwrite other MCP server entries
3. **Graceful degradation**: If Claude Desktop isn't installed, the installer still works — the MCP server files are installed, user just configures later
4. **The MCP server still requires system Python + `mcp` package**: The frozen PyInstaller app can't run the MCP server because it needs the `mcp` pip package. Document this dependency clearly in the README.
5. **Existing functionality unchanged**: The TTS app, hotkeys, pipe listener, and audio pipeline must work exactly as before

---

## What You Are NOT Building

- No auto-start for the MCP server (it's started by Claude Desktop on demand via stdio)
- No bundling Python itself into the installer
- No PyInstaller freezing of the MCP server (it's a tiny script, system Python is fine)
- No changes to pipe_listener.py, tts_engine.py, audio_player.py, or hotkeys.py
- No new TTS features or voices

---

## Known Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| User doesn't have Python in PATH | Document prerequisite in README and installer; `install_config.py` is Python so it will fail obviously if Python isn't available |
| User doesn't have `mcp` package installed | README documents `pip install -r requirements.txt`; `install_config.py` can check and warn |
| Claude Desktop config format changes | Use standard JSON read/write; the `mcpServers` key is the documented stable format |
| Existing claude_desktop_config.json has comments or non-standard JSON | Use `json.loads/dumps` — will fail on non-standard JSON. Document this edge case. |
| Multiple Python installations (conda, pyenv, etc.) | Document that `python` in PATH must have `mcp` and `pywin32` installed |

---

## Git Closing Procedure

**Before ending the session**, commit all changes to git:

```bash
git add -A
git status
git commit -m "Phase 6: Bundle MCP server in installer, generic paths, version 1.1.0"
```

If the commit fails due to a lock file, document the exact commands for Paul to run manually.

---

## Testing Notes

You are in a sandbox and cannot run Windows-specific code. Write all files, review them carefully, and document a manual test procedure Paul can follow:

1. Run `python mcp_tts_server/install_config.py` standalone — verify it patches the Claude Desktop config correctly
2. Run `build.bat` — verify MCP server files appear in `dist/NaturalVoiceTTS/mcp_server/`
3. Run the Inno Setup installer — verify MCP server files are installed to `C:\Program Files\NaturalVoiceTTS\mcp_server\`
4. If "Configure Claude Desktop" was checked, verify `%APPDATA%\Claude\claude_desktop_config.json` has the correct entry
5. Restart Claude Desktop — verify `speak` and `stop_speaking` tools appear
6. Tell Claude "speak your responses" — verify audio plays through the tray app
