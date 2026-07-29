from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,       -- CALL or PUT
    inst_id TEXT NOT NULL,
    strike REAL NOT NULL,
    expiry TEXT NOT NULL,
    bias_score INTEGER NOT NULL,
    opened_at TEXT NOT NULL,
    entry_price REAL NOT NULL,
    entry_spot REAL NOT NULL,
    contracts REAL NOT NULL,
    stake_usd REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN or CLOSED
    closed_at TEXT,
    exit_price REAL,
    exit_spot REAL,
    exit_value_usd REAL,
    pnl_usd REAL,
    result TEXT                     -- WIN / LOSS / PUSH
);
CREATE INDEX IF NOT EXISTS idx_bets_symbol_status ON bets(symbol, status);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    bias_label TEXT NOT NULL,
    bias_score INTEGER NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_log_ts ON activity_log(id DESC);
"""

# Additive migrations for columns introduced after the initial schema.
# ALTER TABLE ADD COLUMN is idempotent-by-catch here since SQLite has no
# "IF NOT EXISTS" for columns.
MIGRATIONS = [
    "ALTER TABLE bets ADD COLUMN entry_order_id TEXT",
    "ALTER TABLE bets ADD COLUMN exit_order_id TEXT",
]


class BetsDB:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(SCHEMA)
        for migration in MIGRATIONS:
            try:
                self._conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists
        self._conn.commit()

    def open_bet(
        self,
        *,
        symbol: str,
        direction: str,
        inst_id: str,
        strike: float,
        expiry: str,
        bias_score: int,
        opened_at: str,
        entry_price: float,
        entry_spot: float,
        contracts: float,
        stake_usd: float,
        entry_order_id: str | None = None,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO bets
                   (symbol, direction, inst_id, strike, expiry, bias_score, opened_at,
                    entry_price, entry_spot, contracts, stake_usd, entry_order_id, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')""",
                (
                    symbol,
                    direction,
                    inst_id,
                    strike,
                    expiry,
                    bias_score,
                    opened_at,
                    entry_price,
                    entry_spot,
                    contracts,
                    stake_usd,
                    entry_order_id,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_open_bet(self, symbol: str) -> sqlite3.Row | None:
        cur = self._conn.execute(
            "SELECT * FROM bets WHERE symbol = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
            (symbol,),
        )
        return cur.fetchone()

    def close_bet(
        self,
        bet_id: int,
        *,
        closed_at: str,
        exit_price: float,
        exit_spot: float,
        exit_value_usd: float,
        pnl_usd: float,
        result: str,
        exit_order_id: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE bets
                   SET status='CLOSED', closed_at=?, exit_price=?, exit_spot=?,
                       exit_value_usd=?, pnl_usd=?, result=?, exit_order_id=?
                   WHERE id=?""",
                (
                    closed_at,
                    exit_price,
                    exit_spot,
                    exit_value_usd,
                    pnl_usd,
                    result,
                    exit_order_id,
                    bet_id,
                ),
            )
            self._conn.commit()

    def list_bets(self, limit: int = 100, symbol: str | None = None) -> list[sqlite3.Row]:
        if symbol:
            cur = self._conn.execute(
                "SELECT * FROM bets WHERE symbol = ? ORDER BY id DESC LIMIT ?", (symbol, limit)
            )
        else:
            cur = self._conn.execute("SELECT * FROM bets ORDER BY id DESC LIMIT ?", (limit,))
        return cur.fetchall()

    def closed_bets_chronological(self, symbol: str | None = None) -> list[sqlite3.Row]:
        if symbol:
            cur = self._conn.execute(
                "SELECT * FROM bets WHERE status='CLOSED' AND symbol=? ORDER BY id ASC",
                (symbol,),
            )
        else:
            cur = self._conn.execute("SELECT * FROM bets WHERE status='CLOSED' ORDER BY id ASC")
        return cur.fetchall()

    def log_activity(
        self, *, ts: str, symbol: str, bias_label: str, bias_score: int, message: str
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO activity_log (ts, symbol, bias_label, bias_score, message)
                   VALUES (?, ?, ?, ?, ?)""",
                (ts, symbol, bias_label, bias_score, message),
            )
            self._conn.commit()

    def list_activity(self, limit: int = 50) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()

    def close(self) -> None:
        self._conn.close()
