from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WMS Pilot"
    app_env: str = "development"
    database_url: str = "sqlite:///./wms.db"
    thermal_printer_queue: str = "ATOL_TT42"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
