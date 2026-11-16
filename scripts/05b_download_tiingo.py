# Download Tiingo prices in queue order, within the free plan's limits.
# Safe to re-run: finished symbols are skipped. Uses each key's monthly symbols in turn,
# then stops, so run it again after the monthly reset to use the next batch.
# python 3.14.10, pandas 2.3.3, requests 2.34.2
# Usage: python 05b_download_tiingo.py [--limit N]
# Output: data/raw/prices/tiingo/<ticker>.parquet, tiingo_status.csv, tiingo_ledger.csv
import argparse
import sys
import time
from datetime import date, datetime

import pandas as pd
import requests

from config import INTERIM, PRICE_DIR, TIINGO_API_KEYS

URL = "https://api.tiingo.com/tiingo/daily/{}/prices"
START = "2018-12-01"
SECONDS_PER_REQUEST = 75  # 48 an hour, just under the limit of 50
MONTHLY_SYMBOLS = 500  # per key
OUT = PRICE_DIR / "tiingo"
STATUS = PRICE_DIR / "tiingo_status.csv"
LEDGER = PRICE_DIR / "tiingo_ledger.csv"
# Used in testing on 2026-11-05, so they count against November
ALREADY_USED = ["TWTR", "ATVI", "BBBYQ", "SIVBQ", "FRCB", "HTZGQ"]
# Seconds to wait before each retry after a network failure. Long enough to outlast
# a brief outage, and few enough to stay well under the hourly request limit.
RETRY_WAITS = [60, 300, 900, 1800]
NETWORK_ERRORS = (requests.ConnectionError, requests.Timeout,
                  requests.exceptions.ChunkedEncodingError)


def load_ledger():
    if LEDGER.exists():
        ledger = pd.read_csv(LEDGER, dtype=str)
        if "key" not in ledger:  # rows from before the second key were all key 1
            ledger["key"] = "1"
        return ledger
    ledger = pd.DataFrame({"month": "2026-11", "ticker": ALREADY_USED, "key": "1"})
    ledger.to_csv(LEDGER, index=False)
    return ledger


def pick_key(ledger, month, ticker):
    """Key slot for this ticker, or None if every key is out of symbols this month."""
    this_month = ledger[ledger["month"] == month]
    seen = this_month.loc[this_month["ticker"] == ticker, "key"]
    if len(seen):  # a repeat symbol costs nothing on the key that already used it
        return seen.iloc[0] if seen.iloc[0] in TIINGO_API_KEYS else None
    for slot in TIINGO_API_KEYS:
        if (this_month["key"] == slot).sum() < MONTHLY_SYMBOLS:
            return slot
    return None


def get_prices(session, ticker, slot):
    for wait in [*RETRY_WAITS, None]:
        try:
            return session.get(URL.format(ticker), timeout=60,
                               headers={"Authorization": f"Token {TIINGO_API_KEYS[slot]}"},
                               params={"startDate": START, "endDate": date.today().isoformat(),
                                       "format": "json"})
        except NETWORK_ERRORS as e:
            if wait is None:
                sys.exit(f"Network still failing at {ticker} after "
                         f"{len(RETRY_WAITS)} retries: {e}")
            print(f"Network error at {ticker}: {e}. Retrying in {wait}s", flush=True)
            time.sleep(wait)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if not TIINGO_API_KEYS:
        sys.exit("TIINGO_API_KEY is missing from .env")
    OUT.mkdir(parents=True, exist_ok=True)

    queue = pd.read_csv(INTERIM / "tiingo_queue.csv", keep_default_na=False)
    done = set()
    if STATUS.exists():
        done = set(pd.read_csv(STATUS, keep_default_na=False)["ticker"])
    todo = [t for t in queue["ticker"] if t not in done]
    if args.limit:
        todo = todo[:args.limit]

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    ledger = load_ledger()
    print(f"{len(queue):,} in queue, {len(done):,} done, {len(todo):,} to try, "
          f"{len(TIINGO_API_KEYS)} key(s)", flush=True)

    fetched = 0
    last_slot = None
    for ticker in todo:
        month = datetime.now().strftime("%Y-%m")
        slot = pick_key(ledger, month, ticker)
        if slot is None:
            used = (ledger["month"] == month).sum()
            print(f"Monthly budget reached: {used} symbols in {month} across "
                  f"{len(TIINGO_API_KEYS)} key(s). Run again after the reset.", flush=True)
            return
        if slot != last_slot:
            print(f"Using key {slot}", flush=True)
            last_slot = slot

        r = get_prices(session, ticker, slot)
        if r.status_code == 429:
            sys.exit(f"Tiingo says limit reached (429) at {ticker} on key {slot}: {r.text[:200]}")
        if r.status_code in (401, 403):
            sys.exit(f"Tiingo refused the request ({r.status_code}) at {ticker} "
                     f"on key {slot}: {r.text[:200]}")

        is_new = not ((ledger["month"] == month) & (ledger["ticker"] == ticker)).any()
        if is_new:
            row = pd.DataFrame({"month": [month], "ticker": [ticker], "key": [slot]})
            ledger = pd.concat([ledger, row], ignore_index=True)
            ledger.to_csv(LEDGER, index=False)

        rows, first, last, status = 0, "", "", "missing"
        if r.status_code == 200:
            data = r.json()
            if data:
                frame = pd.DataFrame(data)
                frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
                frame = frame.set_index("date").sort_index()
                frame.to_parquet(OUT / f"{ticker}.parquet")
                rows, first, last = len(frame), frame.index[0].date(), frame.index[-1].date()
                status = "ok"
        elif r.status_code != 404:
            sys.exit(f"Unexpected response {r.status_code} at {ticker}: {r.text[:200]}")

        pd.DataFrame([(ticker, status, first, last, rows)],
                     columns=["ticker", "status", "first", "last", "rows"]).to_csv(
            STATUS, mode="a", header=not STATUS.exists(), index=False)
        fetched += 1
        print(f"{fetched:,}/{len(todo):,} {ticker}: {status}, {rows} rows", flush=True)
        time.sleep(SECONDS_PER_REQUEST)


if __name__ == "__main__":
    main()
