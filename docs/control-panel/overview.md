title: Control Panel Overview
description: The operator voice control panel — layout, sections, and how settings persist.

# Control Panel Overview

The **Voice Control Panel** is a configuration surface for the operator's
audio + conversational pipeline. It is a drop-in Alpine.js SDK that mounts on
any server-rendered surface; the reference deployment is served at
`/sdk/kitchen-sink.html`.

## Sections

| Section | Purpose |
|---------|---------|
| [Audio Interfaces](/guide/control-panel/audio-interfaces) | Pick capture/playback hardware; monitor live input |
| [Detection Engine](/guide/control-panel/detection-engine) | Gate when the operator is speaking (pipeline step 1) |
| [Dictation (Wispr)](/guide/control-panel/dictation) | Transcription model + text-cleanup defaults |
| [Reasoning](/guide/control-panel/reasoning) | Model that composes Maya's conversational turn |

## How settings persist

Every control maps to a field on `OperatorVoiceSettings`. The panel:

1. Loads catalog + defaults from `GET /api/voice/settings/defaults`.
2. Merges any operator overrides saved in `localStorage` (`maya.voice.settings.v1`).
3. Writes back to `localStorage` on every change.

All panels share one `Alpine.store("mayaVoice")`, so a change in one section is
reflected everywhere instantly — no reload, no network round-trip.

!!! tip "Defaults are server-owned"
    The catalog of available models, languages, and detection modes comes from
    the API, so adding a new model server-side surfaces it in the panel with no
    front-end change.
