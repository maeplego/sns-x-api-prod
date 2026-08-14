from app.labeling.registry import Plan, register_plan


def register[T: type](cls: T) -> T:
    if isinstance(cls, type) and issubclass(cls, Plan):
        return register_plan(cls)
    raise TypeError(f"@register expects a Plan subclass, got {cls!r}")
