"""
Unit tests for the SEC GAAP fetcher.

These tests run fully offline – all network calls are mocked.
Run with:  pytest tests/test_fetcher.py -v
"""

import sqlite3
import sys
import os
import types
from unittest.mock import MagicMock, patch

import pytest

# Make sure the project root is on the path so imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from src import database, fetcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_db():
    """Return an in-memory SQLite connection with the schema initialised."""
    conn = sqlite3.connect(":memory:")
    database.init_db(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# database.py
# ---------------------------------------------------------------------------

class TestDatabase:
    def test_init_creates_tables(self, mem_db):
        tables = {
            row[0]
            for row in mem_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "companies" in tables
        assert "gaap_facts" in tables

    def test_upsert_companies(self, mem_db):
        companies = {
            "0000320193": {"ticker": "AAPL", "name": "Apple Inc."},
            "0001652044": {"ticker": "GOOGL", "name": "Alphabet Inc."},
        }
        database.upsert_companies(mem_db, companies)
        count = mem_db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        assert count == 2

    def test_upsert_companies_idempotent(self, mem_db):
        companies = {"0000320193": {"ticker": "AAPL", "name": "Apple Inc."}}
        database.upsert_companies(mem_db, companies)
        database.upsert_companies(mem_db, companies)
        count = mem_db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        assert count == 1

    def test_get_pending_ciks(self, mem_db):
        companies = {
            "0000320193": {"ticker": "AAPL", "name": "Apple Inc."},
            "0001652044": {"ticker": "GOOGL", "name": "Alphabet Inc."},
        }
        database.upsert_companies(mem_db, companies)
        pending = database.get_pending_ciks(mem_db)
        assert len(pending) == 2
        assert "0000320193" in pending

    def test_mark_fetched_removes_from_pending(self, mem_db):
        companies = {"0000320193": {"ticker": "AAPL", "name": "Apple Inc."}}
        database.upsert_companies(mem_db, companies)
        database.mark_fetched(mem_db, "0000320193")
        pending = database.get_pending_ciks(mem_db)
        assert "0000320193" not in pending

    def test_insert_gaap_facts(self, mem_db):
        companies = {"0000320193": {"ticker": "AAPL", "name": "Apple Inc."}}
        database.upsert_companies(mem_db, companies)

        rows = [
            (
                "0000320193",
                "NetIncomeLoss",
                "Net Income (Loss)",
                "Net income or loss",
                "USD",
                "2022-09-24",
                "2022-11-04",
                "0000320193-22-000108",
                "10-K",
                "CY2022",
                99_803_000_000.0,
            )
        ]
        database.insert_gaap_facts(mem_db, rows)
        count = mem_db.execute("SELECT COUNT(*) FROM gaap_facts").fetchone()[0]
        assert count == 1

    def test_insert_gaap_facts_duplicate_ignored(self, mem_db):
        companies = {"0000320193": {"ticker": "AAPL", "name": "Apple Inc."}}
        database.upsert_companies(mem_db, companies)

        row = (
            "0000320193",
            "NetIncomeLoss",
            "Net Income (Loss)",
            "",
            "USD",
            "2022-09-24",
            "2022-11-04",
            "0000320193-22-000108",
            "10-K",
            "CY2022",
            99_803_000_000.0,
        )
        database.insert_gaap_facts(mem_db, [row])
        database.insert_gaap_facts(mem_db, [row])  # duplicate – should be ignored
        count = mem_db.execute("SELECT COUNT(*) FROM gaap_facts").fetchone()[0]
        assert count == 1


# ---------------------------------------------------------------------------
# fetcher._extract_rows
# ---------------------------------------------------------------------------

class TestExtractRows:
    """Tests for the JSON → flat rows converter."""

    def _make_facts_json(self, concept: str, value: float) -> dict:
        return {
            "facts": {
                "us-gaap": {
                    concept: {
                        "label": f"Label for {concept}",
                        "description": "A description",
                        "units": {
                            "USD": [
                                {
                                    "end": "2022-12-31",
                                    "val": value,
                                    "accn": "0001234567-23-000001",
                                    "fy": 2022,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2023-02-15",
                                    "frame": "CY2022",
                                }
                            ]
                        },
                    }
                }
            }
        }

    def test_extracts_wanted_concept(self):
        concept = config.GAAP_CONCEPTS[0]  # first concept in the list
        json_data = self._make_facts_json(concept, 1_000_000.0)
        rows = fetcher._extract_rows("0000000001", json_data)
        assert len(rows) == 1
        assert rows[0][1] == concept
        assert rows[0][10] == 1_000_000.0

    def test_ignores_unwanted_concept(self):
        json_data = self._make_facts_json("SomeObscureConcept", 99.0)
        rows = fetcher._extract_rows("0000000001", json_data)
        assert rows == []

    def test_skips_entry_missing_end_date(self):
        json_data = {
            "facts": {
                "us-gaap": {
                    config.GAAP_CONCEPTS[0]: {
                        "label": "Revenue",
                        "description": "",
                        "units": {
                            "USD": [
                                {"val": 100.0, "accn": "xxx", "form": "10-K"}
                            ]
                        },
                    }
                }
            }
        }
        rows = fetcher._extract_rows("0000000001", json_data)
        assert rows == []

    def test_skips_entry_missing_value(self):
        json_data = {
            "facts": {
                "us-gaap": {
                    config.GAAP_CONCEPTS[0]: {
                        "label": "Revenue",
                        "description": "",
                        "units": {
                            "USD": [
                                {"end": "2022-12-31", "accn": "xxx", "form": "10-K"}
                            ]
                        },
                    }
                }
            }
        }
        rows = fetcher._extract_rows("0000000001", json_data)
        assert rows == []

    def test_handles_empty_facts(self):
        rows = fetcher._extract_rows("0000000001", {"facts": {}})
        assert rows == []

    def test_handles_missing_facts_key(self):
        rows = fetcher._extract_rows("0000000001", {})
        assert rows == []

    def test_multiple_concepts(self):
        concepts = config.GAAP_CONCEPTS[:3]
        us_gaap = {}
        for concept in concepts:
            us_gaap[concept] = {
                "label": concept,
                "description": "",
                "units": {
                    "USD": [
                        {
                            "end": "2022-12-31",
                            "val": 1.0,
                            "accn": "acc",
                            "form": "10-K",
                            "filed": "2023-01-01",
                            "frame": "CY2022",
                        }
                    ]
                },
            }
        json_data = {"facts": {"us-gaap": us_gaap}}
        rows = fetcher._extract_rows("0000000001", json_data)
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# fetcher.fetch_all_gaap (integration, mocked network)
# ---------------------------------------------------------------------------

class TestFetchAllGaap:
    def _make_facts_json(self, concept: str, value: float) -> dict:
        return {
            "facts": {
                "us-gaap": {
                    concept: {
                        "label": f"Label for {concept}",
                        "description": "",
                        "units": {
                            "USD": [
                                {
                                    "end": "2022-12-31",
                                    "val": value,
                                    "accn": "0001234567-23-000001",
                                    "fy": 2022,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2023-02-15",
                                    "frame": "CY2022",
                                }
                            ]
                        },
                    }
                }
            }
        }

    def test_fetch_all_gaap_inserts_data(self, mem_db, tmp_path, monkeypatch):
        """fetch_all_gaap should call the API and store rows in the DB."""
        # Seed the companies table
        companies = {
            "0000320193": {"ticker": "AAPL", "name": "Apple Inc."},
        }
        database.upsert_companies(mem_db, companies)

        # Point checkpoint file to tmp dir to avoid side-effects
        monkeypatch.setattr(config, "CHECKPOINT_FILE", str(tmp_path / "cp.txt"))

        facts_json = self._make_facts_json(config.GAAP_CONCEPTS[0], 5e9)

        with patch("src.fetcher.sec_api.fetch_company_facts", return_value=facts_json):
            fetcher.fetch_all_gaap(mem_db)

        count = mem_db.execute("SELECT COUNT(*) FROM gaap_facts").fetchone()[0]
        assert count == 1

        fetched = mem_db.execute(
            "SELECT fetched FROM companies WHERE cik = '0000320193'"
        ).fetchone()[0]
        assert fetched == 1

    def test_fetch_all_gaap_handles_no_xbrl(self, mem_db, tmp_path, monkeypatch):
        """Companies without XBRL data (None response) should be marked fetched."""
        companies = {
            "0000000001": {"ticker": "FOREIGN", "name": "Foreign Corp."},
        }
        database.upsert_companies(mem_db, companies)
        monkeypatch.setattr(config, "CHECKPOINT_FILE", str(tmp_path / "cp.txt"))

        with patch("src.fetcher.sec_api.fetch_company_facts", return_value=None):
            fetcher.fetch_all_gaap(mem_db)

        fetched = mem_db.execute(
            "SELECT fetched FROM companies WHERE cik = '0000000001'"
        ).fetchone()[0]
        assert fetched == 1
        count = mem_db.execute("SELECT COUNT(*) FROM gaap_facts").fetchone()[0]
        assert count == 0

    def test_fetch_all_gaap_respects_limit(self, mem_db, tmp_path, monkeypatch):
        """The --limit flag should stop processing after N companies."""
        companies = {f"{i:010d}": {"ticker": f"T{i}", "name": f"Co{i}"} for i in range(10)}
        database.upsert_companies(mem_db, companies)
        monkeypatch.setattr(config, "CHECKPOINT_FILE", str(tmp_path / "cp.txt"))

        with patch("src.fetcher.sec_api.fetch_company_facts", return_value=None) as mock_api:
            fetcher.fetch_all_gaap(mem_db, limit=3)

        assert mock_api.call_count == 3

    def test_fetch_all_gaap_skips_already_fetched(self, mem_db, tmp_path, monkeypatch):
        """Companies already marked fetched should not be re-fetched."""
        companies = {
            "0000000001": {"ticker": "AAA", "name": "Co A"},
            "0000000002": {"ticker": "BBB", "name": "Co B"},
        }
        database.upsert_companies(mem_db, companies)
        database.mark_fetched(mem_db, "0000000001")
        monkeypatch.setattr(config, "CHECKPOINT_FILE", str(tmp_path / "cp.txt"))

        with patch("src.fetcher.sec_api.fetch_company_facts", return_value=None) as mock_api:
            fetcher.fetch_all_gaap(mem_db)

        # Only the un-fetched company should be processed
        assert mock_api.call_count == 1
