import os

os.environ["APP_ENV"] = "test"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.core.database as database
from app.core.database import get_db
from app.core.models import Base
import app.core.social_models  # noqa: F401
import app.core.embedding_models  # noqa: F401
from app.core.queue import set_event_bus
from app.labeling.loading import load_all
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite://"


@pytest.fixture
async def client():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    database.engine = engine
    database.SessionLocal = session_factory

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    set_event_bus(None)
    load_all()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    set_event_bus(None)
    await engine.dispose()
