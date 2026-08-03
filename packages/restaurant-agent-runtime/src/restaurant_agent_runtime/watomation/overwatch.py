"""Privileged test-recipient rules for bounded restaurant-agent verification."""

OVERWATCH_RECIPIENTS = frozenset({"447448440754", "447446933210"})
"""Owner-approved test recipients that bypass operational time guards."""


def is_overwatch_recipient(recipient: str | None) -> bool:
    """Return whether a recipient may exercise flows outside time restrictions."""
    return str(recipient or "").strip().lstrip("+") in OVERWATCH_RECIPIENTS
