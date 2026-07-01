title: Dictation (Wispr)
description: Transcription model and text-cleanup defaults applied to detected speech.

# Dictation (Wispr)

**Pipeline transcription.** Wispr-Flow-style defaults govern which model
transcribes detected speech and how the raw transcript is cleaned before it
reaches the reasoning model.

## Settings

| Setting | Field | Default | Notes |
|---------|-------|---------|-------|
| Dictation model | `wispr_model` | `wispr-flow-1` | `wispr-flow-1`, `wispr-flow-1-fast`, `wispr-flow-pro` |
| Language | `language` | `en` | `en`, `es`, `fr`, `de`, `ja`, `pt` |
| Auto-punctuation | `auto_punctuation` | `true` | Capitalizes and terminates sentences |
| Filler removal | `filler_removal` | `true` | Strips `um`, `uh`, `like`, … |

## Cleanup behavior

With `auto_punctuation` and `filler_removal` enabled, the raw transcript is
normalized before reasoning:

| Raw transcript | Cleaned |
|----------------|---------|
| `um hey   uh maya` | `Hey maya.` |
| `what is the plan` | `What is the plan?` |

Question detection keys off the leading word (`what`, `how`, `is`, `can`, …),
so `What's the plan` is punctuated as a question.

!!! tip "Disable for verbatim capture"
    Turn off both toggles when you need the exact spoken text (e.g. quoting a
    command verbatim). Cleanup is non-destructive to meaning but rewrites
    casing and punctuation.
