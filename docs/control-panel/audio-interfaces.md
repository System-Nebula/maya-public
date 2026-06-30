title: Audio Interfaces
description: Select capture/playback devices and monitor live vocal input.

# Audio Interfaces

Route the operator's audio and verify the capture stream before a session.

## Settings

| Setting | Field | Default | Notes |
|---------|-------|---------|-------|
| Input device | `input_device_id` | System default | Capture source for the detection engine |
| Output device | `output_device_id` | System default | Playback for Maya's synthesized voice |
| Input gain | `input_gain` | `1.0` | Linear multiplier applied to the meter/level |
| Noise suppression | `noise_suppression` | `true` | Applied to the `getUserMedia` capture stream |

Device labels are populated via `navigator.mediaDevices.enumerateDevices()` and
only appear after the operator grants microphone permission.

## Vocal input monitor

A geometric spectrum (FFT bars) visualizes the live capture stream. With no
microphone available, **Simulate input** drives the meter from a synthetic
source so the detection engine can still be exercised.

!!! warning "Permissions"
    Browsers only expose device labels after `getUserMedia` is granted once.
    Until then, devices show as "Microphone 1", "Speaker 1", etc.

## Reading current defaults

=== "curl"
    ```bash
    curl -s http://localhost:8090/api/voice/settings/defaults | jq .default_settings
    ```

=== "Python"
    ```python
    import httpx

    r = httpx.get("http://localhost:8090/api/voice/settings/defaults")
    print(r.json()["default_settings"]["noise_suppression"])
    ```

=== "JavaScript"
    ```javascript
    const r = await fetch("/api/voice/settings/defaults");
    const { default_settings } = await r.json();
    console.log(default_settings.input_gain);
    ```
