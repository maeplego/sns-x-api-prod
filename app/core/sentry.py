"""Optional Sentry error monitoring (no-op when SENTRY_DSN is empty)."""

from __future__ import annotations

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.core.config import settings


def init_sentry() -> None:
    if not settings.sentry_dsn.strip():
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.strip(),
        environment=settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
    )
