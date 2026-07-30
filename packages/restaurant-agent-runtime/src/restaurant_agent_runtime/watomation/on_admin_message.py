"""Legacy admin handlers with explicit graph and runtime dependencies."""

from typing import Any

from pywa_async import WhatsApp
from pywa.types import Message

from restaurant_agent_runtime.config import logger
from restaurant_agent_runtime.runtime import RestaurantRuntime
from restaurant_agent_runtime.services.thread_management import ThreadHandler


async def handle_wa_msg_in_admin_graph(
    wa: WhatsApp, msg: Message, *, graph_call: Any
):
    await msg.indicate_typing()
    logger.info(f"Admin Message: {msg}")
    await graph_call(recipient=msg.sender, human_msg=msg.text)


async def handle_admin_order(wa: WhatsApp, msg: Message, *, graph_call: Any):
    await msg.indicate_typing()
    skus = ", ".join(product.sku for product in msg.order.products)
    await graph_call(
        recipient=msg.sender,
        human_msg=f"Update availability to `out of stock` for skus: [{skus}]",
    )


async def handle_admin_referred_product(
    wa: WhatsApp, msg: Message, *, graph_call: Any
):
    await msg.indicate_typing()
    referred = getattr(msg.reply_to_message, "referred_product", None)
    if referred is None:
        return
    await graph_call(
        recipient=msg.sender,
        human_msg=f"Update availability to `in stock` for sku: {referred.sku}",
    )


async def reset_thread_admin(
    wa: WhatsApp, msg: Message, *, runtime: RestaurantRuntime
):
    pool = await runtime.settings.database.get_pool()
    handler = ThreadHandler(pool, agent=runtime.identity.rest_ref)
    recipient = msg.from_user.wa_id
    await handler.make_threads_inactive(recipient=recipient)
    await wa.send_message(to=recipient, text="Starting new conversation for admin")
