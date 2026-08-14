"""Post embedding storage with pgvector (PostgreSQL) / JSON text (SQLite tests)."""

import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, TypeDecorator, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

EMBEDDING_DIM = 384


class EmbeddingVector(TypeDecorator):
    """PostgreSQL: vector(384). SQLite tests: JSON text."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(EMBEDDING_DIM))
        return dialect.type_descriptor(Text)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value)
        return json.loads(value)


class PostEmbedding(Base):
    __tablename__ = "post_embeddings"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector)
    model: Mapped[str] = mapped_column(String(64), default="hash-v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
