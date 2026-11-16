# Checks on the final table, run after 07. Each check is a bug class found in the
# 2026-11-08 audit, so a rerun can't quietly bring one back.
# python 3.14.10, pandas 2.3.3, numpy 2.5.4
# Usage: python check_data.py
# Output: data/interim/data_checks.csv (one row per check), plus rows to review by hand
#         in data/interim/review_identity.csv and review_market_value.csv
import importlib
import warnings

import numpy as np
import pandas as pd

from config import CRASHES, INTERIM, PROCESSED

warnings.filterwarnings("ignore", message=".*generic.*unit.*", category=DeprecationWarning)
match = importlib.import_module("04_match_tickers")
labels_step = importlib.import_module("06_build_labels")

FEATURES = ["current_ratio", "cash_to_assets", "debt_to_assets", "liabilities_to_assets",
            "interest_coverage", "net_margin", "operating_margin", "return_on_assets",
            "ocf_to_assets", "revenue_growth", "asset_growth", "log_assets",
            "log_market_value", "volatility_12m", "momentum_12_1", "beta"]
REVIEW_SCORE = 0.6     # name similarity below this goes to the identity review list
REVIEW_FLOAT = 20      # market value above this multiple of public float goes to review


def identity_scores(f):
    """Similarity between each firm's name at the peak and the fails name of its ticker at
    the peak. Missing when the fails data doesn't show the ticker then."""
    uni = pd.read_parquet(INTERIM / "universe.parquet")[["cik", "crash", "name_at_peak"]]
    f = f.merge(uni, on=["cik", "crash"], how="left")
    by_symbol = {s: g for s, g in pd.read_parquet(INTERIM / "ftd_symbols.parquet").groupby("symbol")}
    scores, descs = [], []
    for r in f.itertuples():
        peak = pd.Timestamp(CRASHES[r.crash]["peak"])
        g = match.at_peak(by_symbol, r.ticker, peak)
        if g is None:
            scores.append(np.nan)
            descs.append("")
            continue
        names = match.names_in_use(*match.firm_names(r.cik), peak) + [r.name_at_peak]
        s = [max(match.name_score(n, d) for n in names) for d in g["description"]]
        scores.append(max(s))
        descs.append(g["description"].iloc[int(np.argmax(s))])
    return f.assign(id_score=scores, id_desc=descs)


def main():
    f = pd.read_parquet(PROCESSED / "firm_crash.parquet")
    peaks = f["crash"].map(lambda c: pd.Timestamp(CRASHES[c]["peak"]))
    checks = []

    def check(name, bad, note=""):
        n = int(np.sum(bad))
        checks.append({"check": name, "rows_failing": n, "note": note})
        print(f"{'ok  ' if n == 0 else 'FAIL'} {name}: {n}" + (f" ({note})" if note else ""))

    print("Structure")
    check("one row per firm and crash", f.duplicated(["cik", "crash"]))
    check("one firm per ticker in a crash", f.duplicated(["crash", "ticker"]))

    print("\nFilters")
    check("raw pre-crash price at least $1", f["pre_price_raw"] < labels_step.MIN_RAW_PRICE)
    check("market value at least $10M where known", f["market_value"] < labels_step.MIN_MARKET_VALUE)
    check("stale share at most 30%", f["stale_share"] > labels_step.MAX_STALE)
    check("no blank SIC", f["sic"].fillna("").str.strip().eq(""))

    print("\nLabels")
    check("drawdown not positive", f["drawdown"] > 0)
    check("recovery time not negative", f["recovery_days"] < 0)
    check("recovered within 12 months means at most about 366 days",
          (f["recovered_12m"] == 1) & (f["recovery_days"] > 366))
    check("failed before recovering means not recovered",
          (f["exit_status"] == "failed") & (f["recovered_12m"] == 1)
          & (f["exit_date"] < f["recovery_date"]))
    check("beat_market matches the returns",
          f["beat_market"] != (f["firm_return"] > f["spy_return"]).astype(int))

    print("\nFeatures")
    check("growth missing for recent SPAC mergers",
          f["recent_spac"] & (f["revenue_growth"].notna() | f["asset_growth"].notna()))
    fin = pd.to_numeric(f["sic"], errors="coerce").between(6000, 6799)
    check("current ratio and interest coverage missing for financials",
          fin & (f["current_ratio"].notna() | f["interest_coverage"].notna()))
    for col in FEATURES:
        if f"{col}_missing" in f:
            check(f"{col}_missing matches", f[f"{col}_missing"] != f[col].isna().astype(int))
    check("no infinite feature values", np.isinf(f[FEATURES].to_numpy(dtype=float)).any(axis=1))
    check("lowest price is on or after the peak", f["low_date"] < peaks)

    print("\nRaw price and market value")
    print(pd.crosstab(f["raw_method"], f["raw_check"], margins=True).to_string())
    check("split history and fails prices disagree (fails ratio used)", f["raw_check"] == "disagree",
          "kept, fails price is a direct reading")
    big = f[f["value_to_float"] > REVIEW_FLOAT]
    big[["cik", "crash", "name", "ticker", "price_source", "raw_method", "raw_check", "pre_price_raw",
         "shares_out", "market_value", "value_to_float"]].sort_values("value_to_float", ascending=False).to_csv(
        INTERIM / "review_market_value.csv", index=False)
    check(f"market value above {REVIEW_FLOAT}x public float", f["value_to_float"] > REVIEW_FLOAT,
          "listed in review_market_value.csv; float can be misreported, so review by hand")

    print("\nTicker identity")
    scored = identity_scores(f)
    low = scored[scored["id_score"] < REVIEW_SCORE]
    low[["cik", "crash", "name_at_peak", "ticker", "id_desc", "id_score", "price_source"]].sort_values(
        "id_score").to_csv(INTERIM / "review_identity.csv", index=False)
    print(f"identity checked against fails names: {scored['id_score'].notna().mean():.1%} of rows")
    check(f"ticker's fails name at the peak scores below {REVIEW_SCORE}", scored["id_score"] < REVIEW_SCORE,
          "listed in review_identity.csv; mostly renames, review by hand")

    pd.DataFrame(checks).to_csv(INTERIM / "data_checks.csv", index=False)


if __name__ == "__main__":
    main()
