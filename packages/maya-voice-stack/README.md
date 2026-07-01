# Vendored from https://github.com/jov4n/voice-agent (Jovan's Qwen3 streaming voice demo).
#
# Core inference path: faster-whisper STT -> OpenAI-compatible streaming LLM -> faster-qwen3-tts.
# This package adds OTEL tracing, WAV replay benchmarks, and Playwright e2e coverage.

## Quick start (fake stack — no GPU)

```bash
export VA_FAKE_STACK=1
uv run --project packages/maya-voice-stack maya-voice-server
# open http://127.0.0.1:7861
# Mic click replays fixtures/audio/hello_maya.wav on the server (not browser mic).
```

**Note:** Live mic capture runs on the **machine hosting the server** via `sounddevice` + VAD, not in the browser.

## Full stack (GPU + OpenRouter DeepSeek)

```bash
export VA_LLM_BASE_URL=https://openrouter.ai/api/v1
export VA_LLM_API_KEY=$OPENROUTER_API_KEY
export VA_LLM_MODEL=deepseek/deepseek-chat-v3-0324
export VA_LLM_DISABLE_THINKING=1

# Langfuse / OTLP tracing (optional)
export OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64(public:secret)>"
export OTEL_SERVICE_NAME=maya-voice-stack

uv sync --project packages/maya-voice-stack --extra gpu
uv run --project packages/maya-voice-stack maya-voice-server
```

## Benchmarks

```bash
export VA_FAKE_STACK=1
make voice-stack-test
make voice-benchmark-fake

# GPU lane (self-hosted)
unset VA_FAKE_STACK
make voice-e2e-gpu
make voice-benchmark
```

## Playwright web transfer test

```bash
cd tests/e2e && bun x playwright test -c playwright.voice.config.ts
```

## WER

WER via `jiwer` is **deferred**. [`wer.py`](src/maya_voice_stack/wer.py) stubs the interface for a later ASR quality gate.
