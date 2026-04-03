"""
SQLite database layer for SEC GAAP data.

Schema
------
companies   – one row per company (CIK, ticker, name)
gaap_facts  – one row per (company, concept, filing period, unit)
"""

import sqlite3
import logging
from typing import List, Tuple

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS companies (
    cik          TEXT PRIMARY KEY,
    ticker       TEXT NOT NULL,
    name         TEXT,
    fetched      INTEGER NOT NULL DEFAULT 0,   -- 1 = GAAP facts fetched
    updated_at   TEXT                           -- ISO-8601 timestamp
);

CREATE INDEX IF NOT EXISTS idx_companies_ticker ON companies(ticker);

CREATE TABLE IF NOT EXISTS gaap_facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cik         TEXT    NOT NULL,
    concept     TEXT    NOT NULL,   -- e.g. "NetIncomeLoss"
    label       TEXT,
    description TEXT,
    unit        TEXT    NOT NULL,   -- e.g. "USD", "shares"
    end_date    TEXT    NOT NULL,   -- period end date  YYYY-MM-DD
    filed       TEXT,               -- filing date
    accn        TEXT,               -- accession number
    form        TEXT,               -- 10-K, 10-Q, etc.
    frame       TEXT,               -- e.g. "CY2022Q4I"
    value       REAL    NOT NULL,
    FOREIGN KEY (cik) REFERENCES companies(cik)
);

CREATE INDEX IF NOT EXISTS idx_gaap_cik       ON gaap_facts(cik);
CREATE INDEX IF NOT EXISTS idx_gaap_concept   ON gaap_facts(concept);
CREATE INDEX IF NOT EXISTS idx_gaap_end_date  ON gaap_facts(end_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_gaap_fact
    ON gaap_facts(cik, concept, unit, end_date, accn);
"""


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

def get_connection(db_path: str = config.DB_PATH) -> sqlite3.Connection:
    """Open (or create) the SQLite database and return a connection."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not already exist."""
    conn.executescript(_DDL)
    conn.commit()
    logger.info("Database initialised at %s", config.DB_PATH)


# ---------------------------------------------------------------------------
# Company helpers
# ---------------------------------------------------------------------------

def upsert_companies(conn: sqlite3.Connection, companies: dict) -> None:
    """
    Insert or update rows in the *companies* table.

    *companies* maps CIK → {"ticker": str, "name": str}.
    """
    rows = [
        (cik, info["ticker"], info["name"])
        for cik, info in companies.items()
    ]
    conn.executemany(
        """
        INSERT INTO companies (cik, ticker, name)
        VALUES (?, ?, ?)
        ON CONFLICT(cik) DO UPDATE SET
            ticker = excluded.ticker,
            name   = excluded.name
        """,
        rows,
    )
    conn.commit()
    logger.info("Upserted %d companies.", len(rows))


def get_pending_ciks(conn: sqlite3.Connection) -> List[str]:
    """Return CIKs whose GAAP facts have not yet been fetched."""
    cursor = conn.execute(
        "SELECT cik FROM companies WHERE fetched = 0 ORDER BY cik"
    )
    return [row[0] for row in cursor.fetchall()]


def mark_fetched(conn: sqlite3.Connection, cik: str) -> None:
    """Mark a company as having its GAAP facts fetched (or attempted)."""
    conn.execute(
        "UPDATE companies SET fetched = 1, updated_at = datetime('now') WHERE cik = ?",
        (cik,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# GAAP fact helpers
# ---------------------------------------------------------------------------

def insert_gaap_facts(
    conn: sqlite3.Connection,
    rows: List[Tuple],
) -> int:
    """
    Bulk-insert GAAP fact rows, ignoring duplicates.

    Each tuple must contain:
        (cik, concept, label, description, unit, end_date,
         filed, accn, form, frame, value)

    Returns the number of rows actually inserted.
    """
    if not rows:
        return 0

    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO gaap_facts
            (cik, concept, label, description, unit, end_date,
             filed, accn, form, frame, value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return conn.total_changes - before
