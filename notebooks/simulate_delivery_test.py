"""Simulate the delivery initialization flow for a single test order.

Cleans up any prior dispatch state for the order, initializes a fresh delivery
via the ``init_delivery`` RPC, and forces the delivery summary to ``unassigned``
so the process can proceed without the restaurant confirmation step.

Bypassing the restaurant confirmation also skips the step that normally sets
``pickup_time``. A rider dispatch created for an ``unassigned`` summary reads
``pickup_time`` and formats it with ``fmt_uk_time``; a ``None`` value crashes
when ``.astimezone()`` is called. This simulation therefore sets a valid
``pickup_time`` in the same update that forces the ``unassigned`` status so the
downstream dispatch has a usable timestamp.
"""

# %% Imports and test parameters.
import asyncio
from datetime import datetime, timedelta, timezone

from restaurant_agent_runtime.config import client_ordelo, logger

# Lead time applied to the simulated pickup so it lands in the near future.
PICKUP_LEAD_TIME = timedelta(minutes=30)

# %% Delivery initialization helper.
async def init_delivery_summary(order_number: str, recipient: str) -> None:
    """Initialize a delivery via the ``init_delivery`` RPC call."""
    try:
        # Run the blocking RPC call in a thread pool to avoid blocking the event loop.
        response = await asyncio.to_thread(
            lambda: client_ordelo.rpc(
                "init_delivery",
                {"p_cust_id": recipient, "p_order_number": order_number},
            ).execute()
        )
        logger.info(
            f"init_delivery completed for order {order_number} with response {response}"
        )
    except Exception as exc:
        logger.error(f"init_delivery failed for order {order_number}: {exc}")


# %% Simulation entrypoint.
async def simulate_delivery(recipient: str, order_number: str) -> None:
    """Run the end-to-end delivery simulation for one order."""
    logger.info(
        "Testing delivery for user %s with order %s", recipient, order_number
    )

    # Cleanup - reset any prior dispatch state for the order.
    await asyncio.to_thread(
        lambda: client_ordelo.rpc(
            "cleanup_delivery_order", {"p_order_number": order_number}
        ).execute()
    )

    # Initialize the delivery so the downstream process can follow.
    logger.info(
        f"Initializing delivery for user {recipient} with order {order_number}"
    )
    await init_delivery_summary(order_number, recipient)

    # Bypass the restaurant confirmation by forcing the summary to unassigned.
    # Also set pickup_time in the same update: the skipped confirmation step is
    # what normally populates it, and a None pickup_time crashes the rider
    # dispatch when fmt_uk_time calls .astimezone() on it.
    pickup_time = datetime.now(timezone.utc) + PICKUP_LEAD_TIME
    await asyncio.to_thread(
        lambda: client_ordelo.table("delivery_summary")
        .update(
            {
                "status": "unassigned",
                "pickup_time": pickup_time.isoformat(),
            }
        )
        .eq("order_number", order_number)
        .execute()
    )

    logger.info(
        f"Delivery simulation complete for order {order_number} "
        f"with pickup_time {pickup_time.isoformat()}"
    )


# %%
RECIPIENT = "447448440754"
ORDER_NUMBER = "BNAT-EEMF-24"

# %%
await simulate_delivery(RECIPIENT, ORDER_NUMBER)
#
# %% Run the simulation.
if __name__ == "__main__":
    asyncio.run(simulate_delivery(RECIPIENT, ORDER_NUMBER))
