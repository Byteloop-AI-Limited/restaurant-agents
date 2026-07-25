"""
Config module stubs for unit tests
    . Provides fake settings, logger, SKU map, and Supabase-like clients
    . Avoids importing production config modules that create real external clients
    . Records fake client operations for assertions
  Functions/Classes:
    . DummyLogger
    . FakeSupabaseResponse
    . FakeSupabaseQuery
    . FakeSupabaseClient
    . FakeAsyncWaClient
    . build_config_stub
"""

from types import ModuleType, SimpleNamespace


class DummyLogger:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.warnings = []

    def info(self, message, *args, **kwargs):
        self.infos.append((message, args, kwargs))

    def error(self, message, *args, **kwargs):
        self.errors.append((message, args, kwargs))

    def warning(self, message, *args, **kwargs):
        self.warnings.append((message, args, kwargs))

    def debug(self, message, *args, **kwargs):
        self.infos.append((message, args, kwargs))

    def exception(self, message, *args, **kwargs):
        self.errors.append((message, args, kwargs))


class FakeSupabaseResponse:
    def __init__(self, data=None):
        self.data = data


class FakeSupabaseQuery:
    def __init__(self, client, table_name=None, data=None):
        self.client = client
        self.table_name = table_name
        self.data = data
        self.calls = []

    def select(self, *args, **kwargs):
        self.calls.append(("select", args, kwargs))
        return self

    def insert(self, *args, **kwargs):
        self.calls.append(("insert", args, kwargs))
        return self

    def upsert(self, *args, **kwargs):
        self.calls.append(("upsert", args, kwargs))
        return self

    def update(self, *args, **kwargs):
        self.calls.append(("update", args, kwargs))
        return self

    def delete(self, *args, **kwargs):
        self.calls.append(("delete", args, kwargs))
        return self

    def eq(self, *args, **kwargs):
        self.calls.append(("eq", args, kwargs))
        return self

    def order(self, *args, **kwargs):
        self.calls.append(("order", args, kwargs))
        return self

    def limit(self, *args, **kwargs):
        self.calls.append(("limit", args, kwargs))
        return self

    def single(self, *args, **kwargs):
        self.calls.append(("single", args, kwargs))
        if isinstance(self.data, list):
            self.data = self.data[0] if self.data else None
        return self

    def execute(self):
        self.client.queries.append(self)
        return FakeSupabaseResponse(self.data)


class FakeSupabaseClient:
    def __init__(self, table_data=None, rpc_data=None):
        self.table_data = table_data or {}
        self.rpc_data = rpc_data or {}
        self.queries = []
        self.rpc_calls = []

    def table(self, table_name):
        return FakeSupabaseQuery(self, table_name, self.table_data.get(table_name, []))

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params))
        return FakeSupabaseQuery(self, name, self.rpc_data.get(name))


class FakeAsyncWaClient:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)
        return SimpleNamespace(id=kwargs.get("id"))


def build_config_stub():
    module = ModuleType("config")
    module.logger = DummyLogger()
    module.SKU_PRODUCT_NAME_MAP = {
        "chilli_chicken": "Chilli Chicken",
        "aloo_gobi": "Aloo Gobi",
        "mango_lassi": "Mango Lassi",
        "apple_and_mango_smoothie": "Apple and Mango Smoothie",
    }
    module.project_settings = SimpleNamespace(
        salt="unit-test-salt",
        project_root="/tmp/sfcs",
        rest_ref="SFCS",
    )
    module.stripe_settings = SimpleNamespace(
        headers={"Authorization": "Bearer test"},
        generate_payment_intent_url=lambda order_id, thread_id: (
            f"https://stripe.test/threads/{thread_id}/orders/{order_id}/payment-url"
        ),
    )
    module.ms_settings = SimpleNamespace(
        stripe_url="https://stripe.test",
        stripe_headers={"Authorization": "Bearer test"},
        pricing_url="https://pricing.test/calculate",
    )
    module.pg_settings = SimpleNamespace(db_uri="postgresql://test", connection_kwargs={})
    module.google_settings = SimpleNamespace(maps_api_key="maps-test-key")
    module.llm_settings = SimpleNamespace(
        openai_api_key="sk-test",
        model="gpt-test",
        llm_client_single_tool_turn=object(),
    )
    module._async_wa_client = FakeAsyncWaClient()
    module.client = FakeSupabaseClient()
    module.client_ordelo = FakeSupabaseClient()
    return module
