"""Plugin registry for cedolino PDF format plugins.

Usage:
    import plugins
    plugin = plugins.detect('cedolino.pdf')   # -> CedolinoPlugin subclass or None
    plugins.list_plugins()                    # -> list of (name, description)
"""

from importlib import import_module
import pkgutil
from pathlib import Path

from .base import CedolinoPlugin, CEDOLINO_SCHEMA, ITEM_SCHEMA, empty_cedolino, empty_item

_registry: list[type[CedolinoPlugin]] = []
_discovered = False


def register(cls: type[CedolinoPlugin]) -> type[CedolinoPlugin]:
    """Class decorator: add cls to the plugin registry."""
    _registry.append(cls)
    return cls


def _discover() -> None:
    global _discovered
    if _discovered:
        return
    _discovered = True
    pkg_dir = Path(__file__).parent
    for _, mod_name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        if mod_name not in ("base",):
            import_module(f"plugins.{mod_name}")


def get_plugins() -> list[type[CedolinoPlugin]]:
    _discover()
    return list(_registry)


def get_plugin(name: str) -> type[CedolinoPlugin] | None:
    for p in get_plugins():
        if p.name == name:
            return p
    return None


def detect(pdf_path: str) -> type[CedolinoPlugin] | None:
    for plugin in get_plugins():
        try:
            if plugin.can_handle(pdf_path):
                return plugin
        except Exception:
            pass
    return None


def list_plugins() -> list[tuple[str, str]]:
    return [(p.name, p.description) for p in get_plugins()]


__all__ = [
    "CedolinoPlugin",
    "CEDOLINO_SCHEMA",
    "ITEM_SCHEMA",
    "empty_cedolino",
    "empty_item",
    "register",
    "get_plugins",
    "get_plugin",
    "detect",
    "list_plugins",
]
