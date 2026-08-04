from pathlib import Path

import pytest

from number7.config import Settings


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("N7_NORGATE_BASE_URL", "http://vm:8000")
    monkeypatch.setenv("N7_NORGATE_TOKEN", "sekret")
    monkeypatch.setenv("N7_DATA_DIR", str(tmp_path))
    s = Settings(_env_file=None)  # hermetic: ignore the developer's real .env
    assert s.norgate_base_url == "http://vm:8000"
    assert s.norgate_token == "sekret"
    assert s.data_dir == tmp_path
    assert str(s.history_start) == "2004-01-01"
    assert s.watchlist == "S&P 500 Current & Past"
    assert s.extra_symbols == ["SPY"]
    assert s.heartbeat_url is None
    assert isinstance(s.snapshots_dir, Path) and s.snapshots_dir == tmp_path / "snapshots"


def _base(tmp_path, **kw):
    return dict(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path, **kw)


def test_defaults_to_paper(tmp_path):
    assert Settings(**_base(tmp_path)).trading_mode == "paper"


def test_live_without_risk_layer_is_refused(tmp_path):
    with pytest.raises(ValueError, match="risk_layer_version"):
        Settings(**_base(tmp_path, trading_mode="live"))


def test_live_with_risk_layer_is_allowed(tmp_path):
    s = Settings(**_base(tmp_path, trading_mode="live", risk_layer_version="2026-09-a"))
    assert s.risk_layer_version == "2026-09-a"
