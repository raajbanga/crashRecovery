# Check Yahoo prices against SEC fails-to-deliver prices and list what still needs Tiingo.
# Fails files give the SEC's closing price for a ticker on many dates. If Yahoo's series
# doesn't track those prices around a crash, the ticker probably belongs to another
# company now. One split per window is allowed for, so splits don't cause false alarms.
# python 3.14.10, pandas 2.3.3, numpy 2.5.4
# Output: data/interim/price_check.parquet, data/interim/tiingo_queue.csv
import zipfile

import numpy as np
import pandas as pd

from config import CRASHES, INTERIM, PRICE_DIR, RAW

WINDOW = pd.Timedelta(days=270)
MIN_DAYS_BEFORE_PEAK = pd.Timedelta(days=30)
MIN_DATES = 4       # fails dates needed before a ticker can be checked
MIN_AGREE = 0.8     # share of fails dates that must agree
FAILURE_ITEM = "1.03"


def load_ftd(tickers):
    frames = []
    for path in sorted((RAW / "sec" / "ftd").glob("cnsfails*.zip")):
        with zipfile.ZipFile(path) as z:
            df = pd.read_csv(z.open(z.namelist()[0]), sep="|", dtype=str, encoding="latin-1",
                             on_bad_lines="skip", keep_default_na=False)
        df.columns = [c.strip().upper() for c in df.columns]
        df = df[df["SYMBOL"].isin(tickers)][["SETTLEMENT DATE", "SYMBOL", "PRICE"]]
        df.columns = ["date", "ticker", "price"]
        frames.append(df)
    ftd = pd.concat(frames, ignore_index=True)
    ftd["date"] = pd.to_datetime(ftd["date"], format="%Y%m%d", errors="coerce")
    ftd["price"] = pd.to_numeric(ftd["price"], errors="coerce")
    ftd = ftd.dropna()
    ftd = ftd[ftd["price"] > 0].drop_duplicates(["ticker", "date"]).sort_values("date")
    return {t: g for t, g in ftd.groupby("ticker")}


def tolerance(price):
    """Allowed log gap. Thinly traded penny stocks are noisier."""
    return np.where(price < 1, 0.10, np.where(price < 5, 0.05, 0.03))


def agreement(series, ftd, peak):
    """Share of fails dates where Yahoo's level matches the SEC price.

    Yahoo prices are split-adjusted and SEC prices aren't, so the ratio between them can
    jump once at a split. The best single split point is allowed, and the ratio must hold
    steady on each side. Another company's prices drift and fail this.
    """
    near = ftd[(ftd["date"] >= peak - WINDOW) & (ftd["date"] <= peak + WINDOW)]
    if len(near) < MIN_DATES:
        return np.nan, len(near)
    # The fails price is the prior close, but dates can be a day off, so take the closer day
    after = series.index.searchsorted(near["date"].values, side="left")
    ok = after >= 1
    sec = near["price"].values[ok]
    before = series.values[after[ok] - 1]
    same = series.values[np.minimum(after[ok], len(series) - 1)]
    good = (before > 0) & (same > 0)
    sec, before, same = sec[good], before[good], same[good]
    if len(sec) < MIN_DATES:
        return np.nan, len(near)
    gap_a = np.log(sec) - np.log(before)
    gap_b = np.log(sec) - np.log(same)
    tol = tolerance(sec)

    def share(start, stop):
        if stop - start == 0:
            return 0
        a, b = gap_a[start:stop], gap_b[start:stop]
        centre = np.median(a)
        closest = np.minimum(np.abs(a - centre), np.abs(b - centre))
        return int((closest < tol[start:stop]).sum())

    n = len(sec)
    best = share(0, n)
    for split in range(MIN_DATES, n - MIN_DATES + 1):
        best = max(best, share(0, split) + share(split, n))
    return best / n, len(near)


def main():
    tmap = pd.read_parquet(INTERIM / "ticker_map.parquet")
    tmap = tmap[tmap["ticker"].notna() & ~tmap["conflict"]].copy()
    status = pd.read_csv(PRICE_DIR / "yahoo_status.csv", keep_default_na=False)
    has_yahoo = set(status.loc[status["status"] == "ok", "ticker"])
    ftd = load_ftd(set(tmap["ticker"]))

    cache = {}
    rows = []
    for row in tmap.itertuples():
        peak = pd.Timestamp(CRASHES[row.crash]["peak"])
        result = {"cik": row.cik, "crash": row.crash, "ticker": row.ticker, "source": row.source,
                  "agree": np.nan, "ftd_days": 0}
        if row.ticker not in has_yahoo:
            result["check"] = "no_yahoo"
        else:
            if row.ticker not in cache:
                frame = pd.read_parquet(PRICE_DIR / "yahoo" / f"{row.ticker}.parquet")
                cache[row.ticker] = frame["Close"].dropna().sort_index()
            series = cache[row.ticker]
            if series.index[0] > peak - MIN_DAYS_BEFORE_PEAK or series.index[-1] < peak:
                result["check"] = "yahoo_misses_peak"
            else:
                agree, days = (np.nan, 0)
                if row.ticker in ftd:
                    agree, days = agreement(series, ftd[row.ticker], peak)
                result["agree"], result["ftd_days"] = agree, days
                if np.isnan(agree):
                    result["check"] = "too_few_ftd"
                elif agree >= MIN_AGREE:
                    result["check"] = "verified"
                else:
                    result["check"] = "mismatch"
        rows.append(result)
    out = pd.DataFrame(rows)

    # Without SEC prices to compare, only the SEC's own current link is accepted
    trusted = (out["check"] == "verified") | (
        (out["check"] == "too_few_ftd") & out["source"].isin(["sec_current", "manual"]))
    out["use_yahoo"] = trusted
    out.to_parquet(INTERIM / "price_check.parquet", index=False)

    # Tiingo queue: bankruptcy during a crash window first, then delisting, then the rest
    events = pd.read_parquet(INTERIM / "filing_events.parquet")
    need = out[~out["use_yahoo"]].copy()
    need["priority"] = 3
    for crash, c in CRASHES.items():
        trough = pd.Timestamp(c["trough"])
        end = (trough + pd.DateOffset(months=12)).strftime("%Y-%m-%d")
        w = events[(events["date"] >= c["peak"]) & (events["date"] <= end)]
        form25 = set(w.loc[w["form"].str.startswith("25"), "cik"])
        bankrupt = set(w.loc[w["items"].str.contains(FAILURE_ITEM, regex=False), "cik"])
        in_crash = need["crash"] == crash
        need.loc[in_crash & need["cik"].isin(form25), "priority"] = 2
        need.loc[in_crash & need["cik"].isin(bankrupt), "priority"] = 1
    queue = (need.groupby("ticker")
             .agg(priority=("priority", "min"), rows=("crash", "size"))
             .reset_index().sort_values(["priority", "rows", "ticker"],
                                        ascending=[True, False, True]))
    queue.to_csv(INTERIM / "tiingo_queue.csv", index=False)

    print(pd.crosstab(out["check"], out["crash"], margins=True).to_string())
    print(f"\nusable from Yahoo: {out['use_yahoo'].sum():,} of {len(out):,} rows")
    print(f"need Tiingo: {len(queue):,} symbols, {len(need):,} rows")
    print(queue.groupby("priority").agg(symbols=("ticker", "size"), rows=("rows", "sum")).to_string())


if __name__ == "__main__":
    main()
