"""Post embedding storage with pgvector (PostgreSQL) / JSON text (SQLite tests)."""

import json
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, TypeDecorator, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

EMBEDDING_DIM = 384


class EmbeddingVector(TypeDecorator):
    """PostgreSQL: vector(384). SQLite tests: JSON text.

    pgvector's Vector bind processor stringifies the list. asyncpg's
    register_vector codec then rejects that string, so we pass a list.
    """

    impl = Text
    cache_ok = True

    class comparator_factory(TypeDecorator.Comparator):
        def cosine_distance(self, other):
            return self.op("<=>", return_type=Float())(other)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(EMBEDDING_DIM))
        return dialect.type_descriptor(Text)

    def bind_processor(self, dialect):
        if dialect.name == "postgresql":
            def process(value):
                if value is None:
                    return None
                return [float(x) for x in value]

            return process

        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return json.dumps(value)

        return process

    def result_processor(self, dialect, _coltype):
        if dialect.name == "postgresql":
            def process(value):
                if value is None:
                    return None
                return list(value)

            return process

        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return json.loads(value)
            return list(value)

        return process


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
