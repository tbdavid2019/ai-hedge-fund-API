"""Transactional SQLite persistence for resumable backtest evaluations."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def manifest_fingerprint(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def default_store_path() -> str:
    return os.getenv("BACKTEST_RUN_DB", "instance/backtest_runs.sqlite3")


class BacktestRunStore:
    def __init__(self, path: str | None = None):
        self.path = str(Path(path or default_store_path()).expanduser())
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    snapshot_key TEXT NOT NULL,
                    provider_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, snapshot_key)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    session_date TEXT NOT NULL,
                    decisions_json TEXT NOT NULL,
                    portfolio_before_json TEXT NOT NULL,
                    portfolio_after_json TEXT NOT NULL,
                    prices_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, session_date)
                );
                CREATE TABLE IF NOT EXISTS cells (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    session_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    analyst_signals_json TEXT NOT NULL,
                    execution_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, session_date, ticker)
                );
            """)

    def create_or_resume(self, run_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
        fingerprint = manifest_fingerprint(manifest)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT fingerprint, manifest_json, status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    db.rollback()
                    raise ValueError("run_id already exists with a different configuration fingerprint")
                db.execute("UPDATE runs SET updated_at=? WHERE run_id=?", (now, run_id))
                db.commit()
                return {"run_id": run_id, "fingerprint": fingerprint, "status": existing["status"], "resumed": True}
            db.execute(
                "INSERT INTO runs(run_id,fingerprint,manifest_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (run_id, fingerprint, canonical_json(manifest), "running", now, now),
            )
            db.commit()
        return {"run_id": run_id, "fingerprint": fingerprint, "status": "running", "resumed": False}

    def save_snapshots(self, run_id: str, snapshots: dict[str, list[dict[str, Any]]], provider_version: str):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for key, records in snapshots.items():
                payload = canonical_json(records)
                existing = db.execute(
                    "SELECT payload_json FROM snapshots WHERE run_id=? AND snapshot_key=?", (run_id, key)
                ).fetchone()
                if existing and existing["payload_json"] != payload:
                    db.rollback()
                    raise ValueError(f"immutable input snapshot changed for run {run_id}: {key}")
                db.execute(
                    "INSERT OR IGNORE INTO snapshots(run_id,snapshot_key,provider_version,payload_json) VALUES(?,?,?,?)",
                    (run_id, key, provider_version, payload),
                )
            db.execute("UPDATE runs SET updated_at=? WHERE run_id=?", (datetime.now(timezone.utc).isoformat(), run_id))
            db.commit()

    def load_snapshots(self, run_id: str) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as db:
            rows = db.execute("SELECT snapshot_key,payload_json FROM snapshots WHERE run_id=?", (run_id,)).fetchall()
        return {row["snapshot_key"]: json.loads(row["payload_json"]) for row in rows}

    def completed_sessions(self, run_id: str) -> set[str]:
        with self._connect() as db:
            rows = db.execute("SELECT session_date FROM sessions WHERE run_id=?", (run_id,)).fetchall()
        return {row["session_date"] for row in rows}

    def load_last_portfolio(self, run_id: str, fallback: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT portfolio_after_json FROM sessions WHERE run_id=? ORDER BY session_date DESC LIMIT 1", (run_id,)
            ).fetchone()
        return json.loads(row["portfolio_after_json"]) if row else fallback

    def commit_session(
        self, run_id: str, session_date: str, *, decisions: dict[str, Any],
        portfolio_before: dict[str, Any], portfolio_after: dict[str, Any],
        prices: dict[str, Any], metrics: dict[str, Any], analyst_signals: dict[str, Any] | None = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        values = (
            run_id, session_date, canonical_json(decisions), canonical_json(portfolio_before),
            canonical_json(portfolio_after), canonical_json(prices), canonical_json(metrics), now,
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT decisions_json FROM sessions WHERE run_id=? AND session_date=?", (run_id, session_date)
            ).fetchone()
            if existing:
                db.rollback()
                return False
            db.execute(
                "INSERT INTO sessions(run_id,session_date,decisions_json,portfolio_before_json,portfolio_after_json,prices_json,metrics_json,committed_at) VALUES(?,?,?,?,?,?,?,?)",
                values,
            )
            signals = analyst_signals or {}
            fills = metrics.get("fills", {})
            for ticker, decision in decisions.items():
                ticker_signals = {name: signals.get(name, {}).get(ticker) for name in signals if ticker in signals.get(name, {})}
                db.execute(
                    "INSERT INTO cells(run_id,session_date,ticker,decision_json,analyst_signals_json,execution_json) VALUES(?,?,?,?,?,?)",
                    (run_id, session_date, ticker, canonical_json(decision), canonical_json(ticker_signals), canonical_json(fills.get(ticker, {}))),
                )
            db.execute("UPDATE runs SET updated_at=? WHERE run_id=?", (now, run_id))
            db.commit()
        return True

    def get_cells(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM cells WHERE run_id=? ORDER BY session_date,ticker", (run_id,)).fetchall()
        return [{
            "session_date": row["session_date"], "ticker": row["ticker"],
            "decision": json.loads(row["decision_json"]),
            "analyst_signals": json.loads(row["analyst_signals_json"]),
            "execution": json.loads(row["execution_json"]),
        } for row in rows]

    def set_result(self, run_id: str, result: dict[str, Any], status: str = "completed"):
        with self._connect() as db:
            db.execute(
                "UPDATE runs SET status=?, result_json=?, updated_at=? WHERE run_id=?",
                (status, canonical_json(result), datetime.now(timezone.utc).isoformat(), run_id),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return None
        return {
            "run_id": row["run_id"], "fingerprint": row["fingerprint"],
            "manifest": json.loads(row["manifest_json"]), "status": row["status"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
        }
