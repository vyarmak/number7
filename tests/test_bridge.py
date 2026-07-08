import httpx
import pytest

from number7.config import Settings
from number7.data.bridge import BridgeHealth, fetch_health, make_client


def _settings(tmp_path) -> Settings:
    return Settings(norgate_base_url="http://vm:8000", norgate_token="t", data_dir=tmp_path)


def test_fetch_health_parses_db_date(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok", "norgatedata_version": "1.0.68",
                                         "db_date": "2026-07-06"})

    transport = httpx.MockTransport(handler)
    h = fetch_health(_settings(tmp_path), transport=transport)
    assert isinstance(h, BridgeHealth)
    assert str(h.db_date) == "2026-07-06"
    assert h.status == "ok"


def test_fetch_health_raises_on_5xx(tmp_path):
    transport = httpx.MockTransport(lambda req: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_health(_settings(tmp_path), transport=transport)


def test_make_client_returns_norgate_client(tmp_path):
    from norgate_client import NorgateClient
    assert isinstance(make_client(_settings(tmp_path)), NorgateClient)
