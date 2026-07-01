"""Reply when Maya is @-mentioned in a text channel.

Every hop through the mention -> voice-join -> LLM -> reply pipeline is logged
as an explicit stage (see ``_stage``) so a "nothing happened" report can be
diagnosed from log/span output alone: whichever stage name appears last is
where it broke (e.g. if MESSAGE_CREATE never logs, the gateway/intents never
delivered the event; if it stops at MENTION_DETECTED with mentioned=False,
Discord didn't report the mention — often the privileged Message Content
intent toggle in the Developer Portal, not a code bug).
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import discord
import structlog
from discord.ext import commands
from opentelemetry import trace

from maya_llm.client import LlmError, stream_chat
from maya_tools import make_stage_logger

try:
    from observability import current_trace_id, emit_visibility
except ImportError:

    def current_trace_id() -> str | None:
        return None

    def emit_visibility(*_args, **_kwargs) -> None:
        return None


if TYPE_CHECKING:
    from maya_bot.main import MayaBot

logger = structlog.get_logger()
_tracer = trace.get_tracer("maya.discord.chat")

_SYSTEM_PROMPT = (
    "You are Maya, a helpful voice/text assistant living in a Discord server. "
    "Keep replies short and conversational (a few sentences at most)."
)
_FALLBACK_PROMPT = "Say a brief, friendly hello."
_FALLBACK_REPLY = "Maya's brain is offline right now — try again in a bit."
_MAX_REPLY_CHARS = 1900  # stay under Discord's 2000-char message limit


_stage = make_stage_logger("chat.mention")


class ChatCog(commands.Cog):
    def __init__(self, bot: "MayaBot") -> None:
        self.bot = bot
        self._tasks: set[asyncio.Task] = set()

    def _track_task(self, task: asyncio.Task) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _extract_prompt(self, message: discord.Message) -> str:
        content = message.content
        for mention in message.mentions:
            content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        return content.strip()

    async def _join_authors_voice_channel(self, message: discord.Message, span) -> str | None:
        """If the tagging user is in a voice channel, join it (or move there).

        Returns a short status string to fold into the reply, or None if there
        was nothing to join (author not in voice) — silently skipped rather
        than treated as an error, since most mentions are just chat.
        """
        author_voice = getattr(message.author, "voice", None)
        found_channel = author_voice is not None and author_voice.channel is not None
        _stage(
            "VOICE_STATE_LOOKUP",
            span,
            found_channel=found_channel,
            channel_id=getattr(author_voice.channel, "id", None) if found_channel else None,
        )
        if not found_channel:
            return None
        channel = author_voice.channel
        voice_client = message.guild.voice_client if message.guild else None
        try:
            if voice_client is not None and voice_client.is_connected():
                if voice_client.channel.id == channel.id:
                    _stage("VOICE_CONNECT", span, result="already_connected", channel_id=channel.id)
                    return None  # already there
                await voice_client.move_to(channel)
            else:
                await channel.connect()
            span.set_attribute("discord.voice_channel_id", str(channel.id))
            _stage("VOICE_CONNECT", span, result="connected", channel_id=channel.id)
            emit_visibility(
                "chat.mention.voice_join",
                span=span,
                boundary="discord",
                channel_id=str(channel.id),
            )
            return f"Joined **{channel.name}**."
        except Exception as exc:
            span.record_exception(exc)
            _stage("VOICE_CONNECT", span, result="failed", channel_id=channel.id, error=str(exc))
            logger.warning("chat_mention_voice_join_failed", error=str(exc), channel_id=channel.id)
            return None

    async def _reply_to_mention(self, message: discord.Message) -> None:
        with _tracer.start_as_current_span("discord.chat.mention") as span:
            span.set_attribute("discord.user_id", str(message.author.id))
            if message.guild is not None:
                span.set_attribute("discord.guild_id", str(message.guild.id))
            join_status = await self._join_authors_voice_channel(message, span)
            prompt = self._extract_prompt(message) or _FALLBACK_PROMPT
            span.set_attribute("chat.prompt_length", len(prompt))
            _stage("LLM_REQUEST", span, prompt_length=len(prompt))
            started = time.monotonic()
            try:
                async with message.channel.typing():
                    chunks: list[str] = []
                    async for token in stream_chat(prompt, system=_SYSTEM_PROMPT):
                        chunks.append(token)
                    reply = "".join(chunks).strip() or _FALLBACK_REPLY
                _stage(
                    "LLM_RESPONSE",
                    span,
                    token_count=len(chunks),
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
                if join_status:
                    reply = f"{join_status} {reply}"
                emit_visibility(
                    "chat.mention.reply",
                    span=span,
                    boundary="discord",
                    reply_length=len(reply),
                )
                await message.reply(reply[:_MAX_REPLY_CHARS])
                _stage("DISCORD_REPLY", span, result="sent", reply_length=len(reply))
            except LlmError as exc:
                span.record_exception(exc)
                _stage("LLM_RESPONSE", span, result="failed", error=str(exc))
                logger.warning("chat_mention_llm_failed", error=str(exc))
                await message.reply(join_status or _FALLBACK_REPLY)
                _stage("DISCORD_REPLY", span, result="sent_fallback")
            except Exception as exc:
                span.record_exception(exc)
                trace_id = current_trace_id()
                logger.error("chat_mention_failed", error=str(exc), trace_id=trace_id)
                await message.reply(join_status or _FALLBACK_REPLY)
                _stage("DISCORD_REPLY", span, result="sent_fallback", error=str(exc))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        _stage(
            "MESSAGE_CREATE",
            message_id=message.id,
            author_id=message.author.id,
            guild_id=message.guild.id if message.guild else None,
            author_bot=message.author.bot,
        )
        if message.author.bot:
            return
        mentioned = self.bot.user is not None and self.bot.user in message.mentions
        _stage("MENTION_DETECTED", mentioned=mentioned, mentions_count=len(message.mentions))
        if not mentioned:
            return
        task = asyncio.create_task(self._reply_to_mention(message))
        self._track_task(task)


async def setup(bot: "MayaBot") -> None:
    await bot.add_cog(ChatCog(bot))
