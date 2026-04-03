"""
Configuration for the SEC GAAP data fetcher.
Adjust these settings to control which data is fetched and how.
"""

import os

# ---------------------------------------------------------------------------
# SEC EDGAR API settings
# ---------------------------------------------------------------------------

# Required by SEC EDGAR: identify yourself so they can contact you if needed.
# Set via environment variable or change the default below.
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "YourName yourname@example.com",  # <-- Replace with your name/email
)

# Base URLs for SEC EDGAR APIs
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Rate limiting: SEC allows up to 10 requests/second.
# We stay safely below that limit.
REQUESTS_PER_SECOND = 8
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND  # seconds between requests

# Retry settings (uses exponential back-off via tenacity)
MAX_RETRIES = 5
RETRY_WAIT_MIN = 2    # seconds
RETRY_WAIT_MAX = 60   # seconds

# ---------------------------------------------------------------------------
# Database settings
# ---------------------------------------------------------------------------

# Path to the SQLite database file
DB_PATH = os.environ.get("DB_PATH", "sec_gaap.db")

# Path to save a checkpoint file so fetching can be resumed after interruption
CHECKPOINT_FILE = "checkpoint.txt"

# ---------------------------------------------------------------------------
# GAAP concepts to extract
# ---------------------------------------------------------------------------
# These are the most commonly used US-GAAP XBRL concepts for quantitative
# models.  Only concept names recognised by SEC EDGAR are listed here.
# See https://xbrl.fasb.org/us-gaap/2023/elts/us-gaap-2023.htm for the full taxonomy.

GAAP_CONCEPTS = [
    # ---- Income Statement ------------------------------------------------
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "GrossProfit",
    "CostOfRevenue",
    "CostOfGoodsSold",
    "OperatingExpenses",
    "ResearchAndDevelopmentExpense",
    "SellingGeneralAndAdministrativeExpense",
    "OperatingIncomeLoss",
    "InterestExpense",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeTaxExpenseBenefit",
    "NetIncomeLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "EarningsPerShareBasic",
    "EarningsPerShareDiluted",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    # ---- Balance Sheet – Assets ------------------------------------------
    "Assets",
    "AssetsCurrent",
    "CashAndCashEquivalentsAtCarryingValue",
    "ShortTermInvestments",
    "AccountsReceivableNetCurrent",
    "InventoryNet",
    "PrepaidExpenseAndOtherAssetsCurrent",
    "PropertyPlantAndEquipmentNet",
    "Goodwill",
    "IntangibleAssetsNetExcludingGoodwill",
    "LongTermInvestments",
    "OtherAssetsNoncurrent",
    # ---- Balance Sheet – Liabilities ------------------------------------
    "Liabilities",
    "LiabilitiesCurrent",
    "AccountsPayableCurrent",
    "AccruedLiabilitiesCurrent",
    "ShortTermBorrowings",
    "LongTermDebt",
    "LongTermDebtNoncurrent",
    "DeferredRevenueCurrent",
    "DeferredRevenueNoncurrent",
    "OtherLiabilitiesNoncurrent",
    "LiabilitiesAndStockholdersEquity",
    # ---- Balance Sheet – Equity -----------------------------------------
    "StockholdersEquity",
    "CommonStockValue",
    "AdditionalPaidInCapital",
    "RetainedEarningsAccumulatedDeficit",
    "AccumulatedOtherComprehensiveIncomeLossNetOfTax",
    "TreasuryStockValue",
    "CommonStockSharesOutstanding",
    "CommonStockSharesIssued",
    # ---- Cash Flow Statement --------------------------------------------
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInFinancingActivities",
    "DepreciationDepletionAndAmortization",
    "ShareBasedCompensation",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireBusinessesNetOfCashAcquired",
    "ProceedsFromIssuanceOfCommonStock",
    "PaymentsOfDividends",
    "PaymentsForRepurchaseOfCommonStock",
    "CashAndCashEquivalentsPeriodIncreaseDecrease",
]
