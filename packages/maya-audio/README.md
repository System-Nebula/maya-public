# maya-audio

The audio bounded context for Maya. One package, three modes, one DRY backend layer.

Steering spec: [docs/maya-audio-domain-summary.md](../../docs/maya-audio-domain-summary.md)
(public summary; detailed spec in `Vault/quartz-site/content/maya-architecture/maya-audio-domain.md`).

## Modes

| Mode | Driver | Surfaces |
|---|---|---|
| Realtime stream | `StreamSession` | gateway form dictation, Discord VC, live ingest |
| Batch job | `BatchJobRunner` | video→transcript, RSS→audio, audiobook chapters |
| Turn loop | `maya-voice` `TurnLoop` (consumes these backends) | full voice assistant |

## Backends (DRY)

`backends/base.py` defines `BaseInferenceBackend`; ASR backends override `_infer`, TTS
backends override `_synthesize`. Shared audio I/O lives once in `backends/_audio.py`.

- Defaults: `FakeAsrBackend`, `FakeTtsBackend` — zero GPU, used by CI and the gateway stubs.
- Stubs (GPU follow-on): `FasterWhisperBackend`, `OnnxParakeetBackend`, `Qwen3TtsBackend`.

## Quick start

```bash
uv run pytest packages/maya-audio        # all fake-backed, no CUDA
```

Mount the FastAPI router (needs the `[http]` extra, which the gateway already provides):

```python
from maya_audio.router import make_audio_router
app.include_router(make_audio_router())   # /api/audio/{models,stream,jobs}
```

## Pass 1 scope

Architecture + fake-backed stubs. Real GPU inference, arena (`arena-core`), feedback
persistence (`maya-db`), Parakeet ONNX, and live Discord are explicit follow-ons — see the
spec's "Follow-on" section.
