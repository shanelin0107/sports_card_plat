from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "sports-card-platform-api"
    app_env: str = "dev"
    database_url: str = "postgresql+psycopg2://postgres:postgres@db:5432/sports_cards"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
