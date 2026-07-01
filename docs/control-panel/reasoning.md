title: Reasoning
description: The model that turns a cleaned transcript into Maya's conversational turn.

# Reasoning

**Pipeline step 2.** The reasoning model transforms the cleaned transcript into
Maya's conversational turn, tagged with a parsed intent.

## Settings

| Setting | Field | Default | Notes |
|---------|-------|---------|-------|
| Reasoning model | `reasoning_model` | `maya-reason-mini` | `maya-reason-mini`, `maya-reason`, `maya-reason-pro` |
| Persona | `persona` | `maya` | Voice/tone the reply is composed in |

## Endpoint

`POST /api/voice/turn` runs cleanup → intent parse → reply, returning a
step-by-step trace.

=== "curl"
    ```bash
    curl -s -X POST http://localhost:8090/api/voice/turn \
      -H 'Content-Type: application/json' \
      -d '{"transcript": "hey maya, what is on the schedule?"}' | jq
    ```

=== "Python"
    ```python
    import httpx

    payload = {"transcript": "play the new album"}
    r = httpx.post("http://localhost:8090/api/voice/turn", json=payload)
    turn = r.json()
    print(turn["intent"], "→", turn["maya_turn"])
    ```

=== "JavaScript"
    ```javascript
    const r = await fetch("/api/voice/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript: "play the new album" }),
    });
    const turn = await r.json();
    console.log(turn.intent, turn.maya_turn);
    ```

## Parsed intents

| Intent | Trigger |
|--------|---------|
| `greeting` | leads with hi/hey/hello/… |
| `question` | ends with `?` or leads with what/why/how/… |
| `command` | leads with an action verb (play, stop, open, …) |
| `farewell` | leads with bye/goodbye/later/… |
| `statement` | anything else |

!!! note "Deterministic by default"
    The shipped responder is deterministic so the pipeline runs with no API
    keys. A real OpenAI-compatible model swaps in at the `_reason()` seam in
    `services/voice_turn.py` without changing the request/response contract.
