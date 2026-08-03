from restaurant_agent_runtime.watomation.overwatch import (
    OVERWATCH_RECIPIENTS,
    is_overwatch_recipient,
)


def test_overwatch_recipient_is_normalized_and_bounded():
    recipient = next(iter(OVERWATCH_RECIPIENTS))
    assert is_overwatch_recipient(recipient)
    assert is_overwatch_recipient(f"+{recipient}")
    assert not is_overwatch_recipient("447000000000")
    assert not is_overwatch_recipient(None)
