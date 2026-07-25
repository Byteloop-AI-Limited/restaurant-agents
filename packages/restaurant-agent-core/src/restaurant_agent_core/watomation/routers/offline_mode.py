"""Optional offline-mode controller bound to one restaurant runtime."""

from fastapi import APIRouter

from restaurant_agent_core.runtime import RestaurantRuntime


async def handle_offline_message(_, msg):
    await msg.reply("Apologies, we are currently offline. Please try again later.")


def create_offline_mode_router(runtime: RestaurantRuntime) -> APIRouter:
    router = APIRouter(tags=["offline-mode"])

    @router.post("/set")
    def set_offline_mode(enable: bool = True, base_url: str | None = None):
        if base_url is None:
            configuration = (
                runtime.sync_wa_client.get_business_phone_number().webhook_configuration
            )
            current_url = configuration.get("whatsapp_business_account")
            if enable and "offline-mode" in current_url:
                return {
                    "offline_mode": True,
                    "callback_url": current_url,
                    "message": "Already in offline mode",
                }
            base_url = current_url.rstrip("/").removesuffix("/offline-mode")
        else:
            base_url = base_url.rstrip("/")

        callback_url = f"{base_url}/offline-mode" if enable else base_url
        runtime.sync_wa_client.override_waba_callback_url(
            callback_url=callback_url,
            verify_token=runtime.settings.waba.waa_verify_token,
            waba_id=runtime.settings.waba.waa_account_id,
        )
        return {"offline_mode": enable, "callback_url": callback_url}

    @router.get("/details")
    async def get_details():
        phone = await runtime.async_wa_client.get_business_phone_number()
        return {
            "phone_id": str(runtime.settings.waba.waa_phone_id),
            "display_phone_num": phone.display_phone_number,
            "verified_name": phone.verified_name,
            "callback_url": runtime.settings.waba.waa_callback_url,
            "callback_url_on_waba": phone.webhook_configuration["application"],
            "llm_model": runtime.settings.llm.model,
        }

    return router
