from abc import ABC, abstractmethod

_PLAN_REGISTRY: list[type["Plan"]] = []


class Plan(ABC):
    KEY: str
    EVENT_TYPES: list[str]
    ORDER: int = 0

    @abstractmethod
    async def execute(self, ctx) -> bool: ...


def register_plan(cls: type[Plan]) -> type[Plan]:
    if not (isinstance(cls, type) and issubclass(cls, Plan)):
        raise TypeError(f"register_plan expects a Plan subclass, got {cls!r}")
    if not getattr(cls, "KEY", None):
        raise ValueError(f"{cls.__name__} must define KEY")
    if not getattr(cls, "EVENT_TYPES", None):
        raise ValueError(f"{cls.__name__} must define EVENT_TYPES")
    if cls not in _PLAN_REGISTRY:
        _PLAN_REGISTRY.append(cls)
    return cls


def registered_plan_classes() -> list[type[Plan]]:
    return list(_PLAN_REGISTRY)


def clear_registry() -> None:
    _PLAN_REGISTRY.clear()


def build_event_plan_index() -> dict[str, list[Plan]]:
    index: dict[str, list[tuple[int, type[Plan]]]] = {}
    for plan_cls in _PLAN_REGISTRY:
        for event_type in plan_cls.EVENT_TYPES:
            index.setdefault(event_type, []).append((plan_cls.ORDER, plan_cls))

    sorted_index: dict[str, list[Plan]] = {}
    for event_type, entries in index.items():
        sorted_index[event_type] = [cls() for _, cls in sorted(entries, key=lambda x: x[0])]
    return sorted_index
