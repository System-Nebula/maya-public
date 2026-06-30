title: Overview
description: The Maya operator handbook — control panel features and user preferences.

# Maya Handbook

Documentation for the Maya operator surfaces. Every control-panel feature and
user application preference is documented here, rendered server-side from
plain Markdown (FastAPI + Jinja2) with light Alpine.js interactivity.

!!! note "Edit on GitHub"
    Every page has an **Edit this page** link in the footer. Docs are plain
    Markdown under `docs/` — open a PR and the change ships with the site.

## Sections

| Section | What's inside |
|---------|---------------|
| [Control Panel](/guide/control-panel/overview) | Audio routing, detection engine, dictation, and reasoning settings |
| [User Preferences](/guide/preferences) | How operator settings persist and sync |
| [Kitchen Sink](/guide/kitchen-sink) | Every rendering construct the docs engine supports |

## The voice pipeline

The control panel configures one pipeline:

1. **Listen** — the [Detection Engine](/guide/control-panel/detection-engine) gates speech.
2. **Transcribe** — [Dictation](/guide/control-panel/dictation) turns speech into clean text.
3. **Reason** — the [Reasoning](/guide/control-panel/reasoning) model composes Maya's reply.

Each stage is independently configurable and every setting persists per operator.
