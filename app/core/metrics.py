from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "sns_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
ERRORS = Counter(
    "sns_http_errors_total",
    "HTTP responses with status >= 500",
    ["method", "path"],
)
LATENCY = Histogram(
    "sns_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def normalize_path(path: str) -> str:
    """Avoid high-cardinality labels from UUIDs / ids in paths."""
    parts: list[str] = []
    for part in path.split("/"):
        if not part:
            continue
        if len(part) >= 8 and all(c in "0123456789abcdef-" for c in part.lower()):
            parts.append(":id")
        else:
            parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
