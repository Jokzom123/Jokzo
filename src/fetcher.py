"""
Main fetching logic.

Orchestrates:
1. Loading the full SEC ticker list into the database
2. Iterating over pending companies and fetching their GAAP facts
3. Parsing and storing each company's GAAP data
4. Writing/reading a checkpoint file so interrupted runs can resume
"""

import os
import logging
from typing import Optional, List, Tuple

from tqdm import tqdm

import config
from src import sec_api, database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GAAP fact extraction
# ---------------------------------------------------------------------------

def _extract_rows(cik: str, facts_json: dict) -> List[Tuple]:
    """
    Convert the raw company-facts JSON into flat rows ready for the DB.

    The SEC JSON structure is:
        {
          "facts": {
            "us-gaap": {
              "ConceptName": {
                "label": "...",
                "description": "...",
                "units": {
                  "USD": [
                    {"end": "YYYY-MM-DD", "val": 123, "accn": "...",
                     "fy": 2022, "fp": "FY", "form": "10-K",
                     "filed": "YYYY-MM-DD", "frame": "CY2022"},
                    ...
                  ]
                }
              }
            }
          }
        }
    """
    rows: List[Tuple] = []

    us_gaap = (facts_json.get("facts") or {}).get("us-gaap") or {}
    wanted = set(config.GAAP_CONCEPTS)

    for concept, concept_data in us_gaap.items():
        if concept not in wanted:
            continue

        label = concept_data.get("label", "")
        description = concept_data.get("description", "")
        units_dict = concept_data.get("units") or {}

        for unit, filings in units_dict.items():
            for filing in filings:
                end_date = filing.get("end")
                value = filing.get("val")

                # Skip entries without an end date or value
                if end_date is None or value is None:
                    continue

                rows.append((
                    cik,
                    concept,
                    label,
                    description,
                    unit,
                    end_date,
                    filing.get("filed"),
                    filing.get("accn"),
                    filing.get("form"),
                    filing.get("frame"),
                    float(value),
                ))

    return rows


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoint() -> Optional[str]:
    """Return the last successfully processed CIK, or None."""
    if os.path.exists(config.CHECKPOINT_FILE):
        with open(config.CHECKPOINT_FILE) as f:
            return f.read().strip() or None
    return None


def _save_checkpoint(cik: str) -> None:
    with open(config.CHECKPOINT_FILE, "w") as f:
        f.write(cik)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def load_tickers(conn) -> None:
    """
    Fetch the SEC company-ticker list and populate the *companies* table.
    Skips the network call if all tickers are already in the DB.
    """
    pending = database.get_pending_ciks(conn)
    existing_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]

    if existing_count > 0:
        logger.info(
            "%d companies already in DB (%d pending). Skipping ticker download.",
            existing_count,
            len(pending),
        )
        return

    tickers = sec_api.fetch_company_tickers()
    database.upsert_companies(conn, tickers)


def fetch_all_gaap(conn, limit: Optional[int] = None) -> None:
    """
    Fetch GAAP facts for all companies that have not yet been processed.

    Parameters
    ----------
    conn  : sqlite3.Connection
    limit : int, optional
        Stop after processing this many companies (useful for testing).
    """
    pending = database.get_pending_ciks(conn)

    if not pending:
        logger.info("No pending companies – all GAAP data is up to date.")
        return

    # Resume support: skip CIKs already processed in a previous run
    last_cik = _load_checkpoint()
    if last_cik and last_cik in pending:
        idx = pending.index(last_cik) + 1
        logger.info(
            "Resuming from checkpoint: skipping %d already-processed companies.",
            idx,
        )
        pending = pending[idx:]

    if limit is not None:
        pending = pending[:limit]

    logger.info("Fetching GAAP facts for %d companies …", len(pending))

    skipped = 0
    inserted_total = 0

    for cik in tqdm(pending, desc="Companies", unit="co"):
        try:
            facts_json = sec_api.fetch_company_facts(cik)
        except Exception as exc:
            logger.error("Failed to fetch CIK %s: %s", cik, exc)
            database.mark_fetched(conn, cik)  # mark so we don't retry forever
            continue

        if facts_json is None:
            # Company has no XBRL/GAAP data (common for foreign filers)
            skipped += 1
            database.mark_fetched(conn, cik)
            _save_checkpoint(cik)
            continue

        rows = _extract_rows(cik, facts_json)
        n = database.insert_gaap_facts(conn, rows)
        inserted_total += n

        database.mark_fetched(conn, cik)
        _save_checkpoint(cik)

        logger.debug("CIK %s – inserted %d fact rows.", cik, n)

    logger.info(
        "Done. Inserted %d fact rows total. %d companies had no XBRL data.",
        inserted_total,
        skipped,
    )
