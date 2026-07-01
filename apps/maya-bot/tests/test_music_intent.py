import pytest

from maya_bot.music.intent import GuildEngagement, detect


@pytest.mark.parametrize(
    "text,engaged,expect_triggered",
    [
        ("hey maya play despacito", False, True),
        ("maya, put on some lofi", False, True),
        ("play despacito", False, False),  # no wake word, not engaged
        ("play despacito", True, True),  # engaged -> bare play triggers
        ("I think someone should play despacito", False, False),
        ("I wish somebody would play some music", False, False),
        ("just chatting about nothing in particular", False, False),
    ],
)
def test_detect_trigger_cases(text, engaged, expect_triggered):
    result = detect(text, engaged=engaged)
    assert result.triggered is expect_triggered


def test_detect_extracts_query_on_trigger():
    result = detect("hey maya play despacito", engaged=False)
    assert result.triggered
    assert result.query == "despacito"


def test_guild_engagement_expires():
    engagement = GuildEngagement()
    guild_id = 123
    assert not engagement.is_engaged(guild_id)
    engagement.mark_engaged(guild_id)
    assert engagement.is_engaged(guild_id)
