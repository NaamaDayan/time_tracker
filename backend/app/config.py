from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://tracker:tracker@localhost:5432/time_tracker"
    user_timezone: str = "Asia/Jerusalem"
    clockify_api_key: str = ""
    clockify_workspace_id: str = ""
    # Optional override; default: ~/Library/Application Support/Clockify Desktop/Clockify_<user>.sqlite
    clockify_desktop_db_path: str = ""
    api_key: str = "dev-only-change-me"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/google/callback"
    frontend_url: str = "http://localhost:3000"
    activity_merge_gap_minutes: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
