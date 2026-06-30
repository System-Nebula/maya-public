# Discord Shim

Public-safe HTTP glue placeholder for Discord integrations.

This app should not contain private commands, tool orchestration, internal
capabilities, or sensitive policy decisions.

## Audio handoff (maya-audio boundary)

The shim is the Discord VC → gateway boundary for the realtime audio domain. The contract
and gateway endpoints exist as pass-1 stubs; live voice receive is a follow-on.

Handoff sequence (target):

1. Shim opens a session: `POST /api/audio/discord/session` with an `AsrSessionOpen`
   (`surface = "discord_vc"`). The gateway returns the WS `stream_path`.
2. Shim captures per-user PCM from the voice channel and proxies 16 kHz mono int16 frames
   into `WS /api/audio/stream` (the same plane the browser dictation SDK uses).
3. Transcript events (`AsrTranscriptEvent`) flow back over the WS; the shim relays them.

The shim **does not** choose models, run VAD, or store feedback — those belong to
`maya-audio` (`StreamSession`, backends) per the domain boundaries. See
[docs/maya-audio-domain-summary.md](../docs/maya-audio-domain-summary.md).

