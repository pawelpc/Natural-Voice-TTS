# Closing Report: Natural Voice TTS 1.3.0 — Release, Download Page, and Install Test

**Session lead:** Opus 4.8 (`claude-opus-4-8`) · **Work:** 2026-10-22 to 2026-10-25 · **For:** the manager
**Follows:** `_prosody-closing-report.md` (§Handoff) — this session executed that handoff and two
follow-on requests from Paul.

## Summary for the manager

- **v1.3.0 is built, verified, and published.** It is the release the prosody session handed off: the
  **pronunciation list** and **spoken emphasis** (on by default). Release:
  https://github.com/pawelpc/Natural-Voice-TTS/releases/tag/v1.3.0 — not a draft, installer asset attached.
- **The project now has a GitHub Pages download page**, matching Paul's other project pages, at
  https://pawelpc.github.io/Natural-Voice-TTS/. The repo's "About" homepage link points to it.
- **A full end-to-end install test passed on Paul's machine**: uninstall the old version → download the
  installer from GitHub → install → launch → internal pipeline test → speak the result through the
  freshly installed app. Every step passed.
- **Nothing is outstanding.** Two minor, expected side effects of the uninstall were handled (below).

## 1. Release of v1.3.0

**What shipped.** The two post-1.2.0 features from the prosody follow-up sessions:
- **Pronunciation list** — names and brands given exact phonemes; a built-in list ships with the app,
  the user's own entries in `%APPDATA%\NaturalVoiceTTS\pronunciations.json` win over it.
- **Spoken emphasis**, on by default — bold, italics, and shouted ALL-CAPS words (not acronyms) are
  said slightly slower, higher, and louder.

**Version bump (all six places from the handoff):** `installer/setup.iss`, `src/dialogs.py`,
`build.bat` (title + installer echo), `version_info.txt` (×4), and the README download link/filename.
README "What's new" reworked so 1.3.0 leads and the "not in the 1.2.0 installer" notes are gone;
`release_notes/1.3.0.md` written in the 1.2.0 style. Committed as **`fc832ab`**.

**Build.** Ran `build.bat` from PowerShell (the handoff's full-path `cmd /c` via the Bash tool was a
silent no-op — it opened cmd but did not run the script; running the batch directly from PowerShell
fixed it). Both handoff traps verified:
- **Trap 1 (model):** build log shows `Found model at: …\snapshots\local-from-dist`; the model in
  `dist` is SHA-256 identical to the cache copy.
- **Trap 2 (MCP files):** bundled `mcp_server` is byte-identical to the clean working tree (= HEAD).

**Verification before publishing.** 347 automated tests pass. Installer is
**1,885,172,774 bytes (~1.76 GiB)**, SHA-256 `124214DEFB692421CECC006DC36C01339DBF424BA05CE85CE9BB53DD47C84840`.
`_internal\assets\pronunciations.json` present (1 entry). Launch test against the `dist` build:
`Pronunciation list: 1 entries`, one `Playing [1/1]`, `Finished reading`, no `Skipped`; the playing
line read `Important: [Cowork](/kˈO wˈɜɹk/) is NOT down.`, confirming both features live.

**Publish (with Paul's go-ahead).** `git push origin master`, tag `v1.3.0`, push tag,
`gh release create` with the installer and `release_notes/1.3.0.md`. Release is public, not a draft,
asset state `uploaded`. The README's `releases/latest/download/…` link resolves to it.

## 2. GitHub Pages download page

Paul noted most of his repos have a static page and this one did not. I matched the style of the
closest sibling (`claude-desktop-indicator`, also a desktop app with a release download) and created
`docs/index.html`: hero with a direct download button, feature cards, "What's new in 1.3.0," install
steps, requirements, and an Apache-2.0 / Kokoro-attribution footer with the standard
"not affiliated with Anthropic" disclaimer. Committed as **`b75289a`**.

Enabled Pages on **`master /docs`** (this repo's default branch is `master`, not `main`). Verified
live: HTTP 200, serves the page, and the download button follows through to the real v1.3.0 asset
(final `Content-Length` = 1,885,172,774, exact match). Set the repo homepage field to the Pages URL.

## 3. End-to-end install test (on Paul's machine)

| Step | Result |
|---|---|
| Uninstall current version | Old version was **1.1.0** (not 1.2.0). Uninstalled elevated/silent; registry entry removed. |
| Download installer from GitHub | Downloaded the release asset; **byte-for-byte identical** (SHA-256) to the built installer. |
| Install | Silent install, exit 0; log "Installation process succeeded." Windows reports **1.3.0** (exe FileVersion 1.3.0.0), model + 27 voices + pronunciation list + MCP server all present. |
| Restore Claude config | Uninstaller removed the `natural-voice-tts` MCP entry; restored via the shipped `install_config.py`. Other servers untouched. |
| Internal test | Launched the installed app; `Pronunciation list: 1 entries`, one `Playing [1/1]`, `Finished reading`, no `Skipped`; played `Important: [Cowork](/kˈO wˈɜɹk/) is NOT down.` from `C:\Program Files\NaturalVoiceTTS`. |
| Speak via skill | Summary spoken through the installed app over MCP → named pipe → Kokoro → audio (9 sentences, no errors). Full chain confirmed. |

**Two expected side effects of uninstalling, both handled:**
- The uninstaller cleared `%APPDATA%\NaturalVoiceTTS` (voice/speed prefs). No custom pronunciation list
  existed there, so nothing meaningful was lost; the app recreated the folder with defaults on launch.
- It removed the voice MCP entry from Claude Desktop's config (restored from a backup taken first).
  The restored config takes full effect for **future** Claude Desktop sessions after the next restart.

## Follow-ups / notes

- **Pages download button is version-specific in the filename.** It uses
  `releases/latest/download/NaturalVoiceTTS_Setup_1.3.0.exe`, which auto-tracks the latest *release* but
  names the `1.3.0` file. When a future release changes the filename, update that one link on the page.
- **Optional cleanup not done (Paul chose to leave it):** the two merged branches
  `claude/jovial-hypatia-0d6e6d` and `claude/angry-engelbart-71f331` and their worktrees remain.

## Repo state at close

- Published commits on `master`: `fc832ab` (release 1.3.0) and `b75289a` (Pages page), pushed.
- Tag `v1.3.0` pushed; GitHub release live; GitHub Pages live; repo homepage set.
- Uncommitted/working files left as-is (not part of the release): `build.log` (generated) and the
  untracked working docs (`_prosody-*.md`, `_bugfix-closing-report.md`, `_bug-report-*.md`,
  `CANONICAL_SKILL.md`, and this report).
