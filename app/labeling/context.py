import uuid
from dataclasses import dataclass, field


@dataclass
class TaskContext:
    event_type: str
    payload: dict
    errors: list[str] = field(default_factory=list)

    @property
    def post_id(self) -> uuid.UUID:
        return uuid.UUID(self.payload["post_id"])

    @property
    def author_id(self) -> uuid.UUID:
        return uuid.UUID(self.payload["author_id"])
