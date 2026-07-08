from pathlib import Path

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
