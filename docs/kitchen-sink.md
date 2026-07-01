title: Kitchen Sink
description: Every rendering construct supported by the docs engine — a visual test page.

# Kitchen Sink

This page exercises every construct the docs renderer supports. If something
renders wrong here, the docs theme or Markdown pipeline has regressed.

## 1. Typography

Standard paragraph text testing line height and readability. **Bold**,
*italics*, `inline code`, ~~strikethrough~~, ^^insert^^, and
[an internal link](/guide/control-panel/overview).

> Blockquote: documentation should read well in Obsidian *and* in the browser.

## 2. Headings

### Heading level 3

#### Heading level 4

## 3. Lists

- Unordered item
- Another item
    - Nested item
- Task list:
    - [x] Render admonitions
    - [x] Render polyglot tabs
    - [ ] Render Mermaid (future)

1. First
2. Second
3. Third

## 4. Admonitions (callouts)

!!! note "Supplementary information"
    A standard note callout.

!!! tip "Ergonomics"
    Use the language tabs below — your choice syncs across the whole page.

!!! warning "Deprecated"
    `wispr-flow-1` will be superseded by `wispr-flow-pro`.

!!! danger "Critical action"
    Do not lower `vad_threshold` to `0` in production.

## 5. Tables

| Setting | Default | Range |
|---------|--------:|------:|
| `vad_threshold` | 0.020 | 0.000–0.300 |
| `vad_hangover_ms` | 600 | 100–1500 |
| `input_gain` | 1.00 | 0.00–4.00 |

## 6. Polyglot code blocks

=== "Python"
    ```python
    import httpx

    def maya_turn(text: str) -> dict:
        r = httpx.post("http://localhost:8090/api/voice/turn", json={"transcript": text})
        return r.json()
    ```

=== "Go"
    ```go
    resp, _ := http.Post(
        "http://localhost:8090/api/voice/turn",
        "application/json",
        strings.NewReader(`{"transcript":"hello"}`),
    )
    ```

=== "JavaScript"
    ```javascript
    const turn = await fetch("/api/voice/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript: "hello" }),
    }).then((r) => r.json());
    ```

## 7. Single code block (copy button)

```bash
curl -s http://localhost:8090/api/voice/settings/defaults | jq
```

## 8. Inline links & footnotes

The detection engine[^vad] gates speech before transcription.

[^vad]: Voice Activity Detection — an energy gate over the capture stream.
