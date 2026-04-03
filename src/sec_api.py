"""
SEC EDGAR API wrapper.

Handles:
- Fetching the full list of company tickers (CIK mappings)
- Fetching all GAAP facts for a single company
- Rate limiting and retries with exponential back-off
"""

import time
import logging
from typing import Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

import config

logger = logging.getLogger(__name__)

_session: Optional[requests.Session] = None
_last_request_time: float = 0.0


def _get_session() -> requests.Session:
    """Return a singleton requests.Session with the required headers."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(
            {
                "User-Agent": config.SEC_USER_AGENT,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            }
        )
    return _session


def _rate_limited_get(url: str) -> requests.Response:
    """
    Perform a GET request while respecting the SEC rate limit.

    SEC EDGAR allows up to 10 requests per second.  We enforce a minimum
    delay between consecutive calls.
    """
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < config.REQUEST_DELAY:
        time.sleep(config.REQUEST_DELAY - elapsed)

    session = _get_session()
    response = session.get(url, timeout=30)
    _last_request_time = time.monotonic()
    return response


@retry(
    retry=retry_if_exception_type((requests.RequestException, IOError)),
    stop=stop_after_attempt(config.MAX_RETRIES),
    wait=wait_exponential(
        multiplier=1,
        min=config.RETRY_WAIT_MIN,
        max=config.RETRY_WAIT_MAX,
    ),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get_with_retry(url: str) -> requests.Response:
    """GET with automatic retry on transient errors."""
    response = _rate_limited_get(url)
    # Treat 429 (rate-limited) and 5xx as retriable errors
    if response.status_code == 429 or response.status_code >= 500:
        logger.warning("HTTP %s for %s – will retry", response.status_code, url)
        response.raise_for_status()  # triggers the retry
    return response


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def fetch_company_tickers() -> dict:
    """
    Return a dict mapping CIK (zero-padded 10-digit string) to
    ``{"ticker": str, "name": str}``.

    Source: https://www.sec.gov/files/company_tickers.json
    """
    logger.info("Fetching company tickers from SEC EDGAR …")
    response = _get_with_retry(config.SEC_TICKERS_URL)
    response.raise_for_status()

    raw = response.json()
    # The JSON is keyed by sequential integers; each value has:
    #   {"cik_str": int, "ticker": str, "title": str}
    tickers = {}
    for entry in raw.values():
        cik = str(entry["cik_str"]).zfill(10)
        tickers[cik] = {
            "ticker": entry.get("ticker", "").upper(),
            "name": entry.get("title", ""),
        }

    logger.info("Retrieved %d company entries from SEC EDGAR.", len(tickers))
    return tickers


def fetch_company_facts(cik: str) -> Optional[dict]:
    """
    Return the full GAAP facts JSON for a company identified by *cik*
    (the 10-digit zero-padded string).

    Returns ``None`` when the company has no XBRL data (HTTP 404).
    Raises on other errors.
    """
    url = config.SEC_COMPANY_FACTS_URL.format(cik=cik)
    try:
        response = _get_with_retry(url)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()
