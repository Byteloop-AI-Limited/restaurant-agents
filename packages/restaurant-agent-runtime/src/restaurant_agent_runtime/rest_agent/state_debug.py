"""Pure formatting helpers for Restaurant Agent debug state."""

from typing import Any


def get_state_values(
    state: dict[str, Any],
    *,
    exclude_key: str = "messages",
) -> dict[str, Any]:
    """Return state values without the potentially large message history."""

    return {key: value for key, value in state.items() if key != exclude_key}


def shorten_state_messages(messages: list[Any]) -> list[dict[str, dict[str, Any]]]:
    """Serialize the useful fields from messages in reverse chronological order."""

    message_fields = ["content", "additional_kwargs"]
    shortened = [
        {
            type(message).__name__: message.model_dump(
                include=message_fields,
            )
        }
        for message in messages
    ]
    shortened.reverse()
    return shortened

