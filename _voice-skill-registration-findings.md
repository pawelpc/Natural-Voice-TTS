# Closeout: Voice-TTS Skill Registration — Findings & Recommended Plan

**To:** Manager agent
**From:** Opus 4.8 (Claude Code session, Natural_Voice_TTS)
**Date:** 2026-07-01
**Companion doc:** `_bugfix-closing-report.md` (the D1/D2/D3 pipe fix — separate, already done)

---

## TL;DR

Two different problems got conflated under "voice drops content":

1. **Transport (SOLVED, verified):** the named-pipe reader dropped tail sentences on short reads. Fixed (D1/D2/D3), rebuilt, reinstalled, and verified live — the pipe now delivers 100% of what it's sent, including a 3091-byte / 20-sentence payload. See `_bugfix-closing-report.md`.

2. **Agent behavior (ROOT CAUSE FOUND, fix staged, not yet registered):** the agent keeps sending a *different* text to speech than it shows on screen (condensing, rewording, expanding numerals, or stopping after one turn). We traced this to a **skill-discovery failure**: the `natural-voice-tts` skill is stored where **Cowork never reads it**, so none of its rules were ever in the agent's context. This doc is about #2.

---

## What we found (skill discovery)

There are **two separate skill systems** on this machine:

| System | Location | How it activates | Our skill was here? |
|---|---|---|---|
| **Plugin/manifest skills** (docx, pdf, xlsx, schedule, skill-creator…) | `…\Claude\local-agent-mode-sessions\skills-plugin\<…>\<account>\` with `.claude-plugin/plugin.json` + `manifest.json` + `skills/` | Auto-trigger by description (this is what makes "make a word doc" load `docx`) | **No** |
| **Loose folder skills** (vault-interview) | `%APPDATA%\Claude\skills\<name>\SKILL.md` | Explicit only (`/name` slash command, read at startup); **Cowork does not index this folder** | **Yes** — `install_config.py` put it here |

**Decisive verification:** In a Cowork session, typing `/` lists only `add-files, export, context, design, schedule, setup-cowork, skill-creator`. Both loose-folder skills (`natural-voice-tts` **and** the user's own `vault-interview`) are **absent**; only manifest-registered skills appear. So the loose folder `install_config.py` writes to is a dead location for Cowork.

**Consequence:** every earlier attempt to fix behavior by editing `SKILL.md` wording (three rounds) was wasted — Cowork never loaded the file. The agent even said so verbatim: *"there's no skill document… the only instructions I have are the tool's own description."*

Note: `PHASE6_COMPLETION_REPORT.md` claims the skill "triggers on 'voice on'… installed automatically to `%APPDATA%\Claude\skills\`." That claim is now known to be **false for Cowork** — left in place as history; this doc supersedes it.

## What the user actually wants (their words)

- **"Court reporter, not an actor."** Speak back exactly what was written — no words added, dropped, reworded, or summarized. One response, identical to screen and speech.
- Numerals read naturally as numbers (e.g. "Louis XVI" → "Louis the sixteenth") is **fine** — that's human reading, not changing words.
- He wants the **skill mechanism to actually work** in both Cowork and Code, not a workaround (he explicitly rejected relying only on the MCP tool description).

## What has been done this session (staged in the repo)

- **D1/D2/D3 pipe fix** — committed (`bba2200`), rebuilt, reinstalled, verified live.
- **Skill content finalized** with the court-reporter rule (verbatim words, numerals-as-numbers allowed, nothing added/dropped/changed, speak every turn until voice off, brevity-preference override).
- **Repackaged as an installable plugin** at `mcp_tts_server/plugin/`:
  - `.claude-plugin/plugin.json`
  - `skills/natural-voice-tts/SKILL.md`  ← single source of truth now
  - old `mcp_tts_server/skill/` removed.
- **`install_config.py` fixed:** points at the plugin skill, **overwrites** on reinstall (previously it silently skipped if a copy existed — that's why stale skill text persisted), and now prints Cowork import instructions.

## Recommended plan (what still needs doing)

1. **Register the plugin the supported way — do NOT hand-edit the managed `manifest.json`.** The manifest is Anthropic-managed and appears to re-sync, which would wipe a manual entry. Instead, in a **Cowork** session run `/skill-creator` (or `/create-cowork-plugin`) and point it at:
   `mcp_tts_server/plugin/skills/natural-voice-tts/SKILL.md`
   Goal: get it into the manifest system so it **auto-triggers on "voice on"** like `docx`/`pdf` do.
2. **Verify** after registration: `/` (or a "voice on" request) should now surface/activate the skill; confirm the agent loads the SKILL.md and speaks verbatim.
3. **For Claude Code specifically:** the same plugin can be installed via the Code plugin mechanism (`~/.claude/plugins` / marketplace), or the skill placed in a project `.claude/skills/`. `%APPDATA%\Claude\skills` is not the Code personal-skills path either.
4. **Open uncertainty (flagged honestly):** the exact hand-off to register a *custom* (non-Anthropic) skill into the Cowork manifest is undocumented and could not be fully tested from Claude Code. Routing through `/skill-creator` / `/create-cowork-plugin` is the safest supported path; if it does not land the skill, the fallback is a proper marketplace-installed plugin.
5. **Optional hardening (future):**
   - Bundle the MCP server registration *into* the plugin (so one install provides both the tool and the skill).
   - Even with a loaded skill, verbatim compliance is still model discipline. If it recurs, the only hard guarantee is a Desktop-level "speak the actual assistant message" feature — not achievable from within this MCP architecture (the tool only sees the text the model hands it).

## Ceiling to set expectations

Getting the skill to load will fix the *systemic* cause (rules never reaching the agent). It will not make compliance provably 100% — a skill is still an instruction. Expect a large improvement, not a mathematical guarantee.
