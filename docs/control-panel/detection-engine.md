title: Detection Engine
description: Gate when the operator is speaking before audio reaches transcription.

# Detection Engine

**Pipeline step 1.** The detection engine decides *when the operator is
speaking* so only intentional speech is forwarded to transcription and
reasoning.

## Modes

| Mode | Value | Behavior |
|------|-------|----------|
| Voice activity | `vad` | Energy gate — speech starts when RMS crosses the threshold |
| Push to talk | `push_to_talk` | Speech only while the configured key is held |
| Continuous | `continuous` | Always-on, no gating |

## VAD settings

| Setting | Field | Default | Range |
|---------|-------|---------|-------|
| Activity threshold | `vad_threshold` | `0.02` | `0.0`–`0.3` (RMS) |
| Hangover | `vad_hangover_ms` | `600` | `100`–`1500` ms |
| Push-to-talk key | `push_to_talk_key` | `Space` | any key name |

The **threshold** is the RMS level above which speech onset is detected. The
**hangover** is how long silence must persist before a turn is considered
finished — it prevents clipping natural pauses mid-sentence.

!!! note "Live tuning"
    The Detection Engine panel renders a live level track with the threshold
    marked, so the operator can tune the gate against their actual mic noise
    floor in real time.

!!! danger "Too low a threshold"
    Setting `vad_threshold` near `0` makes background noise register as speech,
    flooding the pipeline with empty turns. Start at `0.02` and raise until the
    gate ignores room tone.
