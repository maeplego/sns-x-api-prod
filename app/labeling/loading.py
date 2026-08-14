import importlib
import pkgutil
from types import ModuleType

import app.labeling.flows
from app.labeling.registry import build_event_plan_index, registered_plan_classes

_loaded = False
_event_plan_index: dict[str, list] | None = None


def _import_recursively(package: ModuleType) -> None:
    for mod in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{package.__name__}.{mod.name}")
        if mod.ispkg:
            _import_recursively(module)


def _validate_plan_keys() -> None:
    keys = [plan_cls.KEY for plan_cls in registered_plan_classes()]
    duplicates = {key for key in keys if keys.count(key) > 1}
    if duplicates:
        raise ValueError(f"Duplicate Plan.KEY values: {sorted(duplicates)}")


def load_all() -> dict[str, list]:
    global _loaded, _event_plan_index
    if _loaded and _event_plan_index is not None:
        return _event_plan_index

    _import_recursively(app.labeling.flows)
    _validate_plan_keys()
    _event_plan_index = build_event_plan_index()
    _loaded = True
    return _event_plan_index


def get_plans_for_event(event_type: str) -> list:
    index = load_all()
    return index.get(event_type, [])
