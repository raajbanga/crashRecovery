# Download Yahoo's split history for every ticker priced from Yahoo.
# Yahoo's Close is adjusted for later splits, so the raw price at a peak is the adjusted
# price times every split after it. 06 uses this to get the raw price and market value.
# Safe to re-run: finished tickers are skipped.
# python 3.14.10, pandas 2.3.3, yfinance 1.8.0
# Usage: python 05d_download_splits.py [--limit N]
# Output: data/raw/prices/yahoo_splits.csv (ticker, date, ratio), yahoo_splits_status.csv
import argparse
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf

from config import INTERIM, PRICE_DIR

OUT = PRICE_DIR / "yahoo_splits.csv"
STATUS = PRICE_DIR / "yahoo_splits_status.csv"
PAUSE = 0.4   # per worker, between requests
WORKERS = 4
CONTROL = "AAPL"  # has splits; if it comes back empty, Yahoo is throttling
CHECK_EVERY = 100
MAX_THROTTLED = 5


def splits(ticker):
    s = yf.Ticker(ticker).splits
    if s is None or s.empty:
        return pd.DataFrame(columns=["ticker", "date", "ratio"])
    dates = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
    return pd.DataFrame({"ticker": ticker, "date": dates.date, "ratio": s.values})


def fetch(ticker):
    try:
        f = splits(ticker)
        status = "ok"
    except Exception as e:  # one bad symbol shouldn't stop the run
        f, status = pd.DataFrame(columns=["ticker", "date", "ratio"]), f"error: {type(e).__name__}"
    time.sleep(PAUSE)
    return ticker, f, status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    # Every Yahoo ticker, plus tickers matched since the price download. Tickers without
    # enough fails prices to check the raw price go first, since only splits can fix them.
    src = pd.read_parquet(INTERIM / "price_source.parquet")
    tmap = pd.read_parquet(INTERIM / "ticker_map.parquet")
    matched = set(tmap.loc[tmap["ticker"].notna() & ~tmap["conflict"], "ticker"])
    tickers = set(src.loc[src["price_source"] == "yahoo", "ticker"]) | (matched - set(src["ticker"]))
    check = pd.read_parquet(INTERIM / "price_check.parquet")
    unchecked = set(check.loc[check["check"] != "verified", "ticker"])
    tickers = sorted(tickers, key=lambda t: (t not in unchecked, t))
    done = set()
    if STATUS.exists():
        done = set(pd.read_csv(STATUS, keep_default_na=False)["ticker"])
    todo = [t for t in tickers if t not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(tickers):,} tickers, {len(done):,} done, {len(todo):,} to get", flush=True)

    throttled = 0
    i = 0
    while i < len(todo):
        if i % CHECK_EVERY == 0 and splits(CONTROL).empty:
            throttled += 1
            print(f"control ticker failed ({throttled}/{MAX_THROTTLED}), waiting", flush=True)
            if throttled >= MAX_THROTTLED:
                raise SystemExit("Yahoo seems to be throttling. Re-run later to resume.")
            time.sleep(120 * throttled)
            continue
        throttled = 0
        batch = todo[i:i + CHECK_EVERY]
        with ThreadPoolExecutor(WORKERS) as pool:
            results = list(pool.map(fetch, batch))
        frames = [f for _, f, _ in results]
        status = [(t, s, len(f)) for t, f, s in results]
        frames = [f for f in frames if len(f)]
        got = pd.concat(frames) if frames else pd.DataFrame()
        if len(got):
            got.to_csv(OUT, mode="a", header=not OUT.exists(), index=False)
        pd.DataFrame(status, columns=["ticker", "status", "splits"]).to_csv(
            STATUS, mode="a", header=not STATUS.exists(), index=False)
        i += len(batch)
        print(f"{i:,}/{len(todo):,}", flush=True)


if __name__ == "__main__":
    main()
