# %% [CELL 1] Core Imports
"""Triage agent for onboarding, specialist routing, and conversation termination.
  . Handles service intent classification for a single configured restaurant
  . Routes to specialist agents (delivery, takeaway) on explicit intent
  . Answers general queries (parking, complaints, contact info) directly
  . Owns terminate_conversation — the only agent that can end sessions
  . Manages marketing consent capture before termination
Functions/Classes:
  . context_aware_prompt
  . send_welcome_message
  . ask_user_to_select_service
  . capture_marketing_consent
  . terminate_conversation
"""

from typing import Annotated

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools.base import InjectedToolCallId
from langgraph.graph import END
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from pathlib import Path
from sfcs_agent.rest_agent.agents.agent_harness import (
    AgentState,
    ContextSchema,
    cleanup_before_model,
    respond_on_wa,
    transfer_to_delivery,
    transfer_to_takeaway,
)
from sfcs_agent.rest_agent.agent_wa_senders import (
    select_marketing_consent_wa_send,
    select_service_wa_send,
    send_welcome_msg_wa,
)
from restaurant_agent_core.services.lg_utils import llm_settings


# %% Load prompt from file
with (Path(__file__).parent / "prompts" / "triage_agent_prompt.md").open() as f:
    triage_agent_prompt_str = f.read()


# %% dynamic prompt
from langchain.agents.middleware import dynamic_prompt, ModelRequest


@dynamic_prompt
def context_aware_prompt(request: ModelRequest) -> str:
    return "You are a helpful assistant for the restaurant."


# %% Tool 1: send_welcome_message
@tool
async def send_welcome_message(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Sends welcome text and immediately triggers service selection buttons.

    Call this at the start of a new conversation.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    wa_name = state.get("wa_name", "there")
    rest_ref = (state.get("rest_ref") or ctx.rest_ref).lower()

    await send_welcome_msg_wa(
        recipient=recipient,
        user_name=wa_name,
        wa_client=ctx.wa_client,
        restaurant_name=ctx.restaurant_name,
    )

    await select_service_wa_send(
        recipient=recipient,
        wa_client=ctx.wa_client,
        rest_ref=rest_ref,
    )

    return Command(
        goto=END,
        update={
            "rest_ref": rest_ref,
            "active_agent": "triage_agent",
            "messages": [
                ToolMessage(
                    (
                        f"Welcome message sent to {wa_name}. "
                        "Service selection buttons sent."
                    ),
                    tool_call_id=tool_call_id,
                ),
                AIMessage(
                    "/DoNotRespond: Welcome sent and service selection requested."
                ),
            ],
        },
    )


# %% Tool 2: ask_user_to_select_service
@tool
async def ask_user_to_select_service(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Sends interactive WhatsApp buttons asking user to select service type.
    MUST be called after every response to guide user to select Takeaway/Delivery/Something Else.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    rest_ref = (state.get("rest_ref") or ctx.rest_ref).lower()

    await select_service_wa_send(
        recipient=recipient,
        wa_client=ctx.wa_client,
        rest_ref=rest_ref,
    )

    return Command(
        goto=END,
        update={
            "rest_ref": rest_ref,
            "active_agent": "triage_agent",
            "messages": [
                ToolMessage(
                    "Service selection buttons sent (Takeaway/Delivery/Something Else).",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Please select how I can help you today."),
            ],
        },
    )


# %% Tool 3: capture_marketing_consent
@tool
async def capture_marketing_consent(
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Sends marketing consent buttons (Yes/No) to the user.
    Call this before terminating the conversation to ask if the user wants marketing updates.
    Do not call if ask_for_consent is false in state.
    """
    # Early exit if the question already asked
    if not state.get("ask_for_consent", False):
        return Command(
            goto=END,
            update={
                "messages": [
                    ToolMessage(
                        "Marketing consent already captured. Proceed with termination.",
                        tool_call_id=tool_call_id,
                    ),
                ],
            },
        )

    ctx = runtime.context
    recipient = ctx.recipient
    rest_ref = (state.get("rest_ref") or ctx.rest_ref).lower()

    await select_marketing_consent_wa_send(
        recipient=recipient,
        wa_client=ctx.wa_client,
        rest_ref=rest_ref,
    )

    return Command(
        goto=END,
        update={
            "ask_for_consent": False,  # This flip of flag ensures consent is asked only once
            "messages": [
                ToolMessage(
                    "Marketing consent buttons sent (Yes/No).",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Waiting for marketing consent response."),
            ],
        },
    )


# %% Terminate conversation tool (owned exclusively by triage)
@tool
async def terminate_conversation(
    reason_for_terminating_conversation: str,
    message_to_be_sent_to_user: str,
    state: Annotated[dict, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[ContextSchema],
):
    """
    Terminates the conversation and marks the thread as inactive.
    Call this tool when instructed by system messages to end the session.

    Scenarios when this tool should be called:
    1. Delivery cycle is complete (food delivered successfully)
    2. Customer is outside delivery area
    3. On timeouts (e.g., no delivery driver available after extended wait)

    Args:
        reason_for_terminating_conversation: Internal reason for ending the conversation (for logging).
        message_to_be_sent_to_user: A polite message to send to the user explaining the conversation is ending.

    Returns:
        Command: State update with ToolMessage and AIMessage indicating conversation ended.
    """
    ctx = runtime.context
    recipient = ctx.recipient
    ask_for_consent = state.get("ask_for_consent", False)

    if ask_for_consent:
        return "User has pending marketing consent. Call `capture_marketing_consent` before terminating."

    await ctx.wa_client.send_message(
        to=recipient,
        text=f"{message_to_be_sent_to_user}\n\nThank you and good bye! 👋",
    )

    await ctx.thread_handler.make_threads_inactive(recipient=recipient)

    return Command(
        goto=END,
        update={
            "messages": [
                ToolMessage(
                    f"Conversation terminated. Reason: {reason_for_terminating_conversation}",
                    tool_call_id=tool_call_id,
                ),
                AIMessage("/DoNotRespond: Conversation ended"),
            ],
            "ask_for_consent": False,
        },
    )


# %% Create triage agent
triage_tools = [
    send_welcome_message,
    ask_user_to_select_service,
    capture_marketing_consent,
    terminate_conversation,
    transfer_to_delivery,
    transfer_to_takeaway,
]

agent = create_agent(
    model=llm_settings.llm_client_single_tool_turn,
    tools=triage_tools,
    system_prompt=triage_agent_prompt_str,
    middleware=[cleanup_before_model, respond_on_wa],
    state_schema=AgentState,
    context_schema=ContextSchema,
)

# %%

""" # Test the triage agent

# %%
from sfcs_agent.rest_agent.agents.agent_harness import get_context_schema
from restaurant_agent_core.services.lg_utils import get_config_for_recipient

recipient = "447448440754"
config, _ = await get_config_for_recipient(recipient)

context_schema = await get_context_schema(recipient)

# %%
initial_msg: str | None = None
while True:
    if initial_msg is not None:
        human_msg = initial_msg
        initial_msg = None
    else:
        human_msg = input("Human Input: ")

    if human_msg.strip().lower() == "exit":
        break

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": human_msg}]},
        config=config,
        context=context_schema,
    )
    print(result["messages"][-1].content)
# %%
"""
