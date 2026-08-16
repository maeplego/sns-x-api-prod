import pytest

from app.labeling.events import POST_CREATED
from app.labeling.loading import get_plans_for_event, load_all
from app.labeling.registry import Plan, _PLAN_REGISTRY


def test_load_all_registers_flow_plans():
    load_all()
    plans = get_plans_for_event(POST_CREATED)
    keys = [plan.KEY for plan in plans]
    assert keys == [
        "post_publish",
        "post_safety_labels",
        "embedding",
        "fanout",
        "reply_side_effects",
        "engagement_init",
    ]


def test_duplicate_plan_keys_rejected():
    original = list(_PLAN_REGISTRY)

    class PlanOne(Plan):
        KEY = "duplicate"
        EVENT_TYPES = [POST_CREATED]

        async def execute(self, ctx) -> bool:
            return True

    class PlanTwo(Plan):
        KEY = "duplicate"
        EVENT_TYPES = [POST_CREATED]

        async def execute(self, ctx) -> bool:
            return True

    _PLAN_REGISTRY.clear()
    _PLAN_REGISTRY.extend([PlanOne, PlanTwo])

    from app.labeling.loading import _validate_plan_keys

    try:
        with pytest.raises(ValueError, match="Duplicate Plan.KEY"):
            _validate_plan_keys()
    finally:
        _PLAN_REGISTRY.clear()
        _PLAN_REGISTRY.extend(original)
