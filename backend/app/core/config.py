from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo layout: <root>/backend/app/core/config.py -> <root>
# In the container the same layout lives under /srv (see backend/Dockerfile).
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "sports-card-platform-api"
    app_env: str = "dev"
    database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/sports_cards"

    # Comma-separated list of browser origins allowed to call the API directly.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # When set, every /api/v1 request must send `X-API-Key: <api_key>`.
    # Leave empty for local development.
    api_key: str = ""

    # Create/upgrade tables on startup (idempotent) and load demo data into an empty DB.
    auto_init_db: bool = True
    seed_demo_data: bool = True

    # AI price research (Claude + web search). Empty key = feature disabled.
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-5-5"
    ai_max_searches: int = 8
    ai_max_fetches: int = 6

    ingestion_feed_path: str = str(PROJECT_ROOT / "seed" / "ebay_sample_feed.json")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        # Hosted Postgres providers (Neon, Render, Railway) hand out postgres:// or
        # postgresql:// URLs; SQLAlchemy needs the explicit driver.
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://") :]
        return url


settings = Settings()
