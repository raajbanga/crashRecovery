# Build pre-crash features and join them to the labels: the table the notebooks load.
# python 3.14.10, pandas 2.3.3, numpy 2.5.4
#
# Section 1: Point-in-time SEC facts
# Section 2: Features
# Section 3: Checks and save
#
# Inputs: data/processed/labels.parquet, data/interim/universe.parquet,
#         data/raw/sec/companyfacts.zip, the price files (cleaned by 06)
# Output: data/processed/firm_crash.parquet, data/interim/feature_coverage.csv
import importlib
import json
import warnings
import zipfile

import numpy as np
import pandas as pd

from config import CRASHES, INTERIM, PROCESSED, SEC_DIR

labels_step = importlib.import_module("06_build_labels")
universe_step = importlib.import_module("03_build_universe")
warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)

MAX_AGE = 550          # days from a fact's period end to the peak; older facts are stale
ANNUAL = (340, 380)    # days in a full-year flow
YEAR_GAP = (350, 380)  # days between a period and the same period a year earlier
SPAC_DAYS = 400        # a SPAC merger this close before the peak breaks growth features

# --- Section 1: Point-in-time SEC facts ---
# Tags in fallback order. Per row, the tag with the latest period end wins; ties go to
# the earlier tag, since firms switch tags over time (SalesRevenueNet before 2018).
INSTANT_TAGS = {
    "assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "liabilities": ["Liabilities"],
    "liabilities_and_equity": ["LiabilitiesAndStockholdersEquity"],
    "equity": ["StockholdersEquity"],
    "equity_with_nci": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "lt_debt": ["LongTermDebt"],
    "lt_debt_noncurrent": ["LongTermDebtNoncurrent"],
    "debt_current": ["LongTermDebtCurrent", "DebtCurrent"],
    "trust": sorted(universe_step.SPAC_TAGS),  # SPAC trust account, for the year-earlier check
}
FLOW_TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet"],
    "net_income": ["NetIncomeLoss"],
    "operating_income": ["OperatingIncomeLoss"],
    "interest_expense": ["InterestExpense"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
}


def load_facts(z, cik):
    """USD facts per tag, as a frame with start, end, val, filed (dates)."""
    try:
        gaap = json.loads(z.read(f"CIK{cik}.json")).get("facts", {}).get("us-gaap", {})
    except KeyError:
        return {}
    wanted = {t for tags in (*INSTANT_TAGS.values(), *FLOW_TAGS.values()) for t in tags}
    out = {}
    for tag in wanted & set(gaap):
        rows = gaap[tag].get("units", {}).get("USD", [])
        if not rows:
            continue
        f = pd.DataFrame(rows)
        if "start" not in f:
            f["start"] = None
        f = f[["start", "end", "val", "filed"]].copy()
        for c in ("start", "end", "filed"):
            f[c] = pd.to_datetime(f[c], errors="coerce")
        out[tag] = f.dropna(subset=["end", "filed", "val"])
    return out


def known_at(f, peak):
    """Facts filed before the peak, one value per period: the latest one filed then.
    A restatement filed after the peak can't leak in."""
    f = f[(f["filed"] < peak) & (f["end"] < peak)]
    return f.sort_values("filed").groupby(["start", "end"], dropna=False).tail(1)


def instant_value(f, peak, offset_days=0):
    """Balance-sheet value at the latest period end (or about a year before it)."""
    f = known_at(f, peak)
    if f.empty:
        return None
    latest = f["end"].max()
    if offset_days:
        target = latest - pd.Timedelta(days=offset_days)
        f = f[(f["end"] - target).abs() <= pd.Timedelta(days=45)]
        if f.empty:
            return None
        row = f.loc[(f["end"] - target).abs().idxmin()]
    else:
        row = f[f["end"] == latest].sort_values("filed").iloc[-1]
    return row["val"], row["end"], row["filed"]


def flow_value(f, peak, offset_days=0):
    """Trailing 12-month value: last full year + this year to date - the same period a
    year earlier. Falls back to the last full year. Periods come from start and end,
    not fy and fp, which describe the filing."""
    f = known_at(f, peak).dropna(subset=["start"])
    if f.empty:
        return None
    f = f.assign(days=(f["end"] - f["start"]).dt.days)
    if offset_days:
        # The value about a year before: the full year ending a year before the latest
        f = f[f["end"] <= f["end"].max() - pd.Timedelta(days=offset_days - 30)]
        if f.empty:
            return None
    annual = f[f["days"].between(*ANNUAL)]
    latest = f["end"].max()
    ytd = f[(f["end"] == latest) & (f["days"] < ANNUAL[0])]
    if not ytd.empty and not annual.empty:
        cur = ytd.sort_values("days").iloc[-1]  # longest year-to-date period
        fy = annual[(annual["end"] < cur["start"])
                    & (annual["end"] >= cur["start"] - pd.Timedelta(days=10))]
        gap = (cur["end"] - f["end"]).dt.days
        prior = f[gap.between(*YEAR_GAP) & (f["days"] - cur["days"]).abs().le(10)]
        if not fy.empty and not prior.empty:
            fy, prior = fy.iloc[-1], prior.iloc[-1]
            val = fy["val"] + cur["val"] - prior["val"]
            return val, cur["end"], max(fy["filed"], cur["filed"], prior["filed"])
    if annual.empty:
        return None
    row = annual.sort_values(["end", "filed"]).iloc[-1]
    return row["val"], row["end"], row["filed"]


def pick(facts, tags, peak, kind, offset_days=0):
    """First-choice tag with the latest period end. Returns (value, end, filed, tag)."""
    best = None
    for tag in tags:
        if tag not in facts:
            continue
        got = (instant_value if kind == "instant" else flow_value)(facts[tag], peak, offset_days)
        if got is None or (peak - got[1]).days > MAX_AGE + offset_days:
            continue
        if best is None or got[1] > best[1]:
            best = (*got, tag)
    return best


def sec_inputs(rows):
    """One row per firm-crash with each raw input, plus the latest filed date used."""
    out = []
    with zipfile.ZipFile(SEC_DIR / "companyfacts.zip") as z:
        for cik, group in rows.groupby("cik"):
            facts = load_facts(z, cik)
            for crash in group["crash"]:
                peak = pd.Timestamp(CRASHES[crash]["peak"])
                rec = {"cik": cik, "crash": crash}
                filed = []
                for name, tags in INSTANT_TAGS.items():
                    got = pick(facts, tags, peak, "instant")
                    rec[name] = got[0] if got else np.nan
                    filed += [got[2]] if got else []
                for name, tags in FLOW_TAGS.items():
                    got = pick(facts, tags, peak, "flow")
                    rec[name] = got[0] if got else np.nan
                    filed += [got[2]] if got else []
                # A year earlier, for growth
                for name, tags, kind in [("assets", INSTANT_TAGS["assets"], "instant"),
                                         ("revenue", FLOW_TAGS["revenue"], "flow"),
                                         ("trust", INSTANT_TAGS["trust"], "instant")]:
                    got = pick(facts, tags, peak, kind, offset_days=365)
                    rec[f"{name}_prior"] = got[0] if got else np.nan
                    filed += [got[2]] if got else []
                rec["last_filed_used"] = max(filed) if filed else pd.NaT
                out.append(rec)
    return pd.DataFrame(out)


# --- Section 2: Features ---
SIC_DIVISIONS = [  # (first 2-digit code, last, name)
    (1, 9, "Agriculture"), (10, 14, "Mining"), (15, 17, "Construction"),
    (20, 39, "Manufacturing"), (40, 49, "Transport and utilities"), (50, 51, "Wholesale"),
    (52, 59, "Retail"), (60, 67, "Finance"), (70, 89, "Services"), (91, 99, "Public admin"),
]


def sic_division(sic):
    try:
        two = int(str(sic)[:4].zfill(4)[:2])
    except ValueError:
        return "Unknown"
    for lo, hi, name in SIC_DIVISIONS:
        if lo <= two <= hi:
            return name
    return "Unknown"


def ratio(a, b, positive=True):
    """a / b, missing when b is missing, zero, or (for positive=True) negative."""
    b = b.where(b > 0) if positive else b.where(b != 0)
    return a / b


def financial_features(d):
    debt = d["lt_debt"].fillna(d["lt_debt_noncurrent"] + d["debt_current"].fillna(0))
    f = pd.DataFrame(index=d.index)
    f["current_ratio"] = ratio(d["current_assets"], d["current_liabilities"])
    f["cash_to_assets"] = ratio(d["cash"], d["assets"])
    f["debt_to_assets"] = ratio(debt, d["assets"])
    # Many firms tag only total liabilities and equity, so back out liabilities from it
    equity = d["equity_with_nci"].fillna(d["equity"])
    liabilities = d["liabilities"].fillna(d["liabilities_and_equity"] - equity)
    f["liabilities_to_assets"] = ratio(liabilities, d["assets"])
    f["interest_coverage"] = ratio(d["operating_income"], d["interest_expense"])
    f["net_margin"] = ratio(d["net_income"], d["revenue"])
    f["operating_margin"] = ratio(d["operating_income"], d["revenue"])
    f["return_on_assets"] = ratio(d["net_income"], d["assets"])
    f["ocf_to_assets"] = ratio(d["operating_cash_flow"], d["assets"])
    f["revenue_growth"] = ratio(d["revenue"], d["revenue_prior"]) - 1
    f["asset_growth"] = ratio(d["assets"], d["assets_prior"]) - 1
    f["log_assets"] = np.log(d["assets"].where(d["assets"] > 0))
    return f


def recent_spac(d):
    """Firms that merged with a SPAC shortly before the peak. Their year-earlier balance
    sheet is the SPAC shell, so growth compares the company with a trust account (asset
    growth up to 3,577x). Two signs: a SPAC name dropped within SPAC_DAYS before the peak
    (the name rule from 03), or a year-earlier balance sheet mostly held in trust."""
    names = []
    for cik, crash in zip(d["cik"], d["crash"]):
        peak = pd.Timestamp(CRASHES[crash]["peak"])
        sub = json.loads((SEC_DIR / "submissions" / f"CIK{cik}.json").read_text())
        hit = False
        for f in sub.get("formerNames") or []:
            end = pd.Timestamp(f.get("to", "")[:10]) if f.get("to") else None
            if end is not None and peak - pd.Timedelta(days=SPAC_DAYS) <= end <= peak:
                hit |= bool(universe_step.SPAC_NAME.search(f["name"]))
        names.append(hit)
    trust = (d["trust_prior"] / d["assets_prior"].where(d["assets_prior"] > 0)
             >= universe_step.SPAC_TRUST_SHARE)
    return pd.Series(names, index=d.index) | trust


def price_features(rows, shares):
    """Volatility, momentum, and beta from prices up to the peak only."""
    spy = labels_step.load_spy()
    spy_r = np.log(spy).diff()
    cache, out = {}, []
    for row in rows.itertuples():
        key = (row.ticker, row.price_source, row.cik)
        if key not in cache:
            cache[key] = labels_step.clean_prices(row.ticker, row.price_source,
                                                  shares.get(row.cik))[0]["adj"]
        peak = pd.Timestamp(CRASHES[row.crash]["peak"])
        p = cache[key][cache[key].index <= peak].iloc[-253:]
        r = np.log(p).diff().dropna()
        rec = {"cik": row.cik, "crash": row.crash, "last_price_date": p.index[-1],
               "volatility_12m": np.nan, "momentum_12_1": np.nan, "beta": np.nan}
        if len(r) >= 120:
            rec["volatility_12m"] = r.std() * np.sqrt(252)
            both = pd.concat({"f": r, "m": spy_r}, axis=1, join="inner").dropna()
            if len(both) >= 120:
                rec["beta"] = both.cov().loc["f", "m"] / both["m"].var()
        if len(p) >= 253:
            rec["momentum_12_1"] = p.iloc[-22] / p.iloc[0] - 1
        out.append(rec)
    return pd.DataFrame(out)


# --- Section 3: Checks and save ---
FEATURES = ["current_ratio", "cash_to_assets", "debt_to_assets", "liabilities_to_assets",
            "interest_coverage", "net_margin", "operating_margin", "return_on_assets",
            "ocf_to_assets", "revenue_growth", "asset_growth", "log_assets",
            "log_market_value", "volatility_12m", "momentum_12_1", "beta"]
NOT_FOR_FINANCIALS = ["current_ratio", "interest_coverage"]  # deposits, interest as cost


def main():
    labels = pd.read_parquet(PROCESSED / "labels.parquet")
    universe = pd.read_parquet(INTERIM / "universe.parquet")[["cik", "crash", "name", "sic"]]
    rows = labels[["cik", "crash", "ticker", "price_source"]]

    print("Section 1: reading SEC facts...", flush=True)
    sec = sec_inputs(rows)
    print("Section 2: price features...", flush=True)
    shares = labels_step.latest_shares(rows["cik"].unique())
    prices = price_features(rows, shares)

    d = labels.merge(universe, on=["cik", "crash"], how="left")
    # Blank SIC rows are business development companies (Ares Capital, Prospect), which
    # are funds. 03 removes funds by SIC, so they slipped in, and only in 2025.
    blank = d["sic"].fillna("").str.strip().eq("")
    print(f"Dropped {blank.sum()} rows with a blank SIC (BDCs): "
          f"{d.loc[blank, 'crash'].value_counts().to_dict()}")
    d = d[~blank].reset_index(drop=True)
    d = d.merge(sec, on=["cik", "crash"], how="left").merge(prices, on=["cik", "crash"], how="left")
    feats = financial_features(d)
    feats["log_market_value"] = np.log(d["market_value"].where(d["market_value"] > 0))
    d = pd.concat([d, feats], axis=1)
    d["sic_division"] = d["sic"].map(sic_division)
    d["is_financial"] = pd.to_numeric(d["sic"], errors="coerce").between(6000, 6799).astype(int)
    d.loc[d["is_financial"] == 1, NOT_FOR_FINANCIALS] = np.nan
    d["recent_spac"] = recent_spac(d)
    d.loc[d["recent_spac"], ["revenue_growth", "asset_growth"]] = np.nan  # decided 2026-11-08
    print(f"Recent SPAC mergers, growth set to missing: "
          f"{d.groupby('crash')['recent_spac'].sum().to_dict()}")

    # Leakage test: nothing filed or priced after the peak
    peaks = d["crash"].map(lambda c: pd.Timestamp(CRASHES[c]["peak"]))
    assert (d["last_filed_used"].isna() | (d["last_filed_used"] < peaks)).all(), "fact filed after peak"
    assert (d["last_price_date"] <= peaks).all(), "price after peak"

    for col in FEATURES:
        if d[col].isna().any():
            d[f"{col}_missing"] = d[col].isna().astype(int)

    label_cols = [c for c in labels.columns if c not in ("cik", "crash", "ticker", "price_source")]
    keep = (["cik", "crash", "name", "ticker", "price_source", "sic", "sic_division",
             "is_financial", "recent_spac"] + label_cols + FEATURES
            + [c for c in d.columns if c.endswith("_missing")])
    out = d[keep].sort_values(["crash", "cik"]).reset_index(drop=True)
    out.to_parquet(PROCESSED / "firm_crash.parquet", index=False)

    coverage = out.groupby("crash")[FEATURES].apply(lambda g: g.notna().mean()).T.round(3)
    coverage.to_csv(INTERIM / "feature_coverage.csv", index_label="feature")
    print(f"\nSaved {len(out):,} rows, {out.shape[1]} columns")
    print("\nShare of rows with each feature:")
    print(coverage.to_string())
    print("\nShare of financial firms:", out.groupby("crash")["is_financial"].mean().round(3).to_dict())
    print("\nSIC divisions:")
    print(pd.crosstab(out["sic_division"], out["crash"]).to_string())
    print("\nFeature medians by crash:")
    print(out.groupby("crash")[FEATURES].median().T.round(3).to_string())


if __name__ == "__main__":
    main()
