# Team Lead Instructions: Natural Voice TTS — Phase 6

## Startup Command

At the start of your session, read these files in order:
1. `_team-lead-brief.md` — Phases 1-4 spec (full architecture)
2. `_team-lead-brief-phase5.md` — Phase 5 spec (MCP server + pipe listener)
3. This file (`_team-lead-instructions-phase6.md`)
4. `installer/setup.iss` — current Inno Setup script you're modifying
5. `build.bat` — current build pipeline you're modifying
6. `mcp_tts_server/server.py` — MCP server you're bundling
7. `mcp_tts_server/README.md` — docs you're updating
8. `src/dialogs.py` — About dialog (version string)

## Build Order

Follow this sequence. Each step builds on the previous.

### Step 1: `mcp_tts_server/install_config.py` — CREATE
The config helper script. This is the core deliverable. Key points:
- Use `os.environ.get('APPDATA')` to find Claude Desktop config location
- Use `os.path.dirname(os.path.abspath(__file__))` to find its own location
- Read/write with `json.load`/`json.dump` (indent=2 for readability)
- If `mcpServers` key doesn't exist in existing config, create it
- Always use forward slashes or properly escaped backslashes in the JSON path
- Print clear output: what was done, what path was configured, reminder to restart Claude Desktop
- Include a `--remove` flag that deletes the `natural-voice-tts` entry (for uninstall)

### Step 2: `mcp_tts_server/README.md` — MODIFY
- Replace all instances of Paul's path with generic `C:\Program Files\NaturalVoiceTTS\mcp_server\`
- Add section about `install_config.py` usage
- Add section about prerequisites (Python 3.11+, `mcp` package, `pywin32`)
- Keep the architecture diagram and troubleshooting table

### Step 3: `installer/setup.iss` — MODIFY
- Bump `MyAppVersion` to `1.1.0`
- Add `[Files]` entries for the MCP server directory
- Add `[Tasks]` entry for Claude Desktop config (unchecked by default)
- Add `[Run]` entry for `install_config.py` (conditional on task checkbox)
- Consider adding an uninstall step that runs `install_config.py --remove`

### Step 4: `build.bat` — MODIFY
- Add a step to copy `mcp_tts_server/` to `dist/NaturalVoiceTTS/mcp_server/`
- Update version references to 1.1.0
- Renumber steps if adding a new one

### Step 5: `src/dialogs.py` — MODIFY
- Update version string to `1.1.0`

### Step 6: Path audit
- `grep -r "paulp" .` or equivalent — verify no user-specific paths remain
- Check `README.md`, `mcp_tts_server/README.md`, any other docs
- Check `server.py`, `run_server.bat`

### Step 7: Git commit
- Stage all changes: `git add -A`
- Review staged files: `git status`
- Commit: `git commit -m "Phase 6: Bundle MCP server in installer, generic paths, version 1.1.0"`
- If git commit fails (lock file, permissions), document the exact commands Paul should run

## Code Style

Match the existing codebase:
- Python 3.11, type hints on function signatures
- Docstrings on all public functions
- Use `logging` module (not print) — except in `install_config.py` where print is appropriate (it's a user-facing CLI script)
- Constants at top of module

## Important Technical Notes

### Claude Desktop Config Location
```python
config_dir = os.path.join(os.environ.get('APPDATA', ''), 'Claude')
config_file = os.path.join(config_dir, 'claude_desktop_config.json')
```

### Self-Locating Pattern for install_config.py
```python
# Where is this script installed?
script_dir = os.path.dirname(os.path.abspath(__file__))
server_path = os.path.join(script_dir, 'server.py')

# Convert to the format Claude Desktop expects (escaped backslashes in JSON)
# json.dump handles this automatically
```

### Inno Setup File Entries
```iss
; MCP Server files
Source: "..\dist\NaturalVoiceTTS\mcp_server\*"; DestDir: "{app}\mcp_server"; Flags: ignoreversion recursesubdirs createallsubdirs
```

### Inno Setup Post-Install Task
```iss
[Tasks]
Name: "claudeconfig"; Description: "Configure Claude Desktop for voice output"; GroupDescription: "Claude Desktop Integration"; Flags: unchecked

[Run]
Filename: "python"; Parameters: """{app}\mcp_server\install_config.py"""; Tasks: claudeconfig; Flags: nowait postinstall skipifsilent runhidden
```

## Reporting & Closing

When you complete work or hit a blocker:
1. Write a brief status note at the bottom of the main `_team-lead-instructions.md` under `## Session Notes`
2. Commit all changes to git (see Step 7 above)
3. If git fails, write the exact commands Paul should run in your session notes

## What You Are NOT Doing

- No changes to the TTS engine, audio pipeline, pipe listener, or hotkey system
- No PyInstaller freezing of the MCP server
- No bundling of Python itself
- No auto-start mechanism for the MCP server
- No new features beyond what's specified in the brief
