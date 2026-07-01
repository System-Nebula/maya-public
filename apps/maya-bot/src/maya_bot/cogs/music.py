"""Discord `/play` commands — mpv+yt-dlp voice playback with Wikidata-assisted
resolution, plus optional passive wake-word listening.

Every hop through the interaction -> voice-join -> resolve -> mpv-load ->
reply pipeline is logged as an explicit stage via ``maya_tools.make_stage_logger``
(the same convention as cogs/chat.py's mention handler — see that file's
docstring for how to read a "which stage did it reach" report)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
import structlog
from discord import app_commands
from discord.ext import commands
from opentelemetry import trace

from maya_bot.music.audio_source import MpvPCMAudioSource
from maya_bot.music.mpv_session import MpvSessionRegistry, MpvUnavailableError
from maya_bot.music.resolver import resolve_query_async
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
_tracer = trace.get_tracer("maya.discord.music")
_stage = make_stage_logger("music.play")


class MusicCog(commands.Cog):
    def __init__(self, bot: "MayaBot") -> None:
        self.bot = bot
        self._mpv = MpvSessionRegistry()
        self._listeners: dict[int, object] = {}
        self._tasks: set[asyncio.Task] = set()

    def _track_task(self, task: asyncio.Task) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _connect_voice(
        self, interaction: discord.Interaction, span=None
    ) -> discord.VoiceClient | None:
        user_voice = getattr(interaction.user, "voice", None)
        found_channel = user_voice is not None and user_voice.channel is not None
        _stage(
            "VOICE_STATE_LOOKUP",
            span,
            found_channel=found_channel,
            channel_id=getattr(user_voice.channel, "id", None) if found_channel else None,
        )
        if not found_channel:
            _stage("VOICE_CONNECT", span, result="no_voice_channel")
            await interaction.followup.send(
                "Join a voice channel first, then run `/play` again.", ephemeral=True
            )
            return None
        channel = user_voice.channel
        voice_client = interaction.guild.voice_client if interaction.guild else None
        try:
            if voice_client is not None and voice_client.is_connected():
                if voice_client.channel.id != channel.id:
                    await voice_client.move_to(channel)
                _stage("VOICE_CONNECT", span, result="already_connected", channel_id=channel.id)
                return voice_client
            voice_client = await channel.connect()
            _stage("VOICE_CONNECT", span, result="connected", channel_id=channel.id)
            return voice_client
        except Exception as exc:
            _stage("VOICE_CONNECT", span, result="failed", channel_id=channel.id, error=str(exc))
            raise

    async def _play_query(self, interaction: discord.Interaction, query: str) -> None:
        guild_id = interaction.guild_id
        with _tracer.start_as_current_span("discord.music.play") as span:
            span.set_attribute("discord.guild_id", str(guild_id))
            span.set_attribute("discord.user_id", str(interaction.user.id))
            span.set_attribute("music.query", query)
            _stage(
                "INTERACTION_RECEIVED",
                span,
                guild_id=guild_id,
                user_id=interaction.user.id,
                query=query,
            )
            try:
                voice_client = await self._connect_voice(interaction, span)
                if voice_client is None:
                    return

                _stage("RESOLVE_START", span, query=query)
                try:
                    source = await resolve_query_async(query)
                except Exception as exc:
                    span.record_exception(exc)
                    _stage("RESOLVE_FAILED", span, error=str(exc))
                    logger.warning("music_resolve_failed", query=query, error=str(exc))
                    await interaction.followup.send(
                        f"Couldn't find anything playable for `{query}`.", ephemeral=True
                    )
                    return
                _stage("RESOLVE_DONE", span, matched_via=source.matched_via)

                span.set_attribute("music.matched_via", source.matched_via)
                if source.wikidata_qid:
                    span.set_attribute("music.wikidata_qid", source.wikidata_qid)

                session = self._mpv.get_or_create(guild_id)
                try:
                    await session.load(source.stream_url)
                    _stage("MPV_LOAD", span, result="loaded")
                except MpvUnavailableError as exc:
                    span.record_exception(exc)
                    _stage("MPV_LOAD", span, result="mpv_unavailable", error=str(exc))
                    await interaction.followup.send(
                        "`mpv` is not installed on the bot host — playback is unavailable.",
                        ephemeral=True,
                    )
                    return

                if voice_client.is_playing():
                    voice_client.stop()
                voice_client.play(MpvPCMAudioSource(session))

                emit_visibility(
                    "music.play.start",
                    span=span,
                    boundary="discord",
                    matched_via=source.matched_via,
                    query=query,
                )

                embed = discord.Embed(
                    title=source.title or query,
                    color=discord.Color.green(),
                )
                embed.add_field(name="Matched via", value=source.matched_via, inline=True)
                if source.wikidata_qid:
                    embed.add_field(
                        name="Wikidata",
                        value=f"[{source.wikidata_qid}](https://www.wikidata.org/wiki/{source.wikidata_qid})",
                        inline=True,
                    )
                if source.webpage_url:
                    embed.url = source.webpage_url
                await interaction.followup.send(embed=embed)
                _stage("DISCORD_REPLY", span, result="sent")
            except Exception as exc:
                span.record_exception(exc)
                trace_id = current_trace_id()
                _stage("DISCORD_REPLY", span, result="sent_fallback", error=str(exc))
                logger.error("music_play_failed", query=query, error=str(exc), trace_id=trace_id)
                await interaction.followup.send(
                    f"Playback failed: {exc}" if str(exc) else "Playback failed.",
                    ephemeral=True,
                )

    @app_commands.command(name="play", description="Play a song or YouTube/SoundCloud link in your voice channel")
    @app_commands.describe(query="Song name, artist - title, or a YouTube/SoundCloud link")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()
        task = asyncio.create_task(self._play_query(interaction, query))
        self._track_task(task)

    @app_commands.command(name="stop", description="Stop playback")
    async def stop(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        session = self._mpv.get(guild_id) if guild_id is not None else None
        if session is not None:
            await session.stop()
        voice_client = interaction.guild.voice_client if interaction.guild else None
        if voice_client is not None and voice_client.is_playing():
            voice_client.stop()
        await interaction.followup.send("Stopped.", ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.id != getattr(self.bot.user, "id", None):
            return
        # Bot left a voice channel (kicked, disconnected, or moved to None) — tear down mpv.
        if before.channel is not None and after.channel is None:
            guild_id = before.channel.guild.id
            await self._mpv.shutdown(guild_id)


async def setup(bot: "MayaBot") -> None:
    await bot.add_cog(MusicCog(bot))
