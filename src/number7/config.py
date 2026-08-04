from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="N7_", env_file=".env", extra="ignore", validate_assignment=True)

    norgate_base_url: str
    norgate_token: str
    data_dir: Path
    history_start: date = date(2004, 1, 1)
    watchlist: str = "S&P 500 Current & Past"
    extra_symbols: list[str] = ["SPY"]
    heartbeat_url: str | None = None
    alpaca_key_id: str | None = None
    alpaca_secret: str | None = None
    trading_mode: Literal["paper", "live"] = "paper"
    risk_layer_version: str | None = None

    @model_validator(mode="after")
    def _refuse_live_without_risk_layer(self) -> "Settings":
        """Blueprint §8 / spec §3: the portfolio risk layer is deferred, and deferral is
        only safe under an ENFORCED gate. 25 ATR-parity positions imply ~23% annualized
        vol at 0.30 average pairwise correlation, not the ~8% independence would give —
        ATR parity equalizes standalone dollar movement and does nothing about common
        equity risk. Enforced on Settings so no live process can even start; a call-site
        guard could be forgotten.

        Sequencing for capital (spec §3): build the production profile, estimate the
        Monte-Carlo drawdown thresholds, freeze them, RE-RUN the full gauntlet on the
        production profile, and only then set risk_layer_version."""
        if self.trading_mode != "paper" and not (self.risk_layer_version or "").strip():
            raise ValueError(
                f"trading_mode={self.trading_mode!r} requires risk_layer_version to be set; "
                "the portfolio risk layer (vol target, sector caps, loss brakes, liquidity "
                "overlay) is not built yet, so non-paper trading is refused")
        return self

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def current_link(self) -> Path:
        return self.data_dir / "current"


@lru_cache
def get_settings() -> Settings:
    return Settings()
