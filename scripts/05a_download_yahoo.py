# Try Yahoo for every matched ticker. Safe to re-run: finished tickers are skipped.
# A returned series isn't trusted yet: reused tickers can return another company,
# so prices get checked against SEC fails-to-deliver data in a later step.
# python 3.14.10, pandas 2.3.3, yfinance 1.8.0
# Usage: python 05a_download_yahoo.py [--limit N]
# Output: data/raw/prices/yahoo/<ticker>.parquet, data/raw/prices/yahoo_status.csv
import argparse
import time

import pandas as pd
import yfinance as yf

from config import INTERIM, PRICE_DIR

OUT = PRICE_DIR / "yahoo"
STATUS = PRICE_DIR / "yahoo_status.csv"
START = "2018-12-01"  # about a year before the first peak, for pre-crash features
BATCH = 50
PAUSE = 3
CONTROL = "AAPL"  # if a known ticker fails, we're being throttled, not missing data
MAX_THROTTLED = 5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    tmap = pd.read_parquet(INTERIM / "ticker_map.parquet")
    tickers = sorted(tmap.loc[tmap["ticker"].notna() & ~tmap["conflict"], "ticker"].unique())
    done = {}
    if STATUS.exists():
        done = pd.read_csv(STATUS, keep_default_na=False).set_index("ticker")["status"].to_dict()
    todo = [t for t in tickers if t not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(tickers):,} tickers, {len(done):,} done, {len(todo):,} to try", flush=True)

    throttled = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        data = yf.download(batch + [CONTROL], start=START, auto_adjust=False, group_by="ticker",
                           progress=False, threads=True)
        if data.empty or data[CONTROL]["Close"].dropna().empty:
            throttled += 1
            print(f"control ticker failed ({throttled}/{MAX_THROTTLED}), waiting", flush=True)
            if throttled >= MAX_THROTTLED:
                raise SystemExit("Yahoo seems to be throttling. Re-run later to resume.")
            time.sleep(120 * throttled)
            continue
        throttled = 0
        results = []
        for t in batch:
            frame = data[t].dropna(subset=["Close"]) if t in data.columns.levels[0] else pd.DataFrame()
            if frame.empty:
                results.append((t, "missing", "", "", 0))
                continue
            frame.to_parquet(OUT / f"{t}.parquet")
            results.append((t, "ok", frame.index[0].date(), frame.index[-1].date(), len(frame)))
        pd.DataFrame(results, columns=["ticker", "status", "first", "last", "rows"]).to_csv(
            STATUS, mode="a", header=not STATUS.exists(), index=False)
        got = sum(r[1] == "ok" for r in results)
        print(f"{min(i + BATCH, len(todo)):,}/{len(todo):,}: this batch {got}/{len(batch)}", flush=True)
        time.sleep(PAUSE)


if __name__ == "__main__":
    main()
