---
name: natural-voice-tts
description: "Activate or deactivate spoken voice output via Natural Voice TTS. Use this skill whenever the user says 'voice on', 'speak your responses', 'read aloud', 'read this aloud', 'say this out loud', 'voice off', 'stop speaking', 'be quiet', 'mute', or any variation asking Claude to speak responses aloud or stop doing so. Also use when the user asks about voice output status or wants to toggle TTS. This skill MUST be used even for short requests like 'voice on' — it handles the required tool loading step that makes spoken output work."
---

# Natural Voice TTS — Voice Activation Skill

This skill controls spoken voice output through the Natural Voice TTS system tray app. The TTS tools are registered as **deferred tools** — they exist but their schemas aren't loaded into context by default. You must load them before calling them, or the calls will fail.

## Step 1: Load the TTS tools

Before doing anything else, call `ToolSearch` to load the tool schemas:

```
ToolSearch({ query: "select:mcp__natural-voice-tts__speak,mcp__natural-voice-tts__stop_speaking", max_results: 2 })
```

This is not optional. The tools will fail with `InputValidationError` if you skip this step. Wait for the result before proceeding.

## Step 2: Determine intent

- **Voice ON** (user said "voice on", "speak your responses", "read aloud", or similar): Confirm that voice is now active. From this point forward, after every text response you send, also call `mcp__natural-voice-tts__speak` with your full response text. Continue doing this for all subsequent messages until the user says to stop.

- **Voice OFF** (user said "voice off", "stop speaking", "be quiet", "mute", or similar): Call `mcp__natural-voice-tts__stop_speaking` to halt any current playback immediately. Stop calling `speak` on future responses.

- **One-shot read** (user said "read this aloud", "say this out loud", or similar about specific content): Call `mcp__natural-voice-tts__speak` with the specified text. Don't continue speaking on future messages unless asked.

## Step 3: Ongoing behavior (voice ON mode)

When voice is active, follow this pattern for every response:

1. Write your normal text response first
2. Then call `mcp__natural-voice-tts__speak` with the full text of that response
3. Keep doing this until the user deactivates voice

**Send the complete response, verbatim.** Pass the *same* text you wrote to chat — every sentence, in order, from the first word to the last. Never summarize, shorten, excerpt, paraphrase, or send only the beginning of your response. The spoken words must match the written words. Sending a partial or reduced version produces a jarring mismatch between what the user reads and what they hear, and is explicitly not wanted.

**Never maintain two versions — this applies in *both* directions.** Do not write a short or condensed chat reply and speak a longer one, and do not speak a short version of a longer written reply. Produce exactly one response and use that identical string for both the screen and `speak()`.

**Voice ON overrides any brevity preference.** If you have a standing instruction or preference to keep chat replies short, concise, or direct, it still governs *how long that single response is* — but it must never cause the visible text and the spoken text to differ. Decide the length once, based on what the user actually asked for, then send that exact text to both channels. If the user asks for a long, detailed, or "page-length" answer, the chat text is that full length too — do not condense the on-screen copy. When in doubt, both channels get the fuller text; matching the two channels always takes priority over brevity while voice is on.

The TTS app handles sentence splitting, so send the complete response text in one call — don't split it yourself.

## Important notes

- The Natural Voice TTS tray app must be running for this to work. If you get a "Named pipe not found" error, tell the user to start the TTS app first (and give it a few seconds — the engine loads a model on startup before the pipe accepts input).
- The user can also control playback with keyboard shortcuts: Ctrl+Win+X stops, Ctrl+Win+Z pauses/resumes.
- You may strip pure markdown *formatting characters* (e.g. `**`, `#`, backticks) so they aren't read aloud, but do **not** remove, shorten, or reword any actual sentences — words spoken must equal words written. The TTS app handles normal punctuation and Unicode (em dashes, curly quotes, ellipses) correctly, so there is no need to strip or alter those.
