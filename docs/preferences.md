title: User Preferences
description: How operator preferences persist, sync, and reset.

# User Preferences

Operator preferences are **local-first**: defaults come from the server, and
per-operator overrides live in the browser so the UI stays instantaneous.

## Persistence model

| Concern | Mechanism |
|---------|-----------|
| Server defaults + catalog | `GET /api/voice/settings/defaults` |
| Operator overrides | `localStorage["maya.voice.settings.v1"]` (JSON) |
| Cross-component sync | `Alpine.store("mayaVoice")` (single source of truth) |
| Docs language preference | `localStorage["maya.docs.lang"]` (see below) |

On load the panel reads server defaults, then shallow-merges stored overrides.
Every change writes the full settings object back to `localStorage`.

## The settings object

`OperatorVoiceSettings` (returned by the defaults endpoint):

```json
{
  "input_device_id": null,
  "output_device_id": null,
  "input_gain": 1.0,
  "noise_suppression": true,
  "detection_mode": "vad",
  "vad_threshold": 0.02,
  "vad_hangover_ms": 600,
  "push_to_talk_key": "Space",
  "wispr_model": "wispr-flow-1",
  "language": "en",
  "auto_punctuation": true,
  "filler_removal": true,
  "reasoning_model": "maya-reason-mini",
  "persona": "maya"
}
```

## Global language sync (docs)

These docs are polyglot. Selecting a language tab on **any** code block sets
your preference for **every** block on the page and persists it. Press
++cmd+k++ style isn't required — just click a tab, and reload to confirm it
sticks.

!!! tip "Resetting"
    Clear preferences by removing the `maya.voice.settings.v1` and
    `maya.docs.lang` keys from `localStorage`, or via your browser's site-data
    controls. The panel falls back to server defaults.
