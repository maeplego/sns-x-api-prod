import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class SafetyTargetType(str, enum.Enum):
    POST = "post"
    USER = "user"


class SafetyLabel(Base):
    """Visibility-impacting labels (indie Visibility Filtering / Under the Hood)."""

    __tablename__ = "safety_labels"
    __table_args__ = (
        UniqueConstraint(
            "target_type",
            "target_id",
            "label",
            name="uq_safety_labels_target_label",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type: Mapped[SafetyTargetType] = mapped_column(
        Enum(SafetyTargetType, name="safety_target_type", native_enum=False)
    )
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    label: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
