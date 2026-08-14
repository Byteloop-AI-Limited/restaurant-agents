"""
Thread hooks router for agent thread lifecycle operations
    . Accepts database-selected stale-thread batches for background termination
    . Provides active thread lookup for recipients
    . Provides state inspection and debug endpoints
    . Implements Human-in-the-Loop (HIL) pattern for manual agent intervention
    . Validates the stale-thread route against the locally configured rest_ref
  Functions/Classes:
    . validate_rest_ref - Validates rest_ref and returns 404 if invalid
    . HILMessageRequest
    . TerminateStaleThreadsRequest
    . terminate_stale_active_threads
    . get_active_thread
    . debug_state_values_path
    . debug_state_path
    . debug_admin_state_path
    . debug_thread_path
    . debug_state_by_thread_path
    . hil_system_message
"""

# %%
import asyncio
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from restaurant_agent_runtime.runtime import GraphAdapter, RestaurantRuntime
from restaurant_agent_runtime.web.dependencies import (
    get_graph_adapter,
    get_restaurant_runtime,
)
from restaurant_agent_runtime.watomation.background_task_runner import run_background_task

# %% Define Dependencies and routes

router = APIRouter(tags=["thread-hooks"])

STALE_THREAD_TERMINATION_SYSTEM_MSG = (
    "Call tool `terminate_conversation` with reason - "
    "Ending the conversation due to inactivity."
)
STALE_THREAD_TERMINATION_CONCURRENCY = 3


# %% Validation helper
def validate_rest_ref(rest_ref: str, runtime: RestaurantRuntime) -> str:
    """Validate the route against this service's configured restaurant."""

    rest_ref_upper = rest_ref.upper()
    if not runtime.identity.matches(rest_ref_upper):
        raise HTTPException(status_code=404, detail=f"Restaurant not found: {rest_ref}")
    return rest_ref_upper


# %% Stale-thread termination models and helpers
class StaleThreadCandidate(BaseModel):
    """One stale thread selected by the scheduled database job."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(min_length=1)
    recipient: str = Field(min_length=1)


class TerminateStaleThreadsRequest(BaseModel):
    """One scheduled-job batch for a restaurant service."""

    model_config = ConfigDict(extra="forbid")

    job_run_id: UUID
    threads: list[StaleThreadCandidate] = Field(min_length=1)


class TerminateStaleThreadsAccepted(BaseModel):
    """Acknowledgement returned before background graph work starts."""

    job_run_id: UUID
    received_count: int
    queued_count: int


def _thread_rest_ref(thread_id: str) -> str:
    return thread_id.partition("-")[0].upper()


async def _terminate_stale_thread_candidate(
    *,
    rest_ref: str,
    job_run_id: UUID,
    candidate: StaleThreadCandidate,
    semaphore: asyncio.Semaphore,
    graph_adapter: GraphAdapter,
) -> None:
    """Terminate one scheduled thread without failing sibling work."""

    task_logger = logger.bind(
        job_run_id=str(job_run_id),
        rest_ref=rest_ref,
        thread_id=candidate.thread_id,
    )
    async with semaphore:
        try:
            config = {
                "configurable": {
                    "thread_id": candidate.thread_id,
                    "recipient": candidate.recipient,
                }
            }
            await graph_adapter.run_rest_graph_with_custom_msg(
                recipient=candidate.recipient,
                config=config,
                system_msg=STALE_THREAD_TERMINATION_SYSTEM_MSG,
                state_update_dict={"active_agent": "triage_agent"},
            )
            task_logger.info("Stale-thread termination completed")
        except asyncio.CancelledError:
            task_logger.warning("Stale-thread termination cancelled")
            raise
        except Exception:
            task_logger.exception(
                "Stale-thread termination failed; continuing remaining batch"
            )


async def _process_stale_thread_batch(
    *,
    rest_ref: str,
    request: TerminateStaleThreadsRequest,
    graph_adapter: GraphAdapter,
) -> None:
    """Process a scheduled batch with bounded graph concurrency."""

    batch_logger = logger.bind(
        job_run_id=str(request.job_run_id),
        rest_ref=rest_ref,
        thread_count=len(request.threads),
    )
    batch_logger.info("Stale-thread termination batch started")
    semaphore = asyncio.Semaphore(STALE_THREAD_TERMINATION_CONCURRENCY)
    await asyncio.gather(
        *(
            _terminate_stale_thread_candidate(
                rest_ref=rest_ref,
                job_run_id=request.job_run_id,
                candidate=candidate,
                semaphore=semaphore,
                graph_adapter=graph_adapter,
            )
            for candidate in request.threads
        )
    )
    batch_logger.info("Stale-thread termination batch completed")


# %%
@router.post(
    "/{rest_ref}/terminate-stale-active-threads",
    status_code=202,
    response_model=TerminateStaleThreadsAccepted,
    summary="Queue database-selected stale threads for termination",
    description="""
    Called directly by job_terminate_stale_active_threads(). The scheduled job has
    already applied the restaurant timeout and retain_thread policy. This endpoint
    validates the reduced thread_id/recipient contract and queues graph execution.
    It intentionally performs no additional stale-state database check.
    """,
)
async def terminate_stale_active_threads(
    rest_ref: str,
    request: TerminateStaleThreadsRequest,
    background_tasks: BackgroundTasks,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
) -> TerminateStaleThreadsAccepted:
    rest_ref = validate_rest_ref(rest_ref, runtime)
    mismatched_thread_ids = [
        candidate.thread_id
        for candidate in request.threads
        if _thread_rest_ref(candidate.thread_id) != rest_ref
    ]
    if mismatched_thread_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "thread_id prefix does not match route rest_ref",
                "thread_ids": mismatched_thread_ids,
            },
        )

    background_tasks.add_task(
        run_background_task,
        "terminate_stale_thread_batch",
        _process_stale_thread_batch,
        rest_ref=rest_ref,
        request=request,
        graph_adapter=graph_adapter,
    )

    thread_count = len(request.threads)
    return TerminateStaleThreadsAccepted(
        job_run_id=request.job_run_id,
        received_count=thread_count,
        queued_count=thread_count,
    )


@router.get("/get-active-thread/{rest_ref}/{recipient}")
async def get_active_thread(
    rest_ref: str,
    recipient: str,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
):
    rest_ref = validate_rest_ref(rest_ref, runtime)
    pool = await runtime.settings.database.get_pool()
    from restaurant_agent_runtime.services.thread_management import ThreadHandler

    thread_handler = ThreadHandler(pool, agent=runtime.identity.rest_ref)
    response = await thread_handler.get_active_thread(recipient)

    thread_id = "-1"
    if response and response.get("thread_id") is not None:
        thread_id = str(response["thread_id"])

    return {"thread_id": thread_id, "rest_ref": rest_ref, "recipient": recipient}


@router.get("/debug-state-values")
async def debug_state_values_path(
    recipient: Optional[str] = "447448440754",
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    debug_stack = await graph_adapter.debug_state_values(recipient)
    return debug_stack


@router.get("/debug-state")
async def debug_state_path(
    recipient: Optional[str] = "447448440754",
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    debug_stack = await graph_adapter.debug_state(recipient, full_state=True)
    return debug_stack


@router.get("/debug-thread")
async def debug_thread_path(
    thread_id: str, graph_adapter: GraphAdapter = Depends(get_graph_adapter)
):
    debug_stack = await graph_adapter.debug_state_by_thread(thread_id)
    return debug_stack


# %%


@router.get("/debug-admin-state")
async def debug_admin_state_path(
    recipient: Optional[str] = "447448440754",
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    debug_stack = await graph_adapter.debug_state(recipient)
    return debug_stack


@router.get("/debug-state-by-thread")
async def debug_state_by_thread_path(
    thread_id: str, graph_adapter: GraphAdapter = Depends(get_graph_adapter)
):
    return await graph_adapter.debug_state_by_thread(thread_id)


class HILMessageRequest(BaseModel):
    thread_id: str
    update_message: str
    recipient: Optional[str] = None
    state_update_dict: Optional[Dict[str, Any]] = None


@router.post(
    "/hil-system-message",
    summary="Run agent graph with a HIL system message",
    description="""
    Runs the agent graph with a system message for a given thread_id.
    Used for human-in-the-loop intervention.
    If recipient is not provided, it is fetched from the thread table.
    """,
)
async def hil_system_message(
    request: HILMessageRequest,
    runtime: RestaurantRuntime = Depends(get_restaurant_runtime),
    graph_adapter: GraphAdapter = Depends(get_graph_adapter),
):
    recipient = request.recipient
    # Handle both None and "None" string from common client errors
    if not recipient or recipient == "None":
        result = (
            runtime.settings.database_client.table("thread")
            .select("thread_id", "recipient")
            .eq("thread_id", request.thread_id)
            .eq("is_active", True)
            .execute()
        )
        logger.debug(f"Thread fetch result: {result}")
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Thread not found or inactive: {request.thread_id}",
            )
        recipient = result.data[0]["recipient"]

    state_update_dict = dict(request.state_update_dict or {})
    state_update_dict.setdefault("active_agent", "delivery_agent")
    system_msg = f"Call `update_customer` with message={request.update_message!r}"
    ai_response = await graph_adapter.run_rest_graph_with_custom_msg(
        recipient=recipient,
        system_msg=system_msg,
        state_update_dict=state_update_dict,
    )
    return {
        "status": "success",
        "thread_id": request.thread_id,
        "recipient": recipient,
        "response": ai_response,
    }
