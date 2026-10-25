# Canonical skill moved (MCP server stays here)

The `natural-voice-tts` **skill body** now lives in Paul's unified skills repo:
`C:\Users\paulp\Documents\Claude_Projects\_skills\skills\natural-voice-tts\SKILL.md` (the `paul-skills`
plugin, installed into both Claude Code and Cowork — see `_skills/sync.md`).

- The old in-app copy at `mcp_tts_server\plugin\skills\natural-voice-tts\SKILL.md` is now a **pointer**,
  not a body (rule R1, single source).
- `mcp_tts_server\install_config.py` still registers the **MCP server** (this app owns the server), and
  now copies the Desktop loose-skill from the canonical body above.
- No `.mcp.json` is bundled in `paul-skills` — the server registration stays with this app to avoid
  double-registration.

Edit the skill in the canonical file, then re-sync per `_skills/sync.md`.
