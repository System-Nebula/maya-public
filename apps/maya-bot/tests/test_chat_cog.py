from unittest.mock import AsyncMock, MagicMock

import pytest

from maya_bot.cogs.chat import ChatCog


def _make_message(*, content: str, is_bot: bool, mentions_bot: bool, bot_user, voice_channel=None):
    message = MagicMock()
    message.content = content
    message.author.bot = is_bot
    message.author.voice = None
    if voice_channel is not None:
        message.author.voice = MagicMock(channel=voice_channel)
    message.mentions = [bot_user] if mentions_bot else []
    message.channel.typing = MagicMock()
    message.channel.typing.return_value.__aenter__ = AsyncMock()
    message.channel.typing.return_value.__aexit__ = AsyncMock(return_value=False)
    message.reply = AsyncMock()
    message.guild = None
    return message


@pytest.fixture
def bot():
    bot = MagicMock()
    bot.user = MagicMock(id=999, mention="<@999>")
    return bot


@pytest.mark.asyncio
async def test_on_message_ignores_bot_authors(bot):
    cog = ChatCog(bot)
    message = _make_message(content="hi", is_bot=True, mentions_bot=True, bot_user=bot.user)
    await cog.on_message(message)
    assert not cog._tasks


@pytest.mark.asyncio
async def test_on_message_ignores_non_mentions(bot):
    cog = ChatCog(bot)
    message = _make_message(
        content="talking about @Maya but not tagging", is_bot=False, mentions_bot=False, bot_user=bot.user
    )
    await cog.on_message(message)
    assert not cog._tasks


@pytest.mark.asyncio
async def test_on_message_replies_when_mentioned(bot, monkeypatch):
    async def fake_stream_chat(prompt, *, system=None, config=None, stop=None):
        assert prompt == "hello"
        for chunk in ("Hi", " there!"):
            yield chunk

    monkeypatch.setattr("maya_bot.cogs.chat.stream_chat", fake_stream_chat)

    cog = ChatCog(bot)
    message = _make_message(content="<@999> hello", is_bot=False, mentions_bot=True, bot_user=bot.user)
    await cog.on_message(message)
    assert len(cog._tasks) == 1
    task = next(iter(cog._tasks))
    await task
    message.reply.assert_awaited_once_with("Hi there!")


def test_extract_prompt_strips_mention_forms(bot):
    cog = ChatCog(bot)
    message = _make_message(content="<@!999> what's up", is_bot=False, mentions_bot=True, bot_user=bot.user)
    assert cog._extract_prompt(message) == "what's up"


@pytest.mark.asyncio
async def test_mention_joins_authors_voice_channel(bot, monkeypatch):
    async def fake_stream_chat(prompt, *, system=None, config=None, stop=None):
        yield "hi"

    monkeypatch.setattr("maya_bot.cogs.chat.stream_chat", fake_stream_chat)

    voice_channel = MagicMock(id=555)
    voice_channel.name = "general"
    voice_channel.connect = AsyncMock()

    cog = ChatCog(bot)
    message = _make_message(
        content="<@999>", is_bot=False, mentions_bot=True, bot_user=bot.user, voice_channel=voice_channel
    )
    message.guild = MagicMock(voice_client=None)

    await cog.on_message(message)
    task = next(iter(cog._tasks))
    await task

    voice_channel.connect.assert_awaited_once()
    message.reply.assert_awaited_once_with("Joined **general**. hi")


@pytest.mark.asyncio
async def test_mention_skips_join_when_author_not_in_voice(bot, monkeypatch):
    async def fake_stream_chat(prompt, *, system=None, config=None, stop=None):
        yield "hi"

    monkeypatch.setattr("maya_bot.cogs.chat.stream_chat", fake_stream_chat)

    cog = ChatCog(bot)
    message = _make_message(content="<@999>", is_bot=False, mentions_bot=True, bot_user=bot.user)
    message.guild = MagicMock(voice_client=None)

    await cog.on_message(message)
    task = next(iter(cog._tasks))
    await task

    message.reply.assert_awaited_once_with("hi")
