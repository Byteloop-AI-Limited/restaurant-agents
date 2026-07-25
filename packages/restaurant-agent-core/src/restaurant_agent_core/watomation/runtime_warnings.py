import warnings


def configure_runtime_warning_filters() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r".*`example` has been deprecated, please use `examples` instead.*",
    )
