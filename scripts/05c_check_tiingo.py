# Check Tiingo prices against SEC fails-to-deliver prices, pick one price source per row,
# and compare Yahoo with Tiingo where both have a ticker.
# Uses the same check as 05_check_prices.py. Tiingo's raw close is compared, like the
# SEC prices, and one split per window is still allowed.
# python 3.14.10, pandas 2.3.3, numpy 2.5.4
# Output: data/interim/price_source.parquet, data/interim/source_compare.csv
import importlib

import numpy as np
import pandas as pd

from config import CRASHES, INTERIM, PRICE_DIR

check = importlib.import_module("05_check_prices")
TRUSTED_SOURCES = ["sec_current", "manual"]


def load_tiingo(ticker, column="close"):
    frame = pd.read_parquet(PRICE_DIR / "tiingo" / f"{ticker}.parquet")
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None).as_unit("ns")
    return frame[column].dropna().sort_index()


def old_symbols(need):
    """Fails symbols for the same security under earlier tickers, per row.

    A dead firm's later ticker (SIVBQ) rarely shows up in fails files around the peak,
    when it still traded as SIVB. Name-matched rows keep the fails description they
    matched on, so that description, and any symbol sharing its CUSIP, gives the
    earlier tickers. A reused ticker (BBBY in 2025) has another CUSIP and is left out.
    """
    tmap = pd.read_parquet(INTERIM / "ticker_map.parquet")[["cik", "crash", "ftd_description"]]
    symbols = pd.read_parquet(INTERIM / "ftd_symbols.parquet")
    by_cusip = symbols.groupby("cusip")["symbol"].agg(set)
    cusips_by_desc = symbols.groupby("description")["cusip"].agg(set)
    found = {}
    for row in need.merge(tmap, on=["cik", "crash"], how="left").itertuples():
        if not isinstance(row.ftd_description, str):
            continue
        aliases = set()
        for cusip in cusips_by_desc.get(row.ftd_description, set()):
            aliases |= by_cusip.get(cusip, set())
        if aliases - {row.ticker}:
            found[(row.cik, row.crash)] = aliases | {row.ticker}
    return found


def fails_for(ftd, symbols):
    frames = [ftd[s] for s in symbols if s in ftd]
    if not frames:
        return None
    return pd.concat(frames).drop_duplicates("date").sort_values("date")


def check_tiingo(price_check):
    status = pd.read_csv(PRICE_DIR / "tiingo_status.csv", keep_default_na=False)
    has_tiingo = set(status.loc[status["status"] == "ok", "ticker"])
    need = price_check[~price_check["use_yahoo"]]
    aliases = old_symbols(need)
    ftd = check.load_ftd(set(need["ticker"]).union(*aliases.values()))
    cache, rows = {}, []
    for row in need.itertuples():
        peak = pd.Timestamp(CRASHES[row.crash]["peak"])
        result = {"cik": row.cik, "crash": row.crash, "ticker": row.ticker, "source": row.source,
                  "yahoo_check": row.check, "agree": np.nan, "ftd_days": 0,
                  "via_old_ticker": False}
        if row.ticker not in has_tiingo:
            result["check"] = "no_tiingo"
        else:
            if row.ticker not in cache:
                cache[row.ticker] = load_tiingo(row.ticker)
            series = cache[row.ticker]
            if series.index[0] > peak - check.MIN_DAYS_BEFORE_PEAK or series.index[-1] < peak:
                result["check"] = "tiingo_misses_peak"
            else:
                agree, days = (np.nan, 0)
                if row.ticker in ftd:
                    agree, days = check.agreement(series, ftd[row.ticker], peak)
                # Too few dates under this ticker: try the same security's earlier tickers
                old = fails_for(ftd, aliases.get((row.cik, row.crash), ()))
                if np.isnan(agree) and old is not None:
                    agree, days = check.agreement(series, old, peak)
                    result["via_old_ticker"] = not np.isnan(agree)
                result["agree"], result["ftd_days"] = agree, days
                if np.isnan(agree):
                    result["check"] = "too_few_ftd"
                elif agree >= check.MIN_AGREE:
                    result["check"] = "verified"
                else:
                    result["check"] = "mismatch"
        rows.append(result)
    out = pd.DataFrame(rows)
    out["use_tiingo"] = (out["check"] == "verified") | (
        (out["check"] == "too_few_ftd") & out["source"].isin(TRUSTED_SOURCES))
    return out


def compare_sources(price_check):
    """Daily adjusted returns from Yahoo and Tiingo on the same dates, per shared ticker."""
    status = pd.read_csv(PRICE_DIR / "tiingo_status.csv", keep_default_na=False)
    yahoo = pd.read_csv(PRICE_DIR / "yahoo_status.csv", keep_default_na=False)
    shared = sorted(set(status.loc[status["status"] == "ok", "ticker"])
                    & set(yahoo.loc[yahoo["status"] == "ok", "ticker"]))
    yahoo_verified = set(price_check.loc[price_check["check"] == "verified", "ticker"])
    rows = []
    for ticker in shared:
        t = load_tiingo(ticker, "adjClose")
        y = pd.read_parquet(PRICE_DIR / "yahoo" / f"{ticker}.parquet")["Adj Close"].dropna()
        y.index = pd.DatetimeIndex(y.index).tz_localize(None).as_unit("ns").normalize()
        both = pd.concat({"y": y, "t": t}, axis=1, join="inner")
        both = both[(both > 0).all(axis=1)]
        if len(both) < 60:
            continue
        r = np.log(both).diff().dropna()
        if r.std().min() == 0:  # flat prices give no correlation
            continue
        gap = (r["y"] - r["t"]).abs()
        rows.append({"ticker": ticker, "days": len(r), "yahoo_verified": ticker in yahoo_verified,
                     "corr": r["y"].corr(r["t"]), "median_gap": gap.median(),
                     "share_close": (gap < 0.005).mean(),
                     "total_return_gap": abs(r["y"].sum() - r["t"].sum())})
    return pd.DataFrame(rows)


def main():
    price_check = pd.read_parquet(INTERIM / "price_check.parquet")
    tiingo = check_tiingo(price_check)

    source = price_check[["cik", "crash", "ticker", "source"]].copy()
    source["price_source"] = np.where(price_check["use_yahoo"], "yahoo", "none")
    use = tiingo.loc[tiingo["use_tiingo"], ["cik", "crash"]].assign(use=True)
    source = source.merge(use, on=["cik", "crash"], how="left")
    source.loc[source["use"].eq(True), "price_source"] = "tiingo"
    source = source.drop(columns="use").merge(
        tiingo[["cik", "crash", "check"]].rename(columns={"check": "tiingo_check"}),
        on=["cik", "crash"], how="left")
    source.to_parquet(INTERIM / "price_source.parquet", index=False)

    compare = compare_sources(price_check)
    compare.to_csv(INTERIM / "source_compare.csv", index=False)

    print("Tiingo check on rows Yahoo couldn't cover:")
    print(pd.crosstab(tiingo["check"], tiingo["crash"], margins=True).to_string())
    print(f"verified through earlier tickers: {(tiingo['via_old_ticker'] & (tiingo['check'] == 'verified')).sum():,} rows")
    print("\nWhy those rows needed Tiingo, by Tiingo result:")
    print(pd.crosstab(tiingo["yahoo_check"], tiingo["use_tiingo"], margins=True).to_string())
    print("\nPrice source per row:")
    print(pd.crosstab(source["price_source"], source["crash"], margins=True).to_string())
    print(f"\nYahoo vs Tiingo, {len(compare):,} shared tickers with 60+ common days:")
    print(compare.groupby("yahoo_verified")[["corr", "median_gap", "share_close", "total_return_gap"]]
          .median().round(4).to_string())


if __name__ == "__main__":
    main()
