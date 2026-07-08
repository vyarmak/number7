# Phase 0 — Data Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nightly, QC-gated, versioned Parquet/DuckDB snapshots of Norgate EOD data (prices, S&P 500 point-in-time membership, symbol metadata) pulled from the `norgate-service` REST bridge, with delisting/total-return audit and dead-man monitoring.

**Architecture:** A sync job pulls the "S&P 500 Current & Past" universe + SPY from the bridge into an immutable snapshot directory keyed by the bridge's `db_date`; a QC suite validates the snapshot; only passing snapshots get the `current` symlink; DuckDB provides a query catalog over `current`. Snapshots are versioned because Norgate back-adjusts history (blueprint §9, §14) — every research run pins a snapshot id.

**Tech Stack:** Python 3.12, uv, pandas, pyarrow, duckdb, httpx, pydantic v2 + pydantic-settings, exchange-calendars, pytest, ruff. Reuses `norgate_client.NorgateClient` from the private `norgate-service` repo (git dependency; its README confirms `norgatedata` is platform-gated to Windows, so macOS/Linux installs are clean).

## Global Constraints

- Python `>=3.12`; project managed by `uv`; all commands below run from repo root `number7/`.
- All source under `src/number7/`; tests under `tests/`; import root is `number7`.
- Type hints on every public function; pydantic v2 models for structured data.
- All timestamps/dates are **America/New_York sessions**; trading calendar = `exchange_calendars.get_calendar("XNYS")`.
- Tests never touch the network: bridge calls are faked via `httpx.MockTransport` or a `FakeNorgateClient`. Tests marked `@pytest.mark.vm` are the only exception (live-bridge audit; excluded by default via `-m "not vm"`).
- Snapshots are **immutable once written**: the sync job writes to `data/snapshots/<db_date>/`, never mutates an existing snapshot, and `data/current` is a symlink updated only after QC passes.
- Wire format from the bridge is Parquet (per contract §1.7); on-disk format is Parquet; canonical price columns exactly: `symbol, date, open, high, low, close, volume, unadjusted_close` (contract §1.3; `close` is TOTALRETURN-adjusted).
- Universe: watchlist `"S&P 500 Current & Past"` plus `SPY`; history start `2004-01-01` (contract §5), configurable.
- Conventional-commit messages; one commit per task minimum.

## File Structure

```
number7/
├── pyproject.toml                     # Task 1
├── .env.example                       # Task 1
├── src/number7/
│   ├── __init__.py                    # Task 1
│   ├── config.py                      # Task 1 — Settings (env-driven)
│   ├── data/
│   │   ├── __init__.py                # Task 1
│   │   ├── bridge.py                  # Task 2 — bridge health/db_date + client factory
│   │   ├── snapshot.py                # Task 3 — snapshot layout, meta, promotion
│   │   ├── sync.py                    # Task 4 — pull universe → snapshot
│   │   ├── universe.py                # Task 5 — membership intervals → as-of queries
│   │   ├── store.py                   # Task 6 — DuckDB catalog + price-panel loader
│   │   ├── qc.py                      # Task 7 — QC suite (gates promotion)
│   │   └── audit.py                   # Task 8 — delisting/total-return audit (vm-marked)
│   └── ops/
│       ├── __init__.py                # Task 9
│       ├── nightly.py                 # Task 9 — sync→QC→promote→prune→heartbeat
│       └── prune.py                   # Task 9 — retention policy
├── ops/
│   ├── com.number7.nightly.plist      # Task 10 — launchd (Mac, research spine)
│   └── number7-nightly.{service,timer}# Task 10 — systemd (VPS, later reuse)
└── tests/
    ├── conftest.py                    # Task 3 — shared fixtures (fake snapshot builder)
    ├── test_config.py                 # Task 1
    ├── test_bridge.py                 # Task 2
    ├── test_snapshot.py               # Task 3
    ├── test_sync.py                   # Task 4
    ├── test_universe.py               # Task 5
    ├── test_store.py                  # Task 6
    ├── test_qc.py                     # Task 7
    ├── test_audit_vm.py               # Task 8 (marked vm)
    ├── test_nightly.py                # Task 9
    └── test_prune.py                  # Task 9
```

---

### Task 1: Repo scaffold + configuration

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/number7/__init__.py`, `src/number7/data/__init__.py`, `src/number7/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `number7.config.Settings` with fields `norgate_base_url: str`, `norgate_token: str`, `data_dir: Path`, `history_start: date` (default `2004-01-01`), `watchlist: str` (default `"S&P 500 Current & Past"`), `extra_symbols: list[str]` (default `["SPY"]`), `heartbeat_url: str | None`; and `get_settings() -> Settings` (cached).

- [ ] **Step 1: Initialize project**

```bash
cd /Users/vyarmak/Developer/projects/ai/trading/number7
uv init --name number7 --package --python 3.12
uv add pandas pyarrow duckdb httpx "pydantic>=2" pydantic-settings exchange-calendars
uv add "norgate-service @ git+ssh://git@github.com/vyarmak/norgate-service.git"
uv add --dev pytest ruff
```

Expected: `pyproject.toml` created, `uv.lock` resolves (norgate-service installs without `norgatedata` on macOS — its platform marker guarantees this).

- [ ] **Step 2: Add pytest/ruff config to `pyproject.toml`** (append)

```toml
[tool.pytest.ini_options]
addopts = "-m 'not vm'"
markers = ["vm: requires the live Norgate bridge (run manually)"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 3: Write the failing test** — `tests/test_config.py`

```python
from pathlib import Path

from number7.config import Settings


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("N7_NORGATE_BASE_URL", "http://vm:8000")
    monkeypatch.setenv("N7_NORGATE_TOKEN", "sekret")
    monkeypatch.setenv("N7_DATA_DIR", str(tmp_path))
    s = Settings()
    assert s.norgate_base_url == "http://vm:8000"
    assert s.norgate_token == "sekret"
    assert s.data_dir == tmp_path
    assert str(s.history_start) == "2004-01-01"
    assert s.watchlist == "S&P 500 Current & Past"
    assert s.extra_symbols == ["SPY"]
    assert s.heartbeat_url is None
    assert isinstance(s.snapshots_dir, Path) and s.snapshots_dir == tmp_path / "snapshots"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'number7.config'`

- [ ] **Step 5: Implement** — `src/number7/config.py`

```python
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

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def current_link(self) -> Path:
        return self.data_dir / "current"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Also create `.env.example`:

```bash
N7_NORGATE_BASE_URL=http://<vm-tailscale-ip>:8000
N7_NORGATE_TOKEN=change-me
N7_DATA_DIR=/Users/vyarmak/Developer/projects/ai/trading/number7/data
# N7_HEARTBEAT_URL=https://hc-ping.com/<uuid>
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .env.example src/number7 tests/test_config.py
git commit -m "feat(phase0): project scaffold and env-driven settings"
```

---

### Task 2: Bridge health + client factory

**Files:**
- Create: `src/number7/data/bridge.py`
- Test: `tests/test_bridge.py`

**Interfaces:**
- Consumes: `Settings` (Task 1); `norgate_client.NorgateClient` (external).
- Produces: `BridgeHealth` (pydantic: `status: str`, `norgatedata_version: str`, `db_date: date`); `fetch_health(settings) -> BridgeHealth` (GET `/health`, no auth — service contract); `make_client(settings) -> NorgateClient`.

- [ ] **Step 1: Write the failing test** — `tests/test_bridge.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bridge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'number7.data.bridge'`

- [ ] **Step 3: Implement** — `src/number7/data/bridge.py`

```python
from __future__ import annotations

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
    return NorgateClient(settings.norgate_base_url, settings.norgate_token, http=http)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bridge.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/number7/data/bridge.py tests/test_bridge.py
git commit -m "feat(phase0): bridge health check and NorgateClient factory"
```

---

### Task 3: Snapshot layout, meta, promotion

**Files:**
- Create: `src/number7/data/snapshot.py`, `tests/conftest.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Produces:
  - `SnapshotMeta` (pydantic): `db_date: date`, `created_at: datetime`, `history_start: date`, `watchlist: str`, `n_symbols: int`, `n_price_rows: int`, `file_sha256: dict[str, str]`.
  - `SnapshotPaths` (dataclass over root `Path`): properties `prices` (`prices.parquet`), `membership` (`membership.parquet`), `metadata` (`metadata.parquet`), `meta` (`meta.json`), `qc_report` (`qc_report.json`).
  - `snapshot_dir(settings, db_date) -> Path`; `write_meta(paths, meta)`; `read_meta(paths) -> SnapshotMeta`; `promote(settings, db_date)` (atomically points `data/current` at the snapshot); `current_snapshot(settings) -> Path | None`.
- Test fixture produced for later tasks (`tests/conftest.py`): `fake_snapshot(tmp_path) -> Path` building a tiny 3-symbol snapshot (AAPL, ATVI, SPY; 2026-06-29→2026-07-02 sessions; ATVI membership ends 2026-06-30 and its prices stop then — a mini delisting).

- [ ] **Step 1: Write shared fixture** — `tests/conftest.py`

```python
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from number7.data.snapshot import SnapshotMeta, SnapshotPaths

SESSIONS = [date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)]


def _bars(symbol: str, days: list[date], px: float) -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": symbol,
        "date": pd.to_datetime(days),
        "open": px, "high": px * 1.01, "low": px * 0.99, "close": px,
        "volume": 1_000_000, "unadjusted_close": px,
    })


@pytest.fixture
def fake_snapshot(tmp_path: Path) -> Path:
    root = tmp_path / "snapshots" / "2026-07-02"
    root.mkdir(parents=True)
    p = SnapshotPaths(root)
    prices = pd.concat([
        _bars("AAPL", SESSIONS, 200.0),
        _bars("ATVI", SESSIONS[:2], 95.0),          # stops trading 2026-06-30
        _bars("SPY", SESSIONS, 550.0),
    ], ignore_index=True)
    prices.to_parquet(p.prices, index=False)
    pd.DataFrame([
        {"symbol": "AAPL", "assetid": 1, "start": "2004-01-01", "end": None},
        {"symbol": "ATVI", "assetid": 2, "start": "2015-08-31", "end": "2026-06-30"},
    ]).to_parquet(p.membership, index=False)
    pd.DataFrame([
        {"symbol": "AAPL", "assetid": 1, "security_name": "Apple", "gics_sector": "Information Technology",
         "first_quoted_date": "1980-12-12", "last_quoted_date": None, "status": "active",
         "delisting_reason": None},
        {"symbol": "ATVI", "assetid": 2, "security_name": "Activision", "gics_sector": "Communication Services",
         "first_quoted_date": "1993-10-25", "last_quoted_date": "2026-06-30", "status": "delisted",
         "delisting_reason": "acquisition"},
        {"symbol": "SPY", "assetid": 3, "security_name": "SPDR S&P 500", "gics_sector": None,
         "first_quoted_date": "1993-01-29", "last_quoted_date": None, "status": "active",
         "delisting_reason": None},
    ]).to_parquet(p.metadata, index=False)
    meta = SnapshotMeta(db_date=date(2026, 7, 2), created_at=datetime.now(timezone.utc),
                        history_start=date(2004, 1, 1), watchlist="S&P 500 Current & Past",
                        n_symbols=3, n_price_rows=len(prices), file_sha256={})
    p.meta.write_text(meta.model_dump_json(indent=2))
    return root
```

- [ ] **Step 2: Write the failing test** — `tests/test_snapshot.py`

```python
from datetime import date, datetime, timezone

from number7.config import Settings
from number7.data.snapshot import (SnapshotMeta, SnapshotPaths, current_snapshot,
                                   promote, read_meta, snapshot_dir, write_meta)


def _settings(tmp_path):
    return Settings(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path)


def test_snapshot_paths_layout(tmp_path):
    p = SnapshotPaths(tmp_path)
    assert p.prices.name == "prices.parquet"
    assert p.membership.name == "membership.parquet"
    assert p.metadata.name == "metadata.parquet"
    assert p.meta.name == "meta.json"
    assert p.qc_report.name == "qc_report.json"


def test_meta_roundtrip(tmp_path):
    p = SnapshotPaths(tmp_path)
    meta = SnapshotMeta(db_date=date(2026, 7, 2), created_at=datetime.now(timezone.utc),
                        history_start=date(2004, 1, 1), watchlist="W", n_symbols=3,
                        n_price_rows=10, file_sha256={"prices.parquet": "ab"})
    write_meta(p, meta)
    assert read_meta(p).db_date == date(2026, 7, 2)


def test_promote_and_current(tmp_path, fake_snapshot):
    s = _settings(tmp_path)
    assert current_snapshot(s) is None
    promote(s, date(2026, 7, 2))
    cur = current_snapshot(s)
    assert cur is not None and cur.resolve() == fake_snapshot.resolve()
    # re-promotion is atomic + idempotent
    promote(s, date(2026, 7, 2))
    assert current_snapshot(s).resolve() == fake_snapshot.resolve()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_snapshot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'number7.data.snapshot'`

- [ ] **Step 4: Implement** — `src/number7/data/snapshot.py`

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from number7.config import Settings


class SnapshotMeta(BaseModel):
    db_date: date
    created_at: datetime
    history_start: date
    watchlist: str
    n_symbols: int
    n_price_rows: int
    file_sha256: dict[str, str]


@dataclass(frozen=True)
class SnapshotPaths:
    root: Path

    @property
    def prices(self) -> Path: return self.root / "prices.parquet"
    @property
    def membership(self) -> Path: return self.root / "membership.parquet"
    @property
    def metadata(self) -> Path: return self.root / "metadata.parquet"
    @property
    def meta(self) -> Path: return self.root / "meta.json"
    @property
    def qc_report(self) -> Path: return self.root / "qc_report.json"


def snapshot_dir(settings: Settings, db_date: date) -> Path:
    return settings.snapshots_dir / db_date.isoformat()


def write_meta(paths: SnapshotPaths, meta: SnapshotMeta) -> None:
    paths.meta.write_text(meta.model_dump_json(indent=2))


def read_meta(paths: SnapshotPaths) -> SnapshotMeta:
    return SnapshotMeta.model_validate_json(paths.meta.read_text())


def promote(settings: Settings, db_date: date) -> None:
    """Atomically point data/current at the snapshot (symlink swap via rename)."""
    target = snapshot_dir(settings, db_date)
    if not target.is_dir():
        raise FileNotFoundError(f"snapshot missing: {target}")
    link, tmp = settings.current_link, settings.current_link.with_name("current.tmp")
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target, target_is_directory=True)
    os.replace(tmp, link)


def current_snapshot(settings: Settings) -> Path | None:
    link = settings.current_link
    return link.resolve() if link.is_symlink() or link.exists() else None
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/test_snapshot.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add src/number7/data/snapshot.py tests/conftest.py tests/test_snapshot.py
git commit -m "feat(phase0): immutable snapshot layout, meta, atomic promotion"
```

---

### Task 4: Sync job — bridge → snapshot

**Files:**
- Create: `src/number7/data/sync.py`
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `make_client`/`fetch_health` (Task 2), `SnapshotPaths`/`SnapshotMeta`/`write_meta`/`snapshot_dir` (Task 3).
- Produces: `run_sync(settings, client=None, health=None) -> Path` — builds the snapshot for `health.db_date` and returns its root. Raises `SnapshotExistsError` if the snapshot already exists **with a meta.json** (immutability); a partial dir without meta is resumed/overwritten. Membership JSON (client `sp500_membership_intervals()`) is flattened to one row per interval: columns `symbol, assetid, start, end` (end nullable).

- [ ] **Step 1: Write the failing test** — `tests/test_sync.py`

```python
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from number7.config import Settings
from number7.data.bridge import BridgeHealth
from number7.data.snapshot import SnapshotPaths, read_meta
from number7.data.sync import SnapshotExistsError, run_sync

SESSIONS = pd.to_datetime(["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"])


class FakeClient:
    def watchlist_symbols(self, name):
        assert name == "S&P 500 Current & Past"
        return ["AAPL", "ATVI"]

    def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
        assert adjustment == "totalreturn"
        days = SESSIONS if symbol != "ATVI" else SESSIONS[:2]
        return pd.DataFrame({"date": days, "open": 1.0, "high": 1.1, "low": 0.9,
                             "close": 1.0, "volume": 100, "unadjusted_close": 1.0})

    def sp500_membership_intervals(self):
        return [
            {"symbol": "AAPL", "assetid": 1, "intervals": [{"start": "2004-01-01", "end": None}]},
            {"symbol": "ATVI", "assetid": 2,
             "intervals": [{"start": "2015-08-31", "end": "2026-06-30"}]},
        ]

    def metadata_batch(self, symbols):
        return {s: {"assetid": i + 1, "security_name": s, "gics_sector": "X",
                    "first_quoted_date": "1990-01-01", "last_quoted_date": None,
                    "status": "active", "domicile": "US", "delisting_reason": None}
                for i, s in enumerate(symbols)}


def _settings(tmp_path):
    return Settings(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path)


def _health():
    return BridgeHealth(status="ok", norgatedata_version="1", db_date=date(2026, 7, 2))


def test_run_sync_builds_snapshot(tmp_path):
    root = run_sync(_settings(tmp_path), client=FakeClient(), health=_health())
    p = SnapshotPaths(root)
    prices = pd.read_parquet(p.prices)
    assert set(prices["symbol"].unique()) == {"AAPL", "ATVI", "SPY"}   # SPY from extra_symbols
    assert list(prices.columns) == ["symbol", "date", "open", "high", "low", "close",
                                    "volume", "unadjusted_close"]
    membership = pd.read_parquet(p.membership)
    assert membership.loc[membership.symbol == "ATVI", "end"].iloc[0] == "2026-06-30"
    meta = read_meta(p)
    assert meta.db_date == date(2026, 7, 2)
    assert meta.n_symbols == 3
    assert set(meta.file_sha256) == {"prices.parquet", "membership.parquet", "metadata.parquet"}


def test_run_sync_refuses_finished_snapshot(tmp_path):
    s = _settings(tmp_path)
    run_sync(s, client=FakeClient(), health=_health())
    with pytest.raises(SnapshotExistsError):
        run_sync(s, client=FakeClient(), health=_health())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'number7.data.sync'`

- [ ] **Step 3: Implement** — `src/number7/data/sync.py`

```python
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from number7.config import Settings
from number7.data.bridge import BridgeHealth, fetch_health, make_client
from number7.data.snapshot import SnapshotMeta, SnapshotPaths, snapshot_dir, write_meta

PRICE_COLS = ["symbol", "date", "open", "high", "low", "close", "volume", "unadjusted_close"]


class SnapshotExistsError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pull_prices(client, symbols: list[str], start: str) -> pd.DataFrame:
    frames = []
    for sym in symbols:
        df = client.price_timeseries(sym, start=start, adjustment="totalreturn")
        if df.empty:
            continue
        df = df.copy()
        df["symbol"] = sym
        frames.append(df[PRICE_COLS])
    return pd.concat(frames, ignore_index=True)


def _flatten_membership(raw: list[dict]) -> pd.DataFrame:
    rows = [{"symbol": e["symbol"], "assetid": e["assetid"],
             "start": iv["start"], "end": iv["end"]}
            for e in raw for iv in e["intervals"]]
    return pd.DataFrame(rows, columns=["symbol", "assetid", "start", "end"])


def run_sync(settings: Settings, client=None, health: BridgeHealth | None = None) -> Path:
    health = health or fetch_health(settings)
    client = client or make_client(settings)

    root = snapshot_dir(settings, health.db_date)
    paths = SnapshotPaths(root)
    if paths.meta.exists():
        raise SnapshotExistsError(f"snapshot {health.db_date} already finalized")
    root.mkdir(parents=True, exist_ok=True)

    symbols = sorted(set(client.watchlist_symbols(settings.watchlist)) | set(settings.extra_symbols))
    prices = _pull_prices(client, symbols, start=settings.history_start.isoformat())
    prices.to_parquet(paths.prices, index=False)

    _flatten_membership(client.sp500_membership_intervals()).to_parquet(paths.membership, index=False)

    meta_rows = client.metadata_batch(symbols)
    pd.DataFrame([{"symbol": s, **(m or {})} for s, m in meta_rows.items()]) \
        .to_parquet(paths.metadata, index=False)

    write_meta(paths, SnapshotMeta(
        db_date=health.db_date, created_at=datetime.now(timezone.utc),
        history_start=settings.history_start, watchlist=settings.watchlist,
        n_symbols=len(symbols), n_price_rows=len(prices),
        file_sha256={p.name: _sha256(p) for p in (paths.prices, paths.membership, paths.metadata)},
    ))
    return root
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sync.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/number7/data/sync.py tests/test_sync.py
git commit -m "feat(phase0): sync job builds immutable snapshot from bridge"
```

---

### Task 5: Universe — point-in-time membership queries

**Files:**
- Create: `src/number7/data/universe.py`
- Test: `tests/test_universe.py`

**Interfaces:**
- Consumes: `SnapshotPaths` (Task 3); membership parquet schema (Task 4).
- Produces: `load_membership(snapshot_root) -> pd.DataFrame` (parsed dates, `end` NaT = open); `members_asof(membership_df, d: date) -> set[str]` (interval `end` **inclusive** — contract §2.3); `member_union(membership_df, start, end) -> set[str]`; `in_index_flags(membership_df, symbols, sessions) -> pd.DataFrame` (bool matrix sessions×symbols — the tradability mask; blueprint Gate 1).

- [ ] **Step 1: Write the failing test** — `tests/test_universe.py`

```python
from datetime import date

import pandas as pd

from number7.data.universe import in_index_flags, load_membership, member_union, members_asof


def test_membership_asof_and_union(fake_snapshot):
    m = load_membership(fake_snapshot)
    assert members_asof(m, date(2026, 6, 30)) == {"AAPL", "ATVI"}   # end inclusive
    assert members_asof(m, date(2026, 7, 1)) == {"AAPL"}            # ATVI out next day
    assert member_union(m, date(2026, 6, 1), date(2026, 7, 2)) == {"AAPL", "ATVI"}


def test_multiple_stints():
    m = pd.DataFrame({
        "symbol": ["X", "X"], "assetid": [1, 1],
        "start": pd.to_datetime(["1991-07-01", "2000-01-01"]),
        "end": pd.to_datetime(["1995-01-01", pd.NaT]),
    })
    assert members_asof(m, date(1993, 1, 1)) == {"X"}
    assert members_asof(m, date(1997, 1, 1)) == set()
    assert members_asof(m, date(2026, 1, 1)) == {"X"}


def test_in_index_flags(fake_snapshot):
    m = load_membership(fake_snapshot)
    sessions = pd.to_datetime(["2026-06-30", "2026-07-01"])
    flags = in_index_flags(m, ["AAPL", "ATVI"], sessions)
    assert flags.loc[sessions[0], "ATVI"] and not flags.loc[sessions[1], "ATVI"]
    assert flags["AAPL"].all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_universe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'number7.data.universe'`

- [ ] **Step 3: Implement** — `src/number7/data/universe.py`

```python
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from number7.data.snapshot import SnapshotPaths


def load_membership(snapshot_root: Path) -> pd.DataFrame:
    df = pd.read_parquet(SnapshotPaths(snapshot_root).membership)
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])  # None -> NaT (open interval)
    return df


def _covering(m: pd.DataFrame, ts: pd.Timestamp) -> pd.Series:
    return (m["start"] <= ts) & (m["end"].isna() | (ts <= m["end"]))  # end inclusive


def members_asof(membership: pd.DataFrame, d: date) -> set[str]:
    ts = pd.Timestamp(d)
    return set(membership.loc[_covering(membership, ts), "symbol"])


def member_union(membership: pd.DataFrame, start: date, end: date) -> set[str]:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    overlap = (membership["start"] <= e) & (membership["end"].isna() | (membership["end"] >= s))
    return set(membership.loc[overlap, "symbol"])


def in_index_flags(membership: pd.DataFrame, symbols: list[str],
                   sessions: pd.DatetimeIndex) -> pd.DataFrame:
    out = pd.DataFrame(False, index=sessions, columns=list(symbols))
    for _, row in membership.iterrows():
        if row["symbol"] not in out.columns:
            continue
        end = row["end"] if pd.notna(row["end"]) else sessions[-1]
        mask = (sessions >= row["start"]) & (sessions <= end)
        out.loc[mask, row["symbol"]] = True
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_universe.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/number7/data/universe.py tests/test_universe.py
git commit -m "feat(phase0): point-in-time membership queries and tradability mask"
```

---

### Task 6: DuckDB store + price-panel loader

**Files:**
- Create: `src/number7/data/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `SnapshotPaths` (Task 3).
- Produces (the API Phase 1's engine consumes — signatures are load-bearing):
  - `load_price_panel(snapshot_root, symbols=None, start=None, end=None) -> pd.DataFrame` — tidy long frame, columns exactly `PRICE_COLS`, sorted by `(symbol, date)`.
  - `close_matrix(panel) -> pd.DataFrame` — pivot: index=date (DatetimeIndex, ascending), columns=symbol, values=close.
  - `connect_catalog(snapshot_root) -> duckdb.DuckDBPyConnection` — in-memory DuckDB with views `prices`, `membership`, `metadata` over the snapshot parquets (ad-hoc SQL for QC/analysis).

- [ ] **Step 1: Write the failing test** — `tests/test_store.py`

```python
import pandas as pd

from number7.data.store import close_matrix, connect_catalog, load_price_panel


def test_load_price_panel_filters(fake_snapshot):
    panel = load_price_panel(fake_snapshot, symbols=["AAPL"], start="2026-06-30")
    assert set(panel["symbol"]) == {"AAPL"}
    assert panel["date"].min() == pd.Timestamp("2026-06-30")
    assert list(panel.columns) == ["symbol", "date", "open", "high", "low", "close",
                                   "volume", "unadjusted_close"]


def test_close_matrix_shape(fake_snapshot):
    m = close_matrix(load_price_panel(fake_snapshot))
    assert list(m.columns) == ["AAPL", "ATVI", "SPY"]
    assert m.index.is_monotonic_increasing
    assert pd.isna(m.loc["2026-07-01", "ATVI"])   # delisted names go NaN, not padded


def test_catalog_sql(fake_snapshot):
    con = connect_catalog(fake_snapshot)
    n = con.sql("select count(*) from prices where symbol='SPY'").fetchone()[0]
    assert n == 4
    assert con.sql("select count(*) from membership").fetchone()[0] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'number7.data.store'`

- [ ] **Step 3: Implement** — `src/number7/data/store.py`

```python
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from number7.data.snapshot import SnapshotPaths

PRICE_COLS = ["symbol", "date", "open", "high", "low", "close", "volume", "unadjusted_close"]


def load_price_panel(snapshot_root: Path, symbols: list[str] | None = None,
                     start: str | None = None, end: str | None = None) -> pd.DataFrame:
    df = pd.read_parquet(SnapshotPaths(snapshot_root).prices)
    df["date"] = pd.to_datetime(df["date"])
    if symbols is not None:
        df = df[df["symbol"].isin(symbols)]
    if start is not None:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["date"] <= pd.Timestamp(end)]
    return df.sort_values(["symbol", "date"], ignore_index=True)[PRICE_COLS]


def close_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.pivot(index="date", columns="symbol", values="close").sort_index()


def connect_catalog(snapshot_root: Path) -> duckdb.DuckDBPyConnection:
    p = SnapshotPaths(snapshot_root)
    con = duckdb.connect()
    con.sql(f"create view prices as select * from read_parquet('{p.prices}')")
    con.sql(f"create view membership as select * from read_parquet('{p.membership}')")
    con.sql(f"create view metadata as select * from read_parquet('{p.metadata}')")
    return con
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/number7/data/store.py tests/test_store.py
git commit -m "feat(phase0): duckdb catalog and price-panel loaders"
```

---

### Task 7: QC suite (gates promotion)

**Files:**
- Create: `src/number7/data/qc.py`
- Test: `tests/test_qc.py`

**Interfaces:**
- Consumes: snapshot files (Tasks 3–4), `load_membership` (Task 5), `load_price_panel` (Task 6).
- Produces: `QCIssue` (pydantic: `check: str`, `severity: Literal["error","warn"]`, `detail: str`); `run_qc(snapshot_root, expected_db_date: date | None = None) -> list[QCIssue]`; `qc_passes(issues) -> bool` (no `error`-severity issues); `write_qc_report(snapshot_root, issues)` (JSON to `qc_report.json`).
- Checks (blueprint §9 QC + KB-10/11 + contract):
  1. `schema` (error): price columns == `PRICE_COLS`; membership columns == `symbol,assetid,start,end`.
  2. `ohlc_sanity` (error): `low <= min(open, close)`, `high >= max(open, close)`, `low <= high`, all prices > 0.
  3. `calendar_gaps` (error): for each of SPY + 20 largest symbols by row count, interior missing XNYS sessions between the symbol's own first/last bar (delisting truncation is fine; interior holes are not — contract §1.5 forbids padding, so holes mean data loss).
  4. `outliers` (warn): |daily log return| > 4σ (per symbol, full-sample σ) **and** same-day |SPY log return| < 1% → flag for review (bad-tick suspicion, KB-07: bad ticks inflate MR).
  5. `membership_overlap` (error): overlapping intervals for the same `assetid`.
  6. `membership_orphans` (error): membership symbols with zero price rows.
  7. `freshness` (error, only when `expected_db_date` given): `meta.db_date == expected_db_date`.
  8. `row_floor` (error): ≥ 500_000 price rows when history spans ≥ 15 years (guards against silently truncated pulls; skipped for small test snapshots by the year-span condition).

- [ ] **Step 1: Write the failing test** — `tests/test_qc.py`

```python
from datetime import date

import pandas as pd

from number7.data.qc import qc_passes, run_qc, write_qc_report
from number7.data.snapshot import SnapshotPaths


def test_clean_snapshot_passes(fake_snapshot):
    issues = run_qc(fake_snapshot, expected_db_date=date(2026, 7, 2))
    assert qc_passes(issues), [i.model_dump() for i in issues]


def test_ohlc_violation_fails(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    df.loc[0, "low"] = df.loc[0, "high"] + 1        # corrupt one bar
    df.to_parquet(p.prices, index=False)
    issues = run_qc(fake_snapshot)
    assert not qc_passes(issues)
    assert any(i.check == "ohlc_sanity" for i in issues)


def test_stale_db_date_fails(fake_snapshot):
    issues = run_qc(fake_snapshot, expected_db_date=date(2026, 7, 3))
    assert any(i.check == "freshness" and i.severity == "error" for i in issues)


def test_membership_orphan_fails(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    m = pd.read_parquet(p.membership)
    m.loc[len(m)] = {"symbol": "GHOST", "assetid": 99, "start": "2020-01-01", "end": None}
    m.to_parquet(p.membership, index=False)
    issues = run_qc(fake_snapshot)
    assert any(i.check == "membership_orphans" for i in issues)


def test_report_written(fake_snapshot):
    issues = run_qc(fake_snapshot)
    write_qc_report(fake_snapshot, issues)
    assert SnapshotPaths(fake_snapshot).qc_report.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_qc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'number7.data.qc'`

- [ ] **Step 3: Implement** — `src/number7/data/qc.py`

```python
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from pydantic import BaseModel

from number7.data.snapshot import SnapshotPaths, read_meta
from number7.data.store import PRICE_COLS, load_price_panel
from number7.data.universe import load_membership


class QCIssue(BaseModel):
    check: str
    severity: Literal["error", "warn"]
    detail: str


def _err(check: str, detail: str) -> QCIssue:
    return QCIssue(check=check, severity="error", detail=detail)


def _warn(check: str, detail: str) -> QCIssue:
    return QCIssue(check=check, severity="warn", detail=detail)


def run_qc(snapshot_root: Path, expected_db_date: date | None = None) -> list[QCIssue]:
    paths = SnapshotPaths(snapshot_root)
    issues: list[QCIssue] = []
    prices = load_price_panel(snapshot_root)
    membership = load_membership(snapshot_root)

    # 1. schema
    if list(prices.columns) != PRICE_COLS:
        issues.append(_err("schema", f"price columns {list(prices.columns)}"))
    if list(membership.columns) != ["symbol", "assetid", "start", "end"]:
        issues.append(_err("schema", f"membership columns {list(membership.columns)}"))

    # 2. ohlc sanity
    bad = prices[(prices["low"] > prices[["open", "close"]].min(axis=1))
                 | (prices["high"] < prices[["open", "close"]].max(axis=1))
                 | (prices["low"] > prices["high"])
                 | (prices[["open", "high", "low", "close"]] <= 0).any(axis=1)]
    if len(bad):
        issues.append(_err("ohlc_sanity", f"{len(bad)} bad bars, first: "
                           f"{bad.iloc[0]['symbol']} {bad.iloc[0]['date'].date()}"))

    # 3. interior calendar gaps (SPY + 20 biggest symbols)
    cal = xcals.get_calendar("XNYS")
    counts = prices.groupby("symbol").size().sort_values(ascending=False)
    check_syms = list(dict.fromkeys(["SPY", *counts.head(20).index]))
    for sym in check_syms:
        g = prices[prices["symbol"] == sym]
        if g.empty:
            continue
        expected = cal.sessions_in_range(g["date"].min(), g["date"].max())
        missing = expected.difference(pd.DatetimeIndex(g["date"]))
        if len(missing):
            issues.append(_err("calendar_gaps", f"{sym}: {len(missing)} interior sessions missing "
                               f"(first {missing[0].date()})"))

    # 4. outlier returns without an index move
    close = prices.pivot(index="date", columns="symbol", values="close").sort_index()
    rets = np.log(close).diff()
    if "SPY" in rets.columns:
        spy_calm = rets["SPY"].abs() < 0.01
        z = (rets - rets.mean()) / rets.std(ddof=0)
        flagged = (z.abs() > 4) & spy_calm.to_numpy()[:, None]
        n = int(flagged.to_numpy(na_value=False).sum())
        if n:
            issues.append(_warn("outliers", f"{n} >4-sigma returns on calm-SPY days"))

    # 5. overlapping intervals per assetid
    for aid, g in membership.sort_values("start").groupby("assetid"):
        prev_end = None
        for _, row in g.iterrows():
            if prev_end is not None and pd.notna(prev_end) and row["start"] <= prev_end:
                issues.append(_err("membership_overlap", f"assetid {aid}"))
                break
            prev_end = row["end"]

    # 6. membership symbols without prices
    orphans = set(membership["symbol"]) - set(prices["symbol"])
    if orphans:
        issues.append(_err("membership_orphans", f"{sorted(orphans)[:5]}"))

    # 7. freshness
    if expected_db_date is not None:
        meta = read_meta(paths)
        if meta.db_date != expected_db_date:
            issues.append(_err("freshness", f"db_date {meta.db_date} != expected {expected_db_date}"))

    # 8. row floor for full-history pulls
    span_years = (prices["date"].max() - prices["date"].min()).days / 365.25
    if span_years >= 15 and len(prices) < 500_000:
        issues.append(_err("row_floor", f"only {len(prices)} rows over {span_years:.1f}y"))

    return issues


def qc_passes(issues: list[QCIssue]) -> bool:
    return not any(i.severity == "error" for i in issues)


def write_qc_report(snapshot_root: Path, issues: list[QCIssue]) -> None:
    SnapshotPaths(snapshot_root).qc_report.write_text(
        json.dumps([i.model_dump() for i in issues], indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_qc.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/number7/data/qc.py tests/test_qc.py
git commit -m "feat(phase0): QC suite gating snapshot promotion"
```

---

### Task 8: Delisting / total-return audit (live-bridge, vm-marked)

The blueprint's Phase-0 mandate: *verify Norgate's survivorship/delisting/total-return handling, don't assume it* (§9; the KB never audits Norgate). These tests run against the **real bridge** on demand: `uv run pytest -m vm`.

**Files:**
- Create: `src/number7/data/audit.py`
- Test: `tests/test_audit_vm.py`

**Interfaces:**
- Consumes: `make_client`, `fetch_health` (Task 2), `get_settings` (Task 1).
- Produces: `audit_report(client) -> dict` returning per-case booleans (also runnable via `uv run python -m number7.data.audit`).

- [ ] **Step 1: Write the audit checks** — `src/number7/data/audit.py`

```python
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from number7.config import get_settings
from number7.data.bridge import make_client

# Known-answer fixtures (public corporate-action record):
SPLITS = [("AAPL", "2020-08-31", 4.0), ("NVDA", "2024-06-10", 10.0)]
DELISTED = ["ATVI", "TWTR", "SIVB"]           # acquisition, acquisition, failure
DIVIDEND_PAYER = "KO"


def _split_continuity(client, symbol: str, ex_date: str) -> bool:
    """Adjusted close must NOT jump ~1/ratio across the split ex-date."""
    df = client.price_timeseries(symbol, start=None, end=None)
    df = df.set_index(pd.to_datetime(df["date"]))
    r = np.log(df["close"]).diff().loc[ex_date]
    return bool(abs(r) < 0.20)                 # a missed 4:1 adjustment shows as ~-139% log move


def _delisted_served(client, symbol: str) -> bool:
    df = client.price_timeseries(symbol)
    meta = client.metadata(symbol)
    if df.empty or meta is None or meta["last_quoted_date"] is None:
        return False
    return str(pd.to_datetime(df["date"]).max().date()) == meta["last_quoted_date"]


def _totalreturn_dominates(client, symbol: str) -> bool:
    """Total-return cumulative growth must exceed capital-only for a dividend payer."""
    tr = client.price_timeseries(symbol, start="2010-01-01", adjustment="totalreturn")
    cap = client.price_timeseries(symbol, start="2010-01-01", adjustment="capital")
    g = lambda d: d["close"].iloc[-1] / d["close"].iloc[0]
    return bool(g(tr) > g(cap))


def audit_report(client) -> dict:
    return {
        **{f"split_{s}_{d}": _split_continuity(client, s, d) for s, d, _ in SPLITS},
        **{f"delisted_{s}": _delisted_served(client, s) for s in DELISTED},
        f"totalreturn_{DIVIDEND_PAYER}": _totalreturn_dominates(client, DIVIDEND_PAYER),
    }


if __name__ == "__main__":
    print(json.dumps(audit_report(make_client(get_settings())), indent=2))
```

- [ ] **Step 2: Write the vm-marked test** — `tests/test_audit_vm.py`

```python
import pytest

from number7.config import get_settings
from number7.data.audit import audit_report
from number7.data.bridge import make_client

pytestmark = pytest.mark.vm


def test_norgate_audit_all_green():
    report = audit_report(make_client(get_settings()))
    assert all(report.values()), report
```

- [ ] **Step 3: Verify default runs still exclude vm**

Run: `uv run pytest tests/test_audit_vm.py -v`
Expected: `1 deselected` (marker filter working), exit code 0 or 5.

- [ ] **Step 4: Run live audit once (bridge reachable, .env filled)**

Run: `uv run pytest -m vm -v`
Expected: PASS — if any case fails, STOP and investigate with the vendor docs before Phase 1 (this is the blueprint's Norgate-audit gate).

- [ ] **Step 5: Commit**

```bash
git add src/number7/data/audit.py tests/test_audit_vm.py
git commit -m "feat(phase0): live Norgate delisting/split/total-return audit"
```

---

### Task 9: Nightly orchestrator + retention

**Files:**
- Create: `src/number7/ops/__init__.py`, `src/number7/ops/nightly.py`, `src/number7/ops/prune.py`
- Test: `tests/test_nightly.py`, `tests/test_prune.py`

**Interfaces:**
- Consumes: `run_sync` (Task 4), `run_qc`/`qc_passes`/`write_qc_report` (Task 7), `promote` (Task 3), `fetch_health` (Task 2).
- Produces: `run_nightly(settings, *, sync=run_sync, qc=run_qc, promote_fn=promote, health_fn=fetch_health, ping=_ping) -> NightlyResult` (pydantic: `db_date: date | None`, `synced: bool`, `qc_ok: bool`, `promoted: bool`, `skipped_reason: str | None`); `prune_snapshots(settings, keep_daily=30) -> list[Path]` (deletes snapshot dirs older than `keep_daily` days **except** each ISO-week's first snapshot — weekly kept forever; never deletes the target of `current`).
- Behavior: already-finalized snapshot for today's db_date ⇒ `skipped_reason="exists"`, still QC+promote if not yet promoted; QC failure ⇒ **no promote**, report written, heartbeat **not** pinged (dead-man fires); success ⇒ promote + ping `settings.heartbeat_url` (if set).

- [ ] **Step 1: Write the failing tests** — `tests/test_nightly.py`

```python
from datetime import date

from number7.config import Settings
from number7.data.bridge import BridgeHealth
from number7.data.qc import QCIssue
from number7.ops.nightly import run_nightly


def _settings(tmp_path):
    return Settings(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path,
                    heartbeat_url="http://hc/ping")


def _health():
    return BridgeHealth(status="ok", norgatedata_version="1", db_date=date(2026, 7, 2))


def test_success_path_promotes_and_pings(tmp_path, fake_snapshot):
    pings, promoted = [], []
    r = run_nightly(_settings(tmp_path),
                    sync=lambda s, **kw: fake_snapshot,
                    qc=lambda root, expected_db_date=None: [],
                    promote_fn=lambda s, d: promoted.append(d),
                    health_fn=lambda s: _health(),
                    ping=lambda url: pings.append(url))
    assert r.synced and r.qc_ok and r.promoted
    assert promoted == [date(2026, 7, 2)] and pings == ["http://hc/ping"]


def test_qc_failure_blocks_promotion_and_ping(tmp_path, fake_snapshot):
    pings, promoted = [], []
    bad = [QCIssue(check="ohlc_sanity", severity="error", detail="x")]
    r = run_nightly(_settings(tmp_path),
                    sync=lambda s, **kw: fake_snapshot,
                    qc=lambda root, expected_db_date=None: bad,
                    promote_fn=lambda s, d: promoted.append(d),
                    health_fn=lambda s: _health(),
                    ping=lambda url: pings.append(url))
    assert r.synced and not r.qc_ok and not r.promoted
    assert promoted == [] and pings == []
```

— `tests/test_prune.py`

```python
from datetime import date, timedelta

from number7.config import Settings
from number7.ops.prune import prune_snapshots


def test_prune_keeps_recent_weekly_and_current(tmp_path):
    s = Settings(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path)
    today = date(2026, 7, 2)
    days = [today - timedelta(days=i) for i in range(0, 60)]
    for d in days:
        (s.snapshots_dir / d.isoformat()).mkdir(parents=True)
    (s.snapshots_dir / days[45].isoformat()).mkdir(exist_ok=True)
    s.current_link.symlink_to(s.snapshots_dir / days[45].isoformat())  # current = old snapshot

    deleted = prune_snapshots(s, keep_daily=30, today=today)

    kept = {p.name for p in s.snapshots_dir.iterdir()}
    assert days[0].isoformat() in kept                       # recent kept
    assert days[45].isoformat() in kept                      # current never deleted
    mondays = {d.isoformat() for d in days if d.isoweekday() == 1}
    assert mondays <= kept                                   # weekly anchors kept
    assert all(p.name not in kept for p in deleted)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_nightly.py tests/test_prune.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'number7.ops'`

- [ ] **Step 3: Implement** — `src/number7/ops/nightly.py`

```python
from __future__ import annotations

from datetime import date

import httpx
from pydantic import BaseModel

from number7.config import Settings
from number7.data.bridge import fetch_health
from number7.data.qc import qc_passes, run_qc, write_qc_report
from number7.data.snapshot import promote
from number7.data.sync import SnapshotExistsError, run_sync


class NightlyResult(BaseModel):
    db_date: date | None = None
    synced: bool = False
    qc_ok: bool = False
    promoted: bool = False
    skipped_reason: str | None = None


def _ping(url: str) -> None:
    httpx.get(url, timeout=10)


def run_nightly(settings: Settings, *, sync=run_sync, qc=run_qc, promote_fn=promote,
                health_fn=fetch_health, ping=_ping) -> NightlyResult:
    r = NightlyResult()
    health = health_fn(settings)
    r.db_date = health.db_date
    try:
        root = sync(settings, health=health)
        r.synced = True
    except SnapshotExistsError:
        from number7.data.snapshot import snapshot_dir
        root = snapshot_dir(settings, health.db_date)
        r.synced, r.skipped_reason = True, "exists"

    issues = qc(root, expected_db_date=health.db_date)
    write_qc_report(root, issues)
    r.qc_ok = qc_passes(issues)
    if not r.qc_ok:
        return r                       # no promote, no ping -> dead-man fires

    promote_fn(settings, health.db_date)
    r.promoted = True
    if settings.heartbeat_url:
        ping(settings.heartbeat_url)
    return r


if __name__ == "__main__":
    from number7.config import get_settings
    from number7.ops.prune import prune_snapshots
    result = run_nightly(get_settings())
    prune_snapshots(get_settings())
    print(result.model_dump_json(indent=2))
    raise SystemExit(0 if result.promoted else 1)
```

— `src/number7/ops/prune.py`

```python
from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

from number7.config import Settings


def prune_snapshots(settings: Settings, keep_daily: int = 30,
                    today: date | None = None) -> list[Path]:
    today = today or date.today()
    cutoff = today - timedelta(days=keep_daily)
    current = settings.current_link.resolve() if settings.current_link.exists() else None
    deleted: list[Path] = []
    if not settings.snapshots_dir.exists():
        return deleted
    for p in sorted(settings.snapshots_dir.iterdir()):
        try:
            d = date.fromisoformat(p.name)
        except ValueError:
            continue
        keep = (d >= cutoff) or (d.isoweekday() == 1) or (current is not None and p.resolve() == current)
        if not keep:
            shutil.rmtree(p)
            deleted.append(p)
    return deleted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_nightly.py tests/test_prune.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/number7/ops tests/test_nightly.py tests/test_prune.py
git commit -m "feat(phase0): nightly orchestrator with QC gate, heartbeat, retention"
```

---

### Task 10: Scheduling units + first supervised run

**Files:**
- Create: `ops/com.number7.nightly.plist` (Mac now), `ops/number7-nightly.service`, `ops/number7-nightly.timer` (VPS later — same job)

**Interfaces:**
- Consumes: `python -m number7.ops.nightly` (Task 9).

- [ ] **Step 1: launchd plist** — `ops/com.number7.nightly.plist` (runs 22:30 ET; Norgate finalizes US EOD in the evening)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.number7.nightly</string>
  <key>ProgramArguments</key><array>
    <string>/opt/homebrew/bin/uv</string><string>run</string>
    <string>python</string><string>-m</string><string>number7.ops.nightly</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/vyarmak/Developer/projects/ai/trading/number7</string>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>22</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>/Users/vyarmak/Developer/projects/ai/trading/number7/data/logs/nightly.out.log</string>
  <key>StandardErrorPath</key><string>/Users/vyarmak/Developer/projects/ai/trading/number7/data/logs/nightly.err.log</string>
</dict></plist>
```

- [ ] **Step 2: systemd units for the VPS (deployed in Phase 2, authored now)** — `ops/number7-nightly.service`

```ini
[Unit]
Description=number7 nightly data sync
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/number7
ExecStart=/usr/local/bin/uv run python -m number7.ops.nightly
```

— `ops/number7-nightly.timer`

```ini
[Unit]
Description=number7 nightly data sync timer

[Timer]
OnCalendar=Mon..Fri 22:30 America/New_York
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Install + first supervised run on the Mac**

```bash
mkdir -p data/logs
cp .env.example .env   # then fill N7_NORGATE_BASE_URL, N7_NORGATE_TOKEN, N7_DATA_DIR, N7_HEARTBEAT_URL
uv run python -m number7.ops.nightly          # first run manually, watch it
cp ops/com.number7.nightly.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.number7.nightly.plist
```

Expected: first run prints `NightlyResult` with `"promoted": true`; `data/current` points at today's snapshot; `data/snapshots/<db_date>/qc_report.json` exists.

- [ ] **Step 4: Commit**

```bash
git add ops/
git commit -m "feat(phase0): launchd/systemd scheduling for nightly sync"
```

---

## Phase 0 acceptance (from blueprint §10)

- [ ] Nightly snapshot lands unattended 5 consecutive trading days (check `data/snapshots/`, heartbeat dashboard green).
- [ ] QC green all 5 days (`qc_report.json` empty or warn-only).
- [ ] `uv run pytest -m vm` — Norgate audit all green (splits, delisted names served through last quote, total-return dominance).
- [ ] `uv run pytest` — full offline suite green.

## Self-review (done at authoring)

1. **Spec coverage:** bridge consumption ✔ (T2/T4), Parquet+DuckDB ✔ (T3/T6), PIT membership ✔ (T5), QC ✔ (T7), delisting/total-return audit ✔ (T8), freshness/dead-man ✔ (T7 check 7 + T9 no-ping-on-fail), snapshot versioning for Norgate restatements ✔ (T3 immutability + T9 prune keeps weekly anchors), scheduling ✔ (T10). Gap deliberately deferred: VPS deployment of the same units (Phase 2 per blueprint §9).
2. **Placeholder scan:** none — every step has full code/commands.
3. **Type consistency:** `PRICE_COLS` defined in `sync.py` and re-exported/duplicated in `store.py` — both spell the identical list; `Settings` fields referenced in Tasks 2–10 match Task 1; `QCIssue`/`NightlyResult` signatures consistent between Tasks 7 and 9.
