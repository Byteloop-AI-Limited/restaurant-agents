import importlib.util


def test_fapp_module_path_exists():
    assert importlib.util.find_spec("restaurant_agent_runtime.watomation.fapp") is not None
