from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="N7_", env_file=".env", extra="ignore")

    norgate_base_url: str
    norgate_token: str
    data_dir: Path
    history_start: date = date(2004, 1, 1)
    watchlist: str = "S&P 500 Current & Past"
    extra_symbols: list[str] = ["SPY"]
    heartbeat_url: str | None = None
    alpaca_key_id: str | None = None
    alpaca_secret: str | None = None

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def current_link(self) -> Path:
        return self.data_dir / "current"


@lru_cache
def get_settings() -> Settings:
    return Settings()
