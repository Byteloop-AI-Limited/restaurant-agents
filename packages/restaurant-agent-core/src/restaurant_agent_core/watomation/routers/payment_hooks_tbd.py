"""
Payment webhook handler module for the agent
    . Processes payment webhook events from payment providers
    . Extracts payment status information from webhook payloads
    . Updates payment status in database with transaction status
    . Triggers graph updates to notify agent of payment verification
    . Implements FastAPI router endpoints for payment webhooks
    . Retrieves app state resources for database access
  Functions/Classes:
    . handle_payment_complete - Processes payment completion and updates order status
    . payment_complete_path - FastAPI route handling payment completion webhooks
"""

# # %%
# from fastapi import APIRouter, Request, BackgroundTasks
# from restaurant_agent_core.config import client_ordelo
# Graph calls must be supplied by the restaurant-owned GraphAdapter.
# from loguru import logger

# # %% Define Dependancies and routes

# router = APIRouter(tags=["payment-hooks"])


# # %% supporting functions
# async def handle_payment_complete(request_body: dict):
#     """
#     Handles the update of the payment status in the graph.

#     Args:
#         request_body: The request body from the payment webhook
#         graph: the graph object
#         pool: the database connection pool
#     """
#     # update payment status to `requires_payment`, `requires_capture`
#     order_id = request_body["data"]["object"]["metadata"]["orderID"]
#     logger.info(f"order_id:{order_id} - PaymentComplete webhook from stripe called")

#     # Update the payment status
#     response = (
#         client_ordelo.table("food_order")
#         .update({"payment_status": "requires_capture"})
#         .eq("order_id", order_id)
#         .execute()
#     )

#     recipient = response.data[0]["recipient"]
#     thread_id = response.data[0]["thread_id"]

#     # logger.error(f"response:{response}")
#     # # update graph state
#     # config = {"configurable": {"thread_id": thread_id, "recipient": recipient}}
#     # await graph.aupdate_state(
#     #     config, {"is_payment_successful": True}, as_node="toolNode"
#     # )

#     await run_elai_graph_with_custom_msg(
#         recipient, system_msg="Verify if payment is complete"
#     )

#     return {"success": "success"}


# @router.post("/payment-complete")
# async def payment_complete_path(request: Request, background_tasks: BackgroundTasks):
#     # Unpack request
#     logger.info("PaymentComplete webhook from stripe called")
#     request_body: dict = await request.json()
#     background_tasks.add_task(handle_payment_complete, request_body)
#     return {"success": "success"}
