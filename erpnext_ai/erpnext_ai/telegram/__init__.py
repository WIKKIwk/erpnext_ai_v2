"""Telegram integration package for erpnext_ai.

Modules in this namespace coordinate Telegram bot orchestration, including
configuration loading, persistent storage, and ERPNext API interactions.
"""

from importlib import import_module
from typing import Any

__all__ = ["BotConfig", "BotStorage", "ERPNextClient", "load_bot_config"]


def __getattr__(name: str) -> Any:
    if name in {"BotConfig", "load_bot_config"}:
        module = import_module(".config", __name__)
        return getattr(module, name)
    if name == "BotStorage":
        module = import_module(".storage", __name__)
        return getattr(module, name)
    if name == "ERPNextClient":
        module = import_module(".erpnext_client", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
