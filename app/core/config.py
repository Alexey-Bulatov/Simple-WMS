from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Simple WMS"
    app_env: str = "development"
    database_url: str = "sqlite:///./wms.db"
    thermal_printer_queue: str = "ATOL_TT42"
    thermal_printer_host: str = "printer.local"
    thermal_printer_port: int = 9100
    auth_enforcement_enabled: bool = False
    auth_bootstrap_token: str | None = None
    auth_session_hours: int = 12
    auth_lock_threshold: int = 5
    auth_lock_minutes: int = 15
    auth_cookie_secure: bool = False
    auth_cookie_name: str = "wms_session"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
