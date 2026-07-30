"""SFCS-owned prompts bound to the shared Restaurant Agent adapter."""

from functools import partial
from pathlib import Path

from restaurant_agent_runtime.rest_agent import (
    RestaurantGraphAdapter,
    RestaurantPrompts,
)


PROMPT_DIR = Path(__file__).parent / "prompts"
PROMPTS = RestaurantPrompts(
    triage=(PROMPT_DIR / "triage_agent_prompt.md").read_text(),
    delivery=(PROMPT_DIR / "delivery_multiagent_prompt.md").read_text(),
    takeaway=(PROMPT_DIR / "takeaway_agent_prompt.md").read_text(),
)
GRAPH_ADAPTER_FACTORY = partial(RestaurantGraphAdapter, prompts=PROMPTS)
