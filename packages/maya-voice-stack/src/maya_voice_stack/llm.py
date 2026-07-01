"""Streaming LLM client for an LM Studio (OpenAI-compatible) local server.

LM Studio exposes an OpenAI-compatible API at http://localhost:1234/v1, so we use
the official `openai` client and point base_url at it.
"""

from __future__ import annotations

from typing import Iterator

from openai import OpenAI

from maya_voice_stack.config import CONFIG, LLMConfig

# Guidance appended to the system prompt when auto-delivery is on. The agent parses
# the first "VOICE:" line out of the stream and feeds it to TTS as a per-reply
# delivery directive; the rest is the spoken reply.
AUTO_INSTRUCT_GUIDE = (
    "Delivery direction: begin every response with a single line that starts with "
    "'VOICE:' followed by a short, comma-separated description of HOW to say this "
    "particular reply - emotion, pace, volume, and any vocal cues that fit the "
    "content (e.g. whispering, laughing, sighing, excited, gentle, deadpan). Then "
    "put the spoken reply on the following line(s). Keep the VOICE line under ~12 "
    "words and never mention it in the spoken text. Example:\n"
    "VOICE: amused, warm, chuckling softly\n"
    "Ha, that's a good one - you got me there."
)


class LLMClient:
    def __init__(self, cfg: LLMConfig | None = None):
        self.cfg = cfg or CONFIG.llm
        self.client = OpenAI(base_url=self.cfg.base_url, api_key=self.cfg.api_key)

    def _messages(self, user_text: str, history: list[dict] | None) -> list[dict]:
        system = self.cfg.system_prompt
        if CONFIG.wants_style_cue():
            system = f"{system}\n\n{AUTO_INSTRUCT_GUIDE}"
        if self.cfg.disable_thinking and self.cfg.no_think_token:
            system = f"{system} {self.cfg.no_think_token}".strip()
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            # Keep only the most recent exchanges to bound latency.
            keep = self.cfg.history_turns * 2
            messages.extend(history[-keep:])
        messages.append({"role": "user", "content": user_text})
        return messages

    def stream_reply(self, user_text: str, history: list[dict] | None = None) -> Iterator[str]:
        """Yield content deltas as the model generates them."""
        kwargs: dict = dict(
            model=self.cfg.model,
            stream=True,
            temperature=self.cfg.temperature,
            top_p=self.cfg.top_p,
            max_tokens=self.cfg.max_tokens,
            messages=self._messages(user_text, history),
        )
        extra_body: dict = {}
        if self.cfg.disable_thinking:
            # Honored by LM Studio / vLLM for Qwen3-style templates; ignored otherwise.
            extra_body["chat_template_kwargs"] = {"enable_thinking": False}
        if self.cfg.reasoning_effort:
            # Honored by reasoning models like Gemma; "none" disables hidden reasoning
            # so the visible reply isn't empty. Sent raw to bypass client validation.
            extra_body["reasoning_effort"] = self.cfg.reasoning_effort
        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception:
            # Some servers reject the extra body; retry without it.
            kwargs.pop("extra_body", None)
            response = self.client.chat.completions.create(**kwargs)

        for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
