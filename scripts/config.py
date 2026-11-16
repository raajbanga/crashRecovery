# Shared settings for all project scripts
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

SEED = 42

# Paths
RAW = ROOT / "data" / "raw"
SEC_DIR = RAW / "sec"
FRED_DIR = RAW / "fred"
PRICE_DIR = RAW / "prices"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "figures"

# Keys come from .env and are never written into code
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "")
# Each key has its own monthly symbol limit; the download script uses them in order
TIINGO_API_KEYS = {slot: key for slot, key in (("1", os.environ.get("TIINGO_API_KEY", "")),
                                               ("2", os.environ.get("TIINGO_API_KEY_2", "")),
                                               ("3", os.environ.get("TIINGO_API_KEY_3", "")),
                                               ("4", os.environ.get("TIINGO_API_KEY_4", "")))
                   if key}

# S&P 500 closing peak and trough, confirmed from FRED SP500
CRASHES = {
    "covid_2020": {"peak": "2020-02-19", "trough": "2020-03-23"},
    "rates_2022": {"peak": "2022-01-03", "trough": "2022-10-12"},
    "tariff_2025": {"peak": "2025-02-19", "trough": "2025-04-08"},
}

# Windows, in months after the market trough
RECOVERY_MONTHS = 12
SURVIVAL_CAP_MONTHS = 18

FRED_SERIES = ["SP500", "VIXCLS", "DGS10"]
