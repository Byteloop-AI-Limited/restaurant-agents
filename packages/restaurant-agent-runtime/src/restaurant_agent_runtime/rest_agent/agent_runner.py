"""
Graph execution and state management for the agent system
  . Executes LangGraph delivery graph with PostgreSQL checkpointer
  . Manages conversation state and message history
  . Provides custom message injection for testing and admin operations
  . Handles user name capture and system message updates
  . Repairs persisted tool-call mismatch state (OpenAI 400) by trimming malformed assistant/tool tails and retrying
  . Terminates broken sessions by marking threads inactive when tool-call mismatch cannot be repaired
  . Supports state debugging and inspection, including value-only helpers
  Functions/Classes:
    . _find_malformed_tool_call_tail
    . _repair_malformed_tool_call_tail
    . _terminate_session_on_tool_call_error
    . run_rest_graph_with_custom_msg
    . debug_state_by_thread
    . debug_state
    . debug_state_values
    . RestaurantGraphAdapter
"""

# %%

from collections.abc import Mapping, Sequence
from typing import Any, Optional

import openai
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.runtime import RestaurantRuntime
from restaurant_agent_runtime.rest_agent.agents.agent_harness import ContextSchema
from restaurant_agent_runtime.rest_agent.agents.delivery import build_delivery_agent
from restaurant_agent_runtime.rest_agent.agents.multi_agent import build_multi_agent_graph
from restaurant_agent_runtime.rest_agent.agents.takeaway import build_takeaway_agent
from restaurant_agent_runtime.rest_agent.agents.triage import build_triage_agent
from restaurant_agent_runtime.rest_agent.prompts import RestaurantPrompts
from restaurant_agent_runtime.rest_agent.state_debug import (
    get_state_values,
    shorten_state_messages,
)
from restaurant_agent_runtime.services.ordelo_service.ordelo_service import OrdeloService
from restaurant_agent_runtime.services.thread_management import ThreadHandler
from restaurant_agent_runtime.services.thread_management.graph_config import (
    get_config_for_recipient,
)
from restaurant_agent_runtime.watomation import activity

STANDARD_AGENT_NAMES = frozenset(
    {"triage_agent", "delivery_agent", "takeaway_agent"}
)


def _current_restaurant_master(runtime: RestaurantRuntime):
    """Load the mutable operational record only for a real graph invocation."""
    return runtime.operational_lookups.get_restaurant_master()


def _build_graph(
    runtime: RestaurantRuntime,
    prompts: RestaurantPrompts,
    extra_tools_by_agent: Mapping[str, Sequence[Any]],
    agent_overrides: Mapping[str, Any],
):
    model = runtime.settings.llm.llm_client_single_tool_turn
    triage_agent = agent_overrides.get("triage_agent")
    if triage_agent is None:
        triage_agent = build_triage_agent(
            model=model,
            system_prompt=prompts.triage,
            extra_tools=extra_tools_by_agent.get("triage_agent", ()),
        )

    delivery_agent = agent_overrides.get("delivery_agent")
    if delivery_agent is None:
        delivery_agent = build_delivery_agent(
            model=model,
            system_prompt=prompts.delivery,
            extra_tools=extra_tools_by_agent.get("delivery_agent", ()),
        )

    takeaway_agent = agent_overrides.get("takeaway_agent")
    if takeaway_agent is None:
        takeaway_agent = build_takeaway_agent(
            model=model,
            system_prompt=prompts.takeaway,
            extra_tools=extra_tools_by_agent.get("takeaway_agent", ()),
        )

    async def call_triage_agent(state):
        return await triage_agent.ainvoke(state)

    async def call_delivery_agent(state):
        return await delivery_agent.ainvoke(state)

    async def call_takeaway_agent(state):
        return await takeaway_agent.ainvoke(state)

    return build_multi_agent_graph(
        triage_agent_node=call_triage_agent,
        delivery_agent_node=call_delivery_agent,
        takeaway_agent_node=call_takeaway_agent,
    )


def _find_malformed_tool_call_tail(
    messages: list[BaseMessage],
) -> tuple[int, list[str]] | None:
    """Return the first malformed assistant tool-call turn in the persisted tail.

    A valid assistant tool-call message must be followed immediately by ToolMessage
    responses for every tool_call_id before any other message type appears.
    """
    for idx, msg in enumerate(messages):
        if not isinstance(msg, AIMessage):
            continue

        tool_calls = getattr(msg, "tool_calls", None) or []
        expected_tool_call_ids = [
            call.get("id")
            for call in tool_calls
            if isinstance(call, dict) and call.get("id")
        ]
        if not expected_tool_call_ids:
            continue

        pending_tool_call_ids = set(expected_tool_call_ids)
        cursor = idx + 1
        while cursor < len(messages) and isinstance(messages[cursor], ToolMessage):
            tool_call_id = getattr(messages[cursor], "tool_call_id", None)
            pending_tool_call_ids.discard(tool_call_id)
            cursor += 1
            if not pending_tool_call_ids:
                break

        if pending_tool_call_ids:
            return idx, sorted(pending_tool_call_ids)

    return None


async def _repair_malformed_tool_call_tail(graph, config: dict) -> bool:
    state = await graph.aget_state(config=config)
    messages = (state.values or {}).get("messages") or []
    if not messages:
        return False

    malformed_tail = _find_malformed_tool_call_tail(messages)
    if malformed_tail is None:
        return False

    logger.critical("Repairing malformed tool-call tail before model invoke")
    malformed_idx, missing_tool_call_ids = malformed_tail
    messages_to_remove = [
        RemoveMessage(id=msg.id)
        for msg in messages[malformed_idx:]
        if getattr(msg, "id", None)
    ]
    if not messages_to_remove:
        return False

    logger.warning(
        "Repairing malformed tool-call tail before model invoke",
        malformed_index=malformed_idx,
        removed_count=len(messages_to_remove),
        missing_tool_call_ids=missing_tool_call_ids,
    )
    await graph.aupdate_state(
        config=config,
        values={"messages": messages_to_remove},
        as_node="toolNode",
    )
    return True


async def _terminate_session_on_tool_call_error(
    context_schema: ContextSchema, recipient: str
) -> None:
    try:
        if context_schema.thread_handler is None:
            context_schema.thread_handler = ThreadHandler(
                context_schema.pool, agent=context_schema.rest_ref
            )
        await context_schema.thread_handler.make_threads_inactive(recipient=recipient)
    except Exception:
        logger.exception(
            "Failed to terminate session on tool-call mismatch error",
            recipient=recipient,
        )


@activity.tracked(activity.AGENT_RUNS, label_arg="recipient")
async def run_rest_graph_with_custom_msg(
    recipient: str,
    wa_name: str | None = None,
    pool: AsyncConnectionPool | None = None,
    human_msg: str = None,
    ai_msg: str = None,
    system_msg: str = None,
    msgs: list[BaseMessage] = None,
    state_update_dict: dict = None,
    config: dict = None,
    persist_only: bool = False,
    *,
    runtime: RestaurantRuntime,
    graph_builder,
):
    """Executes the delivery graph and returns the AI's response."""

    # Setup RunContext
    if pool is None:
        pool = await runtime.settings.database.get_pool()
    checkpointer: AsyncPostgresSaver = AsyncPostgresSaver(pool)

    graph = graph_builder.compile(checkpointer=checkpointer)

    # Use the prepared config if available
    is_new_thread = False
    if config is None:
        config, is_new_thread = await get_config_for_recipient(
            recipient, pool, agent=runtime.identity.rest_ref
        )

    if is_new_thread and wa_name:
        (
            customer_master,
            ask_for_consent,
        ) = await OrdeloService(
            rest_ref=runtime.identity.rest_ref,
            database_client=runtime.settings.database_client,
            operational_lookups=runtime.operational_lookups,
        ).get_or_create_customer_master(recipient, wa_name)

        if customer_master.postcode is None:
            customer_address = None
        else:
            customer_address = customer_master.model_dump()

        await graph.aupdate_state(
            config=config,
            values={
                "wa_name": wa_name,
                "rest_ref": runtime.identity.rest_ref.lower(),
                "active_agent": "triage_agent",
                "customer_address": customer_address,
                "ask_for_consent": ask_for_consent,
                "messages": [
                    SystemMessage(
                        f"user name is {wa_name}. Address the user at key points in the conversation. Call tool `send_welcome_message`"
                    )
                ],
            },
        )

    # which ever msg is not None, for a list of msgs.
    if msgs is None:
        msgs = []
    if system_msg:
        msgs.append(SystemMessage(system_msg))
    if ai_msg:
        msgs.append(AIMessage(ai_msg))
    if human_msg:
        msgs.append(HumanMessage(human_msg))

    ip_msgs = {"messages": msgs}

    if persist_only:
        # Callback-originated deterministic actions need an auditable state
        # transition but must not ask the model to make a second availability
        # decision. Repair first so the persisted selection is not removed as
        # part of a malformed historic tool-call tail.
        await _repair_malformed_tool_call_tail(graph=graph, config=config)
        persisted_update = dict(state_update_dict or {})
        if msgs:
            persisted_update["messages"] = [
                *(persisted_update.get("messages") or []),
                *msgs,
            ]
        if persisted_update:
            await graph.aupdate_state(config, persisted_update)
        return None

    # Update state if updates provided
    if state_update_dict:
        # await graph.aupdate_state(config, state_update_dict, as_node="toolNode")
        await graph.aupdate_state(config, state_update_dict)

    await _repair_malformed_tool_call_tail(graph=graph, config=config)

    # Create run Configuration
    context_schema = ContextSchema(
        pool=pool,
        wa_client=runtime.async_wa_client,
        recipient=recipient,
        rest_ref=runtime.identity.rest_ref,
        restaurant_name=runtime.presentation.display_name,
        restaurant_logo_url=runtime.presentation.logo_url or "",
        restaurant_contact_phone=runtime.presentation.contact_phone,
        delivery_button_label=runtime.presentation.delivery_button_label,
        takeaway_button_label=runtime.presentation.takeaway_button_label,
        enquiry_menu=runtime.presentation.enquiry_menu,
        restaurant_master=_current_restaurant_master(runtime),
        project_settings=runtime.settings.project,
        payment_settings=runtime.settings.payment,
        client_ordelo=runtime.settings.database_client,
        operational_lookups=runtime.operational_lookups,
    )

    try:
        ai_msg = await graph.ainvoke(
            input=ip_msgs, config=config, context=context_schema
        )
    except openai.BadRequestError as e:
        err_txt = str(e)
        if (
            "must be followed by tool messages responding to each 'tool_call_id'"
            not in err_txt
        ):
            raise

        repaired = await _repair_malformed_tool_call_tail(graph=graph, config=config)
        if not repaired:
            await _terminate_session_on_tool_call_error(
                context_schema=context_schema, recipient=recipient
            )
            raise

        try:
            ai_msg = await graph.ainvoke(
                input=ip_msgs, config=config, context=context_schema
            )
        except openai.BadRequestError:
            await _terminate_session_on_tool_call_error(
                context_schema=context_schema, recipient=recipient
            )
            raise
    ai_msg_content = ai_msg["messages"][-1].content

    return ai_msg_content


# %% Debug State By Thread
async def debug_state_by_thread(
    thread_id: str,
    full_state: bool = False,
    *,
    runtime: RestaurantRuntime,
    graph_builder,
) -> dict:
    """Debug state by thread_id - fetches recipient from thread table."""
    result = (
        runtime.settings.database_client.table("thread")
        .select("thread_id", "recipient")
        .eq("thread_id", thread_id)
        .execute()
    )

    if not result.data:
        raise ValueError(f"Thread not found: {thread_id}")
    recipient = result.data[0]["recipient"]
    config = {"configurable": {"thread_id": thread_id, "recipient": recipient}}
    # Get graph and then state
    pool = await runtime.settings.database.get_pool()
    checkpointer = AsyncPostgresSaver(pool)
    graph = graph_builder.compile(checkpointer=checkpointer)
    state = await graph.aget_state(config=config)

    if full_state:
        debug_stack = state.values
    else:
        debug_stack = {
            **get_state_values(state.values),
            "messages": shorten_state_messages(state.values["messages"]),
        }
    return debug_stack


# %% Debug State
async def debug_state(
    recipient: str,
    full_state: bool = False,
    *,
    runtime: RestaurantRuntime,
    graph_builder,
) -> dict:
    pool = await runtime.settings.database.get_pool()
    checkpointer = AsyncPostgresSaver(pool)
    graph = graph_builder.compile(checkpointer=checkpointer)

    config, _ = await get_config_for_recipient(
        recipient, pool, agent=runtime.identity.rest_ref
    )

    state = await graph.aget_state(config=config)

    if full_state:
        return {
            **get_state_values(state.values),
            "messages": shorten_state_messages(state.values["messages"]),
        }
    return get_state_values(state.values)


# %% Debug State
async def debug_state_values(
    recipient: Optional[str] = None,
    config: Optional[dict] = None,
    *,
    runtime: RestaurantRuntime,
    graph_builder,
) -> dict:
    pool = await runtime.settings.database.get_pool()
    checkpointer = AsyncPostgresSaver(pool)
    graph = graph_builder.compile(checkpointer=checkpointer)

    if config is None:
        config, _ = await get_config_for_recipient(
            recipient, pool, agent=runtime.identity.rest_ref
        )
    state = await graph.aget_state(config=config)

    state_values = get_state_values(state.values)
    return state_values


class RestaurantGraphAdapter:
    """Bind every graph call to the exact Restaurant runtime and WhatsApp client."""

    def __init__(
        self,
        runtime: RestaurantRuntime,
        *,
        prompts: RestaurantPrompts,
        extra_tools_by_agent: Mapping[str, Sequence[Any]] | None = None,
        agent_overrides: Mapping[str, Any] | None = None,
    ):
        self.runtime = runtime
        extra_tools_by_agent = dict(extra_tools_by_agent or {})
        agent_overrides = dict(agent_overrides or {})

        unknown_names = (
            set(extra_tools_by_agent) | set(agent_overrides)
        ) - STANDARD_AGENT_NAMES
        if unknown_names:
            names = ", ".join(sorted(unknown_names))
            raise ValueError(f"unknown standard agent names: {names}")

        overlapping_names = set(extra_tools_by_agent) & set(agent_overrides)
        if overlapping_names:
            names = ", ".join(sorted(overlapping_names))
            raise ValueError(f"cannot add tools to replaced agents: {names}")

        for name, agent in agent_overrides.items():
            if not callable(getattr(agent, "ainvoke", None)):
                raise ValueError(f"agent override must define ainvoke: {name}")

        self.graph_builder = _build_graph(
            runtime,
            prompts,
            extra_tools_by_agent,
            agent_overrides,
        )

    async def run_rest_graph_with_custom_msg(self, recipient: str, **kwargs):
        return await run_rest_graph_with_custom_msg(
            recipient=recipient,
            runtime=self.runtime,
            graph_builder=self.graph_builder,
            **kwargs,
        )

    async def debug_state(self, recipient: str, full_state: bool = False) -> dict:
        return await debug_state(
            recipient,
            full_state=full_state,
            runtime=self.runtime,
            graph_builder=self.graph_builder,
        )

    async def debug_state_values(
        self, recipient: str | None = None, config: dict | None = None
    ) -> dict:
        return await debug_state_values(
            recipient,
            config=config,
            runtime=self.runtime,
            graph_builder=self.graph_builder,
        )

    async def debug_state_by_thread(
        self, thread_id: str, full_state: bool = False
    ) -> dict:
        return await debug_state_by_thread(
            thread_id,
            full_state=full_state,
            runtime=self.runtime,
            graph_builder=self.graph_builder,
        )
