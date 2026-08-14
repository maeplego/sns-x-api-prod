from dataclasses import dataclass
from pathlib import Path

import yaml

WEIGHTS_PATH = Path(__file__).resolve().parents[2] / "ranking" / "weights.yaml"


@dataclass(frozen=True)
class RankingWeights:
    recency: float
    in_network_boost: float
    engagement: float
    author_affinity: float
    seen_penalty: float


def load_weights(path: Path = WEIGHTS_PATH) -> RankingWeights:
    if not path.exists():
        raise FileNotFoundError(f"Ranking weights file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("weights.yaml must be a mapping")

    required = ("recency", "in_network_boost", "engagement", "author_affinity", "seen_penalty")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"weights.yaml missing keys: {missing}")

    return RankingWeights(
        recency=float(raw["recency"]),
        in_network_boost=float(raw["in_network_boost"]),
        engagement=float(raw["engagement"]),
        author_affinity=float(raw["author_affinity"]),
        seen_penalty=float(raw["seen_penalty"]),
    )
