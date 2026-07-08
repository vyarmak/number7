from __future__ import annotations

import atexit
from datetime import date

import httpx
from norgate_client import NorgateClient
from pydantic import BaseModel

from number7.config import Settings


class BridgeHealth(BaseModel):
    status: str
    norgatedata_version: str
    db_date: date


def fetch_health(settings: Settings, transport: httpx.BaseTransport | None = None) -> BridgeHealth:
    with httpx.Client(base_url=settings.norgate_base_url, timeout=30.0,
                      transport=transport) as http:
        r = http.get("/health")
        r.raise_for_status()
        return BridgeHealth.model_validate(r.json())


def make_client(settings: Settings, transport: httpx.BaseTransport | None = None) -> NorgateClient:
    http = httpx.Client(base_url=settings.norgate_base_url, timeout=120.0, transport=transport)
    atexit.register(http.close)   # short-lived jobs leak nothing; daemons get cleanup
    return NorgateClient(settings.norgate_base_url, settings.norgate_token, http=http)
