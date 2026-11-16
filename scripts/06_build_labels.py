# Build recovery labels, one row per firm-crash with a checked price series.
# python 3.14.10, pandas 2.3.3, numpy 2.5.4, yfinance 1.8.0 (SPY only)
#
# Section 1: Drop non-common securities (todo Task 2)
# Section 2: Load and clean prices
# Section 3: Market benchmark (SPY)
# Section 4: Pre-crash price and the minimum price and size filter
# Section 5: Labels
# Section 6: Exit status from SEC filings
# Section 7: Save and report
#
# Inputs: data/interim/price_source.parquet, filing_events.parquet, ftd_symbols.parquet,
#         universe.parquet, SEC fails files, data/raw/prices/{yahoo,tiingo},
#         data/raw/prices/yahoo_splits.csv, data/raw/sec/companyfacts.zip
# Output: data/processed/labels.parquet, data/interim/label_counts.csv,
#         data/interim/price_fixes.csv
import importlib
import warnings
import json
import zipfile

import numpy as np
import pandas as pd

from config import (CRASHES, INTERIM, PRICE_DIR, PROCESSED, RECOVERY_MONTHS, SEC_DIR,
                    SURVIVAL_CAP_MONTHS)

check = importlib.import_module("05_check_prices")
# numpy 2.5 warns inside pandas on Timestamp - Timedelta; the results are right
warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)

PRE_DAYS = 30                 # trading days up to and including the peak
MIN_PRE_CLOSES = 20           # closes needed in that window
DRAWDOWN_MONTHS = 3           # drawdown runs from the peak to 3 months after the trough
MIN_RAW_PRICE = 1.0           # dollars, unadjusted, at the peak
MIN_MARKET_VALUE = 10e6       # dollars
FEATURE_DAYS = 400            # calendar days before the peak that 07 uses for price features
STALE_DAYS = 365              # calendar days before the peak checked for trading
MAX_STALE = 0.30              # share of days with no price change or no volume (decided 2026-11-08)
FAILS_RATIO_SPREAD = 0.05     # fails ratios must agree this closely (median log gap)
RAW_AGREE = 0.10              # split-history and fails-ratio factors agree within this log gap

# --- Section 1: Drop non-common securities ---
# Found by searching fails descriptions (NT, DEB, PFD), firms with zero shares reported,
# and OTC real estate and fund names. Each was checked by hand.
NOT_COMMON = {
    "NRUC": "debt issuer (rural utilities cooperative), no common stock",
    "TVE": "debt issuer (Tennessee Valley Authority), no common stock",
    "MHLA": "Maiden Holdings notes; the common stock is MHLD",
    "BSA": "BrightSphere notes; the common stock was BSIG",
    "ESBA": "operating partnership units of Empire State Realty (ESRT)",
    "KBSR": "non-traded REIT",
    "INRE": "non-traded REIT",
    "LTSV": "non-traded REIT",
    "BSTT": "non-traded REIT",
    "ICRP": "non-traded REIT",
    "STSR": "non-traded REIT",
    "CMRF": "non-traded REIT",
    "TRLC": "non-traded fund",
    "FRBP": "non-traded business development company",
}
ADR_PATTERN = r"\bADR\b|\bADS\b|AMERICAN DEP|SPONSORED"
# Share counts checked by hand (2026-11-09) among rows above 20x public float. Each is a
# cover-page count off by about 1,000x or by an old split, while the price agrees with
# SEC fails prices. Their market value is set to missing, not the row dropped: the labels
# don't use shares. Rows above 20x float not listed here had a misreported float (DD,
# CTVA, EA at $0.0M) or a real high value on few assets (meme and biotech names).
SHARE_COUNT_ERRORS = {
    ("VCEL", "covid_2020"): "44.7B shares, 1,000x nearby filings",
    ("GEC", "covid_2020"): "25.4B shares, 1,000x nearby filings",
    ("TXNM", "covid_2020"): "79.7B shares, 1,000x nearby filings",
    ("MITT", "covid_2020"): "32.7B shares, 1,000x nearby filings",
    ("GOVX", "covid_2020"): "count before a 1:500 reverse split, 31x nearby filings",
    ("CCRN", "rates_2022"): "38.0B shares, 1,000x nearby filings",
    ("THER", "rates_2022"): "5.6B shares, value 5,500x assets",
    ("HURA", "tariff_2025"): "42.3B shares, 660x nearby filings",
    ("AKTX", "tariff_2025"): "49.5B ordinary shares priced as ADSs",
    ("CPK", "tariff_2025"): "22.8B shares, about 23M real",
    ("NXTS", "tariff_2025"): "price 1,500x float and 955x assets, split history unverified",
}


def adr_flags(rows):
    """ADRs of 10-K filers are kept: their returns are the firm's. Share counts are for
    ordinary shares, so market value can be off by the ADS ratio; 07 should know."""
    symbols = pd.read_parquet(INTERIM / "ftd_symbols.parquet")
    adr = symbols[symbols["description"].str.contains(ADR_PATTERN, regex=True)]
    flags = []
    for row in rows.itertuples():
        peak = pd.Timestamp(CRASHES[row.crash]["peak"])
        hit = adr[(adr["symbol"] == row.ticker) & (pd.to_datetime(adr["first"]) <= peak)
                  & (pd.to_datetime(adr["last"]) >= peak - pd.Timedelta(days=365))]
        flags.append(len(hit) > 0)
    return np.array(flags)


# --- Section 2: Load and clean prices ---
SPIKE = np.log(1.5)           # a one-day move above 50%...
SPIKE_UNDONE = 0.75           # ...with at least 75% of it undone the next day
SPLIT_RATIOS = np.array([2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 35, 40, 50, 60, 75, 80,
                         100, 150, 200, 250, 500, 1000])
SPLIT_GAP = 0.04              # log distance from a split ratio
EXTREME = np.log(3)           # moves left above 3x either way are flagged


def load_prices(ticker, source):
    """Daily adjusted close (dividends and splits), raw close, and volume."""
    if source == "yahoo":
        f = pd.read_parquet(PRICE_DIR / "yahoo" / f"{ticker}.parquet")
        s = pd.DataFrame({"adj": f["Adj Close"], "close": f["Close"], "vol": f["Volume"],
                          "split": 1.0})
    else:
        f = pd.read_parquet(PRICE_DIR / "tiingo" / f"{ticker}.parquet")
        s = pd.DataFrame({"adj": f["adjClose"], "close": f["close"], "vol": f["volume"],
                          "split": f["splitFactor"]})
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize().as_unit("ns")
    s = s[~s.index.duplicated()].sort_index()
    return s[(s["adj"] > 0) & s["adj"].notna()].astype(float)


def remove_spikes(s):
    """Drop one-day moves above 50% that are mostly undone the next day (bad prints)."""
    r = np.log(s["adj"]).diff().values
    nxt = np.append(r[1:], np.nan)
    spike = ((np.abs(r) > SPIKE) & (np.sign(nxt) == -np.sign(r))
             & (np.abs(r + nxt) < (1 - SPIKE_UNDONE) * np.abs(r)))
    return s[~spike], s.index[spike]


def find_splits(s):
    """Overnight jumps near a split ratio that hold for the next two weeks.

    Returns (date, price ratio, dollar volume stays level). A missed split moves price
    by k and share volume by 1/k, so dollar volume doesn't jump, but a crash followed by
    heavy trading can look the same, so this only finds candidates.
    """
    adj, vol = s["adj"].values, s["vol"].values
    r = np.diff(np.log(adj), prepend=np.nan)
    out = []
    for i in np.where(np.abs(r) > np.log(1.9))[0]:
        gap = np.abs(np.abs(r[i]) - np.log(SPLIT_RATIOS))
        k = SPLIT_RATIOS[gap.argmin()]
        if gap.min() > SPLIT_GAP or i < 20 or i + 10 > len(adj):
            continue
        held = np.log(np.median(adj[i:i + 10]) / adj[i - 1]) / r[i]
        if held < 0.75:
            continue
        before, after = vol[i - 20:i], vol[i:i + 20]
        level = False
        if (before > 0).sum() >= 10 and (after > 0).sum() >= 10:
            dollar = np.log(np.median(after[after > 0]) / np.median(before[before > 0])) + r[i]
            level = abs(dollar) < np.log(3)
        out.append((s.index[i], float(k) ** np.sign(r[i]), level))
    return out


def shares_confirm(shares, date, ratio):
    """True if SEC cover-page share counts move by about 1/ratio across the jump.

    A 1-for-10 reverse split cuts shares outstanding tenfold; a real 10x rally doesn't.
    Cover dates within 400 days on each side are used.
    """
    if shares is None:
        return False
    end = pd.to_datetime(shares["end"])
    before = shares[(end < date) & (end >= date - pd.Timedelta(days=FEATURE_DAYS))]
    after = shares[(end >= date) & (end <= date + pd.Timedelta(days=FEATURE_DAYS))]
    if before.empty or after.empty:
        return False
    b = before.sort_values(["end", "filed"]).iloc[-1]["val"]
    a = after.sort_values(["end", "filed"]).iloc[0]["val"]
    if a <= 0 or b <= 0:
        return False
    tol = min(0.5 * abs(np.log(ratio)), np.log(2))
    return abs(np.log(a / b) + np.log(ratio)) < tol


def clean_prices(ticker, source, shares=None):
    """Cleaned series plus a log of what changed. 07 imports this for price features.

    shares: the firm's dei share counts (end, val, filed). Without them no split is fixed.
    """
    s = load_prices(ticker, source)
    s, spikes = remove_spikes(s)
    fixes = [{"ticker": ticker, "price_source": source, "date": d, "fix": "spike_removed",
              "ratio": np.nan} for d in spikes]
    for date, ratio, level in find_splits(s):
        # Only missed reverse splits (price up, shares down) are fixed. A drop with
        # shares doubling is usually a discounted stock offering, a real loss to holders.
        if ratio > 1 and shares_confirm(shares, date, ratio):
            # Scale everything before the jump, so the series is continuous at it
            s.loc[s.index < date, ["adj", "close"]] *= ratio
            fix = "split_fixed"
        elif level:
            fix = "split_flagged"
        else:
            continue
        fixes.append({"ticker": ticker, "price_source": source, "date": date, "fix": fix,
                      "ratio": ratio})
    return s, fixes


# --- Section 3: Market benchmark ---

def load_spy():
    """SPY's adjusted close is the market's total return, matching the firms' adjusted
    returns (FRED SP500 is price-only). Downloaded once from Yahoo if missing."""
    path = PRICE_DIR / "yahoo" / "SPY.parquet"
    if not path.exists():
        import yfinance as yf
        f = yf.download("SPY", start="2018-12-01", auto_adjust=False, progress=False,
                        multi_level_index=False)
        f.index = pd.DatetimeIndex(f.index).tz_localize(None)
        f.to_parquet(path)
    spy = load_prices("SPY", "yahoo")["adj"]
    for crash, c in CRASHES.items():
        cap = pd.Timestamp(c["trough"]) + pd.DateOffset(months=SURVIVAL_CAP_MONTHS)
        assert spy.index[-1] >= cap, f"SPY ends before the {crash} cap date"
    return spy


def close_on(series, date):
    """Last close on or before a date."""
    s = series[series.index <= date]
    return (s.iloc[-1], s.index[-1]) if len(s) else (np.nan, pd.NaT)


# --- Section 4: Pre-crash price and the minimum filter ---

def latest_shares(ciks):
    """Shares outstanding from the latest cover page filed before each peak (dei tag).

    Multi-class firms often report this only by class, which companyfacts leaves out,
    so they come back missing and are filtered on price alone.
    """
    out = {}
    with zipfile.ZipFile(SEC_DIR / "companyfacts.zip") as z:
        names = set(z.namelist())
        for cik in ciks:
            name = f"CIK{cik}.json"
            if name not in names:
                continue
            facts = (json.loads(z.read(name)).get("facts", {}).get("dei", {})
                     .get("EntityCommonStockSharesOutstanding", {}).get("units", {})
                     .get("shares", []))
            if facts:
                out[cik] = pd.DataFrame(facts)[["end", "val", "filed"]]
    return out


def shares_at(shares, cik, peak):
    f = shares.get(cik)
    if f is None:
        return np.nan
    f = f[(pd.to_datetime(f["filed"]) < peak)
          & (pd.to_datetime(f["filed"]) >= peak - pd.Timedelta(days=FEATURE_DAYS))]
    f = f[f["val"] > 1000]  # a few filers report 0 or 1 for a class they don't list
    if f.empty:
        return np.nan
    return float(f.sort_values(["filed", "end"]).iloc[-1]["val"])


def load_splits():
    """Yahoo split history per ticker (05d). Tickers Yahoo answered for are all present,
    with an empty series when they never split."""
    status = pd.read_csv(PRICE_DIR / "yahoo_splits_status.csv", keep_default_na=False)
    ok = set(status.loc[status["status"] == "ok", "ticker"])
    splits = pd.read_csv(PRICE_DIR / "yahoo_splits.csv", keep_default_na=False, parse_dates=["date"])
    by = {t: g.set_index("date")["ratio"] for t, g in splits.groupby("ticker")}
    none = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    return {t: by.get(t, none) for t in ok}


def fails_factor(s, ticker, ftd, peak):
    """Raw price over Yahoo's split-adjusted close, from SEC fails prices near the peak.
    None unless at least 3 dates agree. Not snapped to one split ratio, so stacked
    reverse splits (1:15 then 1:20) are handled."""
    if ticker not in ftd:
        return None
    f = ftd[ticker]
    f = f[(f["date"] >= peak - pd.Timedelta(days=45)) & (f["date"] <= peak + pd.Timedelta(days=45))]
    pos = s.index.searchsorted(f["date"].values, side="left")
    ok = pos >= 1
    if ok.sum() < 3:
        return None
    gaps = np.log(f["price"].values[ok] / s["close"].values[pos[ok] - 1])
    centre = np.median(gaps)
    if np.median(np.abs(gaps - centre)) > FAILS_RATIO_SPREAD:
        return None
    return float(np.exp(centre))


def raw_factor(s, source, ticker, ftd, splits, peak):
    """Ratio of the unadjusted price to the adjusted close at the peak, and how it was found.

    Tiingo has the raw close. Yahoo's Close is adjusted for every later split, so the raw
    close is Close times all split ratios after the peak (Yahoo's split history, 05d).
    SEC fails prices give an independent check, and the factor when the split history
    is missing or disagrees with them. Only with neither is no split assumed.
    Before 2026-11-08 the fails ratio was the only source and had to be one split ratio,
    so stacked reverse splits counted as no split and inflated about 850 market values.
    """
    at = s[s.index <= peak].iloc[-1]
    dividends = at["close"] / at["adj"]
    if source == "tiingo":
        return dividends, "tiingo_raw", "none"
    from_fails = fails_factor(s, ticker, ftd, peak)
    if ticker in splits:
        h = splits[ticker]
        # A split dated after the download isn't in the prices yet (ARAY, JSPR in Nov 2026)
        factor = float(h[(h.index > peak) & (h.index <= s.index[-1])].prod())
        if from_fails is None:
            return factor * dividends, "yahoo_splits", "none"
        if abs(np.log(factor / from_fails)) < RAW_AGREE:
            return factor * dividends, "yahoo_splits", "agree"
        # They agree on 99% of rows. Fails prices observe the raw price directly, while
        # Yahoo sometimes lists a split before its prices reflect it (OPAD, NFE), so the
        # fails ratio wins. Rows without fails prices can't be checked this way.
        return from_fails * dividends, "fails_ratio", "disagree"
    if from_fails is not None:
        return from_fails * dividends, "fails_ratio", "none"
    return dividends, "assumed", "none"


def stale_share(s, peak):
    """Share of trading days in the year before the peak with no price change or no volume."""
    w = s[(s.index > peak - pd.Timedelta(days=STALE_DAYS)) & (s.index <= peak)]
    if len(w) < 2:
        return np.nan
    flat = w["adj"].diff().iloc[1:].eq(0) | w["vol"].iloc[1:].fillna(0).eq(0)
    return float(flat.mean())


# --- Section 5: Labels ---

def label_row(s, spy, peak, trough):
    adj = s["adj"]
    pre = adj[adj.index <= peak].iloc[-PRE_DAYS:]
    if len(pre) < MIN_PRE_CLOSES or (peak - pre.index[-1]).days > 7:
        return None
    pre_price = pre.max()
    t12 = trough + pd.DateOffset(months=RECOVERY_MONTHS)
    cap = trough + pd.DateOffset(months=SURVIVAL_CAP_MONTHS)
    dd = adj[(adj.index >= peak) & (adj.index <= trough + pd.DateOffset(months=DRAWDOWN_MONTHS))]
    after = adj[(adj.index >= trough) & (adj.index <= cap)]
    hit = after[after >= pre_price]
    first = hit.index[0] if len(hit) else pd.NaT

    peak_close, _ = close_on(adj, peak)
    end_close, end_date = close_on(adj, t12)
    spy_peak, _ = close_on(spy, peak)
    spy_end, _ = close_on(spy, t12)
    firm_ret = end_close / peak_close - 1
    spy_ret = spy_end / spy_peak - 1
    return {
        "pre_price": pre_price,
        "drawdown": dd.min() / pre_price - 1 if len(dd) else np.nan,
        "low_date": dd.idxmin() if len(dd) else pd.NaT,
        "recovery_date": first,
        "recovered_12m": int(pd.notna(first) and first <= t12),
        "firm_return": firm_ret,
        "spy_return": spy_ret,
        "excess_return": firm_ret - spy_ret,
        "beat_market": int(firm_ret > spy_ret),
        "last_trade": adj.index[-1],
        "ends_early": adj.index[-1] < t12,
        "extreme_move": bool((np.abs(np.log(adj[(adj.index >= peak) & (adj.index <= cap)])
                                     .diff()) > EXTREME).any()),
    }


# --- Section 6: Exit status ---
FORM25 = {"25", "25-NSE"}
FORM15 = {"15-12B", "15-12G", "15-15D"}
ACQUIRED_DAYS = 90
STOP_DAYS = 90                # prices must stop within this many days after the form


def exit_status(events, cik, peak, trough, last_trade, data_end):
    """Returns (status, date, bankruptcy_8k).

    failed: 8-K item 1.03 followed by a Form 25 or 15 within 12 months. Item 1.03 alone
      isn't enough: it is also used for a subsidiary's bankruptcy (EchoStar 2026), for
      buying assets out of one (Luna 2020), and by mistake (Granite 2026, fixed by 8-K/A).
      Bankrupt stocks often keep trading over the counter, so prices don't need to stop.
    acquired: Form 25 within 90 days of an 8-K item 2.01, since acquirers file 2.01 too.
    delisted_other: Form 25 or 15 otherwise.
    For acquired and delisted_other, the stock's prices must stop within 90 days after the
    form. Form 25 is filed per security, so firms delisting a preferred or note series
    (Wells Fargo 2023, Marsh & McLennan 2026) would count otherwise.
    """
    end = trough + pd.DateOffset(months=SURVIVAL_CAP_MONTHS)
    e = events.get(cik)
    if e is None:
        return "none", pd.NaT, False
    gone_all = e[e["form"].isin(FORM25 | FORM15)]["date"]
    e = e[(e["date"] >= peak) & (e["date"] <= end)]
    bankrupt = e[e["form"].str.startswith("8-K") & e["items"].str.contains("1.03", regex=False)]
    had_8k = len(bankrupt) > 0
    for date in bankrupt["date"].sort_values():
        if ((gone_all >= date - pd.Timedelta(days=30))
                & (gone_all <= date + pd.Timedelta(days=365))).any():
            return "failed", date, True
    # Prices must really stop, not just run to the end of the download
    stopped = last_trade < data_end - pd.Timedelta(days=7)
    stops = e[stopped & (last_trade <= e["date"] + pd.Timedelta(days=STOP_DAYS))]
    f25 = stops[stops["form"].isin(FORM25)]
    deal = e[e["form"].str.startswith("8-K") & e["items"].str.contains("2.01", regex=False)]
    for date in f25["date"].sort_values():
        if (abs(deal["date"] - date).dt.days <= ACQUIRED_DAYS).any():
            return "acquired", date, had_8k
    gone = stops[stops["form"].isin(FORM25 | FORM15)]
    if len(gone):
        return "delisted_other", gone["date"].min(), had_8k
    return "none", pd.NaT, had_8k


def survival(row, trough):
    """Days from the trough to recovery, capped at 18 months.

    Not recovered: failed firms count as never recovering (event 0 at the cap). Every
    other firm whose prices stop is censored at its last trade. delisted_other is
    censored too, since it still holds acquisitions where the target filed no item 2.01
    (Cerner 2022, Mellanox 2020). 04 can treat failures as a competing risk instead.
    """
    cap = trough + pd.DateOffset(months=SURVIVAL_CAP_MONTHS)
    if pd.notna(row["recovery_date"]):
        return (row["recovery_date"] - trough).days, 1
    if row["exit_status"] != "failed" and row["last_trade"] < cap:
        return max((row["last_trade"] - trough).days, 0), 0
    return (cap - trough).days, 0


# --- Section 7: Save and report ---

def main():
    counts = {}
    rows = pd.read_parquet(INTERIM / "price_source.parquet")
    rows = rows[rows["price_source"] != "none"].reset_index(drop=True)
    counts["Matched rows with a checked price"] = rows.groupby("crash").size()

    drop = rows["ticker"].isin(NOT_COMMON)
    print(f"Section 1: dropped {drop.sum()} non-common rows "
          f"({rows.loc[drop, 'ticker'].nunique()} tickers)")
    rows = rows[~drop].reset_index(drop=True)
    counts["Common stock only"] = rows.groupby("crash").size()
    rows["is_adr"] = adr_flags(rows)
    print(f"ADR rows kept and flagged: {rows['is_adr'].sum()}")

    # Section 2 and 3
    spy = load_spy()
    events = {cik: g for cik, g in
              pd.read_parquet(INTERIM / "filing_events.parquet")
              .assign(date=lambda d: pd.to_datetime(d["date"]), items=lambda d: d["items"].fillna(""))
              .groupby("cik")}
    ftd = check.load_ftd(set(rows.loc[rows["price_source"] == "yahoo", "ticker"]))
    splits = load_splits()
    shares = latest_shares(rows["cik"].unique())

    cache, all_fixes, out = {}, [], []
    for row in rows.itertuples():
        key = (row.ticker, row.price_source, row.cik)
        if key not in cache:
            cache[key] = clean_prices(row.ticker, row.price_source, shares.get(row.cik))
        s, fixes = cache[key]
        peak = pd.Timestamp(CRASHES[row.crash]["peak"])
        trough = pd.Timestamp(CRASHES[row.crash]["trough"])
        lo = peak - pd.Timedelta(days=FEATURE_DAYS)
        hi = trough + pd.DateOffset(months=SURVIVAL_CAP_MONTHS)
        in_window = [f for f in fixes if lo <= f["date"] <= hi]
        all_fixes += [{**f, "cik": row.cik, "crash": row.crash} for f in in_window]

        lab = label_row(s, spy, peak, trough)
        base = {"cik": row.cik, "crash": row.crash, "ticker": row.ticker,
                "price_source": row.price_source, "is_adr": row.is_adr}
        if lab is None:
            out.append({**base, "drop": "no pre-crash price"})
            continue
        factor, method, raw_check = raw_factor(s, row.price_source, row.ticker, ftd, splits, peak)
        n_shares = shares_at(shares, row.cik, peak)
        lab.update(base)
        lab.update({
            "pre_price_raw": lab["pre_price"] * factor, "raw_method": method, "raw_check": raw_check,
            "stale_share": stale_share(s, peak),
            "shares_out": n_shares, "market_value": n_shares * lab["pre_price"] * factor,
            "spikes_removed": sum(f["fix"] == "spike_removed" for f in in_window),
            "splits_fixed": sum(f["fix"] == "split_fixed" for f in in_window),
            "split_flagged": any(f["fix"] == "split_flagged" for f in in_window),
        })
        lab["exit_status"], lab["exit_date"], lab["bankruptcy_8k"] = exit_status(
            events, row.cik, peak, trough, lab["last_trade"], spy.index[-1])
        out.append(lab)
    labels = pd.DataFrame(out)
    fixes = pd.DataFrame(all_fixes)

    # Market values known to be wrong: share counts above, and ADRs, whose ordinary share
    # count doesn't match the ADS price. They pass the size filter on price alone.
    bad = pd.Series(list(zip(labels["ticker"], labels["crash"])), index=labels.index).isin(
        SHARE_COUNT_ERRORS) | labels["is_adr"]
    labels.loc[bad, ["shares_out", "market_value"]] = np.nan
    print(f"Market value set to missing: {labels.loc[bad, 'is_adr'].sum()} ADR rows, "
          f"{(bad & ~labels['is_adr']).sum()} hand-checked share counts")

    # Section 4 filter
    no_pre = labels["drop"].eq("no pre-crash price")
    labels = labels[~no_pre].drop(columns="drop")
    counts["Has 20+ closes in the 30 days before the peak"] = labels.groupby("crash").size()
    low_price = labels["pre_price_raw"] < MIN_RAW_PRICE
    small = labels["market_value"] < MIN_MARKET_VALUE  # missing share counts pass
    labels = labels[~low_price]
    counts[f"Pre-crash price at least ${MIN_RAW_PRICE:.0f}"] = labels.groupby("crash").size()
    labels = labels[~small.loc[labels.index]]
    counts[f"Market value at least ${MIN_MARKET_VALUE / 1e6:.0f}M"] = labels.groupby("crash").size()
    labels = labels[~(labels["stale_share"] > MAX_STALE)]
    counts[f"Traded on at least {1 - MAX_STALE:.0%} of days in the year before the peak"] = (
        labels.groupby("crash").size())

    # Market value against the SEC's public float, for the hand check of what's left.
    # Float excludes insiders, and some filers misreport its units, so it only flags rows.
    floats = pd.read_parquet(INTERIM / "universe.parquet")[["cik", "crash", "public_float"]]
    labels = labels.merge(floats, on=["cik", "crash"], how="left")
    labels["value_to_float"] = labels["market_value"] / labels["public_float"].where(labels["public_float"] > 0)

    # Section 5 rules that need the exit status
    failed_first = (labels["exit_status"] == "failed") & (
        labels["recovery_date"].isna() | (labels["exit_date"] < labels["recovery_date"]))
    labels.loc[failed_first, ["recovered_12m"]] = 0
    labels.loc[failed_first, "recovery_date"] = pd.NaT
    labels["exit_before_recovery"] = labels["exit_date"].notna() & (
        labels["recovery_date"].isna() | (labels["exit_date"] < labels["recovery_date"]))
    troughs = labels["crash"].map(lambda c: pd.Timestamp(CRASHES[c]["trough"]))
    surv = [survival(r, t) for (_, r), t in zip(labels.iterrows(), troughs)]
    labels["recovery_days"] = [d for d, _ in surv]
    labels["recovered_event"] = [e for _, e in surv]

    cols = ["cik", "crash", "ticker", "price_source", "is_adr",
            "pre_price", "pre_price_raw", "raw_method", "raw_check", "shares_out", "market_value",
            "value_to_float", "stale_share",
            "drawdown", "low_date", "recovered_12m", "recovery_date", "recovery_days",
            "recovered_event", "firm_return", "spy_return", "excess_return", "beat_market",
            "exit_status", "exit_date", "bankruptcy_8k", "exit_before_recovery", "last_trade", "ends_early",
            "spikes_removed", "splits_fixed", "split_flagged", "extreme_move"]
    labels = labels[cols].sort_values(["crash", "cik"]).reset_index(drop=True)
    ints = ["recovered_12m", "beat_market", "spikes_removed", "splits_fixed"]
    labels[ints] = labels[ints].astype(int)
    labels[["is_adr", "ends_early", "bankruptcy_8k"]] = labels[
        ["is_adr", "ends_early", "bankruptcy_8k"]].astype(bool)
    PROCESSED.mkdir(exist_ok=True)
    labels.to_parquet(PROCESSED / "labels.parquet", index=False)
    fixes.to_csv(INTERIM / "price_fixes.csv", index=False)
    count_table = pd.DataFrame(counts).T[list(CRASHES)]
    count_table.to_csv(INTERIM / "label_counts.csv", index_label="step")

    report(labels, fixes, count_table, cache, shares)


def report(labels, fixes, count_table, cache, shares):
    by = labels.groupby("crash")
    print("\nRows kept at each step:")
    print(count_table.to_string())
    print("\nPrice fixes inside the windows used (rows):")
    print(pd.crosstab(fixes["fix"], [fixes["crash"], fixes["price_source"]]).to_string()
          if len(fixes) else "none")
    print("\nRows with a move above 3x left after cleaning:")
    print(pd.crosstab(labels["extreme_move"], [labels["crash"], labels["price_source"]]).to_string())
    print("\nKnown cases (whole series, both sources where present):")
    for t, cik in [("AAMCF", "0001555074"), ("ABTS", "0001516805"), ("AFIIQ", "0001655075")]:
        for src in ["yahoo", "tiingo"]:
            if (PRICE_DIR / src / f"{t}.parquet").exists():
                _, f = cache.get((t, src, cik)) or clean_prices(t, src, shares.get(cik))
                kinds = pd.Series([x["fix"] for x in f]).value_counts().to_dict()
                big = [(x["date"].date(), round(x["ratio"], 3)) for x in f if x["fix"] != "spike_removed"]
                print(f"  {t} {src}: {kinds} splits: {big}")

    print("\nBase rates and medians:")
    print(by.agg(rows=("cik", "size"), recovered_12m=("recovered_12m", "mean"),
                 beat_market=("beat_market", "mean"), drawdown=("drawdown", "median"),
                 spy_return=("spy_return", "first"), recovered_event=("recovered_event", "mean"),
                 ends_early=("ends_early", "mean")).round(3).to_string())
    print("\nExit status:")
    print(pd.crosstab(labels["exit_status"], labels["crash"], margins=True).to_string())
    print("\nRecovered (12m) by exit status:")
    print(labels.pivot_table(index="exit_status", columns="crash", values="recovered_12m",
                             aggfunc="mean").round(3).to_string())
    print("\nHow the raw price was found, and whether split history and fails prices agree:")
    print(pd.crosstab(labels["raw_method"], labels["raw_check"], margins=True).to_string())
    print(f"share count missing: {labels['shares_out'].isna().mean():.1%}; "
          f"market value above 20x public float: {(labels['value_to_float'] > 20).sum():,} rows")
    tariff = labels[(labels["crash"] == "tariff_2025") & (labels["exit_status"] == "none")]
    cap = pd.Timestamp(CRASHES["tariff_2025"]["trough"]) + pd.DateOffset(months=SURVIVAL_CAP_MONTHS)
    print(f"2025 cap date {cap.date()}: {(tariff['last_trade'] >= cap).mean():.1%} of still-listed "
          "rows trade through it")


if __name__ == "__main__":
    main()
