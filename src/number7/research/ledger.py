from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from number7.research.registry import PreRegistration

_SCHEMA = """
create sequence if not exists reg_seq;
create sequence if not exists run_seq;
create table if not exists registrations(
  reg_id bigint primary key, family text, origin text, mechanism text,
  param_space_hash text, search_space_size int, status text default 'registered',
  created_at timestamp default current_timestamp);
create table if not exists runs(
  run_id bigint primary key, reg_id bigint, code_sha text, snapshot_id text,
  param_hash text, params json, sharpe double, n_obs int, metrics json,
  created_at timestamp default current_timestamp)
"""


def param_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


class Ledger:
    """Trials ledger (blueprint §5): every backtest logged; scrapped param spaces
    cannot re-enter without human sign-off (the tweak-and-retest guard)."""

    def __init__(self, path: Path) -> None:
        self._con = duckdb.connect(str(path))
        for stmt in _SCHEMA.strip().split(";"):
            if stmt.strip():
                self._con.execute(stmt)

    def register(self, prereg: PreRegistration) -> int:
        space_hash = param_hash(prereg.param_space)
        dup = self._con.execute(
            "select count(*) from registrations where family=? and param_space_hash=? "
            "and status='scrapped'", [prereg.family, space_hash]).fetchone()[0]
        if dup:
            raise ValueError(f"param space was scrapped in family {prereg.family!r}; "
                             "re-entry requires human sign-off (new family or amended space)")
        reg_id = self._con.execute("select nextval('reg_seq')").fetchone()[0]
        self._con.execute(
            "insert into registrations(reg_id, family, origin, mechanism, param_space_hash, "
            "search_space_size) values (?,?,?,?,?,?)",
            [reg_id, prereg.family, prereg.origin, prereg.mechanism, space_hash,
             prereg.search_space_size])
        return int(reg_id)

    def log_run(self, reg_id: int, code_sha: str, snapshot_id: str,
                params: dict, metrics: dict) -> int:
        run_id = self._con.execute("select nextval('run_seq')").fetchone()[0]
        self._con.execute(
            "insert into runs values (?,?,?,?,?,?,?,?,?, current_timestamp)",
            [run_id, reg_id, code_sha, snapshot_id, param_hash(params), json.dumps(params),
             float(metrics.get("sharpe", 0.0)), int(metrics.get("n_obs", 0)),
             json.dumps(metrics)])
        return int(run_id)

    def family_trials(self, family: str) -> int:
        declared = self._con.execute(
            "select coalesce(sum(search_space_size),0) from registrations where family=?",
            [family]).fetchone()[0]
        runs = self._con.execute(
            "select count(*) from runs x join registrations r on r.reg_id=x.reg_id "
            "where r.family=?", [family]).fetchone()[0]
        return max(int(declared), int(runs))

    def var_of_trial_sharpes(self, family: str) -> float:
        v = self._con.execute(
            "select var_pop(x.sharpe) from runs x join registrations r on r.reg_id=x.reg_id "
            "where r.family=?", [family]).fetchone()[0]
        return float(v or 0.0)

    def scrap(self, reg_id: int) -> None:
        self._con.execute("update registrations set status='scrapped' where reg_id=?",
                          [reg_id])
