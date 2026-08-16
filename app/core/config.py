from pydantic_settings import BaseSettings, SettingsConfigDict

WEAK_JWT_SECRETS = frozenset({"dev-only-change-me", "change-me-in-production", ""})
WEAK_POSTGRES_PASSWORDS = frozenset({"sns", "password", ""})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "sns"
    postgres_password: str = "sns"
    postgres_db: str = "sns_x_prod"

    redis_host: str = "localhost"
    redis_port: int = 6379

    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 14

    cors_origins: str = (
        "http://localhost:5175,http://127.0.0.1:5175,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174"
    )

    allowed_hosts: str = ""

    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def is_weak_jwt_secret(self) -> bool:
        return self.jwt_secret in WEAK_JWT_SECRETS or len(self.jwt_secret) < 32

    @property
    def is_weak_postgres_password(self) -> bool:
        return self.postgres_password in WEAK_POSTGRES_PASSWORDS

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
