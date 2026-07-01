// resample-worklet.js — AudioWorkletProcessor: float32 mic frames → int16 PCM ArrayBuffers.
//
// Pass-1 stub: the AudioContext is already opened at the target sample rate, so this just
// converts float32 [-1,1] to little-endian int16 and posts it. A real worklet would also
// resample if the device rate differs and apply a VAD pre-gate.

class Pcm16Resampler extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch = input[0];
    const pcm = new Int16Array(ch.length);
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    this.port.postMessage(pcm.buffer, [pcm.buffer]);
    return true;
  }
}

registerProcessor("pcm16-resampler", Pcm16Resampler);
