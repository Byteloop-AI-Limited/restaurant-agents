"""Build one isolated FastAPI and PyWa application per restaurant."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from restaurant_agent_core.runtime import (
    GraphAdapterFactory,
    RestaurantIdentity,
    RestaurantPresentation,
    RestaurantRuntime,
    RestaurantSettingsBundle,
)
from restaurant_agent_core.waba_callback import build_runtime_details
from restaurant_agent_core.watomation.activity import ActivityMiddleware
from restaurant_agent_core.watomation import activity


@dataclass(frozen=True, slots=True)
class AgentBindings:
    """Small app-owned surface required by shared WhatsApp handlers."""

    callback_data_type: type
    select_service_sender: Callable[..., Any]


SettingsLoader = Callable[[RestaurantIdentity], RestaurantSettingsBundle]
AsyncWaFactory = Callable[[Any, FastAPI], Any]
SyncWaFactory = Callable[[Any], Any]


def _default_settings_loader(
    identity: RestaurantIdentity,
) -> RestaurantSettingsBundle:
    from restaurant_agent_core.config.bundle import load_settings_bundle

    return load_settings_bundle(identity)


def _default_async_wa_factory(waba_settings: Any, app: FastAPI) -> Any:
    return waba_settings.create_async_client(server=app)


def _default_sync_wa_factory(waba_settings: Any) -> Any:
    return waba_settings.create_sync_client()


def _register_whatsapp_handlers(
    runtime: RestaurantRuntime,
    graph_adapter: Any,
    bindings: AgentBindings,
) -> None:
    from pywa import filters
    from pywa.handlers import CallbackButtonHandler, MessageHandler

    from restaurant_agent_core.watomation.on_callback_handler import (
        admin_collection_ready,
        delivery_address_confirmation,
        restaurant_order_confirmation_handler,
        select_consent_handler,
        select_service_handler,
    )
    from restaurant_agent_core.watomation.on_message_graph_handler import (
        ALLOWED_USERS_FILTER,
        WHEN_ADHOC_TEST,
        WHEN_ADHOC_TEST_TAKEAWAY,
        WHEN_DEBUG,
        WHEN_PAYMENT_COMPLETE,
        WHEN_RESET,
        create_out_of_hours_filter,
        handle_adhoc_test,
        handle_adhoc_test_takeaway,
        handle_debug_state,
        handle_request_location_response,
        handle_wa_msg_in_graph,
        reset_thread,
        send_closed_message,
        send_redirect_to_offline_mode,
        simulate_payment_complete,
    )

    wa = runtime.async_wa_client

    async def bound_closed_message(client, message):
        return await send_closed_message(client, message, runtime=runtime)

    async def bound_reset(client, message):
        return await reset_thread(client, message, runtime=runtime)

    async def bound_adhoc(client, message):
        return await handle_adhoc_test(
            client, message, runtime=runtime, graph_adapter=graph_adapter
        )

    async def bound_adhoc_takeaway(client, message):
        return await handle_adhoc_test_takeaway(
            client, message, runtime=runtime, graph_adapter=graph_adapter
        )

    async def bound_debug(client, message):
        return await handle_debug_state(client, message, graph_adapter=graph_adapter)

    async def bound_graph(client, message):
        return await handle_wa_msg_in_graph(
            client, message, graph_adapter=graph_adapter
        )

    async def bound_delivery_address(client, callback):
        return await delivery_address_confirmation(
            client,
            callback,
            callback_data_type=bindings.callback_data_type,
            graph_adapter=graph_adapter,
        )

    async def bound_collection_ready(client, callback):
        return await admin_collection_ready(
            client,
            callback,
            callback_data_type=bindings.callback_data_type,
            runtime=runtime,
        )

    async def bound_order_confirmation(client, callback):
        return await restaurant_order_confirmation_handler(
            client, callback, callback_data_type=bindings.callback_data_type
        )

    async def bound_service(client, callback):
        return await select_service_handler(
            client,
            callback,
            callback_data_type=bindings.callback_data_type,
            graph_adapter=graph_adapter,
            runtime=runtime,
            select_service_sender=bindings.select_service_sender,
        )

    async def bound_consent(client, callback):
        return await select_consent_handler(
            client,
            callback,
            callback_data_type=bindings.callback_data_type,
            graph_adapter=graph_adapter,
            runtime=runtime,
        )

    wa.add_handlers(
        MessageHandler(
            callback=bound_closed_message,
            filters=create_out_of_hours_filter(runtime),
        ),
        MessageHandler(
            callback=send_redirect_to_offline_mode, filters=ALLOWED_USERS_FILTER
        ),
        MessageHandler(callback=bound_reset, filters=WHEN_RESET),
        MessageHandler(
            callback=handle_request_location_response, filters=filters.location
        ),
        MessageHandler(callback=bound_adhoc_takeaway, filters=WHEN_ADHOC_TEST_TAKEAWAY),
        MessageHandler(callback=bound_adhoc, filters=WHEN_ADHOC_TEST),
        MessageHandler(
            callback=simulate_payment_complete, filters=WHEN_PAYMENT_COMPLETE
        ),
        MessageHandler(callback=bound_debug, filters=WHEN_DEBUG),
        MessageHandler(callback=bound_graph),
    )
    wa.add_handlers(
        CallbackButtonHandler(
            callback=bound_delivery_address,
            filters=filters.contains("/ConfirmDeliveryAddress"),
        ),
        CallbackButtonHandler(
            callback=bound_collection_ready,
            filters=filters.contains("/AdminCollectionReady"),
        ),
        CallbackButtonHandler(
            callback=bound_order_confirmation,
            filters=filters.contains("/RestaurantOrder"),
        ),
        CallbackButtonHandler(
            callback=bound_service,
            filters=filters.contains("/SelectService"),
        ),
        CallbackButtonHandler(
            callback=bound_consent,
            filters=filters.contains("/SelectConsent"),
        ),
    )


def create_restaurant_app(
    identity: RestaurantIdentity,
    presentation: RestaurantPresentation,
    graph_adapter_factory: GraphAdapterFactory,
    agent_bindings: AgentBindings,
    *,
    settings_loader: SettingsLoader = _default_settings_loader,
    async_wa_factory: AsyncWaFactory = _default_async_wa_factory,
    sync_wa_factory: SyncWaFactory = _default_sync_wa_factory,
    register_whatsapp_handlers: bool = True,
    include_order_router: bool = True,
    include_rider_router: bool = True,
    include_thread_router: bool = True,
) -> FastAPI:
    """Create one independently configured restaurant application."""

    settings = settings_loader(identity)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            await settings.database.close_pool()

    app = FastAPI(title=f"{presentation.display_name} Agent", lifespan=lifespan)
    app.add_middleware(ActivityMiddleware)

    async_wa_client = async_wa_factory(settings.waba, app)
    sync_wa_client = sync_wa_factory(settings.waba)
    runtime = RestaurantRuntime(
        identity=identity,
        presentation=presentation,
        settings=settings,
        async_wa_client=async_wa_client,
        sync_wa_client=sync_wa_client,
    )
    graph_adapter = graph_adapter_factory(runtime)
    app.state.restaurant_runtime = runtime
    app.state.graph_adapter = graph_adapter

    if register_whatsapp_handlers:
        _register_whatsapp_handlers(runtime, graph_adapter, agent_bindings)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"status": "ok"}

    @app.get("/internal/activity", include_in_schema=False)
    async def internal_activity():
        return activity.snapshot()

    @app.get("/identity", include_in_schema=False)
    async def runtime_identity():
        return {
            "rest_ref": identity.rest_ref,
            "waba_namespace": identity.waba_namespace,
        }

    @app.get("/details", include_in_schema=False)
    async def runtime_details():
        return await build_runtime_details(runtime)

    # Routers read runtime and graph dependencies from app.state per request.
    if include_rider_router:
        from restaurant_agent_core.watomation.routers.rider_event_hooks import (
            router as rider_router,
        )

        app.include_router(rider_router, prefix="/rider-event-hooks")
    if include_order_router:
        from restaurant_agent_core.watomation.routers.order_event_hooks import (
            router as order_router,
        )

        app.include_router(order_router, prefix="/order-event-hooks")
    if include_thread_router:
        from restaurant_agent_core.watomation.routers.thread_hooks import (
            router as thread_router,
        )

        app.include_router(thread_router, prefix="/thread-hooks")
    return app
