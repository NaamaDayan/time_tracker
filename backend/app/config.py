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
    activitywatch_base_url: str = "http://127.0.0.1:5600"
    activitywatch_poll_enabled: bool = True
    api_key: str = "dev-only-change-me"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/google/callback"
    frontend_url: str = "http://localhost:3001"
    activity_merge_gap_minutes: int = 5
    dawarich_base_url: str = "http://localhost:3000"
    dawarich_api_key: str = ""
    dawarich_sync_enabled: bool = True
    dawarich_sync_hour: int = 2
    location_geofence_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
