# Build the list of candidate firms for each crash and record what each filter removes.
# Uses SEC data as the starting list so that firms that later died stay in.
# python 3.14.10, pandas 2.3.3
# Output: data/interim/universe.parquet, filter_counts.csv, filing_events.parquet
import json
import re
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from config import CRASHES, INTERIM, SEC_DIR

MAX_10K_AGE_DAYS = 550  # latest 10-K must end within about 18 months of the peak
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "10-K405", "10-KSB"}
SPAC_SIC = "6770"
# Asset-backed issuers, commodity pools and investment funds (checked against the data)
FUND_SICS = {"6189", "6221", "6722", "6726"}
# Other firms also use these tags (nuclear decommissioning trusts, client funds),
# so a SPAC must hold most of its assets in trust
# The plain AssetsHeldInTrust tag is left out because banks use it for client trust assets
SPAC_TAGS = {"AssetsHeldInTrustNoncurrent", "AssetsHeldInTrustCurrent"}
SPAC_TRUST_SHARE = 0.5
NOT_SPAC_NAMES = {"parkway acquisition corp."}  # a bank holding company
SPAC_NAME = re.compile(r"\b(acquisition|merger)\s+(corp|co\b|company|inc|ltd|limited)|blank check", re.I)
# 8-K items: 1.03 bankruptcy, 2.01 completed acquisition or sale, 3.01 delisting notice
EVENT_ITEMS = {"1.03", "2.01", "3.01"}


def filing_events(sub):
    """Delisting-related filings for one company."""
    tables = [sub["filings"]["recent"]] + sub.get("older_pages", [])
    events = []
    for t in tables:
        for form, date, items in zip(t["form"], t["filingDate"], t["items"]):
            if form.startswith(("25", "15")):
                events.append((form, date, ""))
            elif form.startswith("8-K"):
                hits = EVENT_ITEMS.intersection(items.split(","))
                if hits:
                    events.append((form, date, ",".join(sorted(hits))))
    return events


def name_at(sub, date):
    """Company name on a given date, since SPACs rename after merging."""
    for former in sub.get("formerNames") or []:
        if former.get("from", "")[:10] <= date <= former.get("to", "")[:10]:
            return former["name"]
    return sub.get("name") or ""


def latest_before(rows, peak):
    """Latest-filed fact known before the peak."""
    known = [r for r in rows if r["filed"] < peak]
    return max(known, key=lambda r: (r["filed"], r["end"])) if known else None


def process(names):
    rows, events = [], []
    with zipfile.ZipFile(SEC_DIR / "companyfacts.zip") as z:
        for name in names:
            facts = json.loads(z.read(name)).get("facts", {})
            sub = json.loads((SEC_DIR / "submissions" / name).read_text())
            cik = name[3:13]
            gaap = facts.get("us-gaap", {})
            assets = gaap.get("Assets", {}).get("units", {}).get("USD", [])
            annual = [r for r in assets if r.get("form") in ANNUAL_FORMS]
            floats = (facts.get("dei", {}).get("EntityPublicFloat", {})
                      .get("units", {}).get("USD", []))
            trust = [r for t in SPAC_TAGS
                     for r in gaap.get(t, {}).get("units", {}).get("USD", [])]
            for form, date, items in filing_events(sub):
                events.append((cik, form, date, items))
            for crash, c in CRASHES.items():
                peak = c["peak"]
                last = latest_before(annual, peak)
                age = None
                if last:
                    age = (pd.Timestamp(peak) - pd.Timestamp(last["end"])).days
                flt = latest_before(floats, peak)
                # Compare trust and total assets from the same balance sheet
                share = None
                if last and last["val"]:
                    same = [r for r in trust if r["end"] == last["end"] and r["filed"] < peak]
                    if same:
                        share = max(same, key=lambda r: r["filed"])["val"] / last["val"]
                peak_name = name_at(sub, peak)
                rows.append({
                    "cik": cik, "crash": crash, "name": sub.get("name"),
                    "entity_type": sub.get("entityType"), "sic": sub.get("sic") or "",
                    "sic_desc": sub.get("sicDescription") or "",
                    "current_tickers": ",".join(sub.get("tickers") or []),
                    "last_10k_end": last["end"] if last else None,
                    "last_10k_filed": last["filed"] if last else None,
                    "last_10k_age_days": age,
                    "assets": last["val"] if last else None,
                    "public_float": flt["val"] if flt else None,
                    "name_at_peak": peak_name,
                    "trust_share": share,
                    "spac_name": bool(SPAC_NAME.search(peak_name))
                    and peak_name.lower() not in NOT_SPAC_NAMES,
                })
    return rows, events


def main():
    start = time.monotonic()
    with zipfile.ZipFile(SEC_DIR / "companyfacts.zip") as z:
        names = sorted(n for n in z.namelist() if n.startswith("CIK") and n.endswith(".json"))
    batches = [names[i:i + 250] for i in range(0, len(names), 250)]
    rows, events = [], []
    with ProcessPoolExecutor(max_workers=8) as pool:
        for r, e in pool.map(process, batches):
            rows += r
            events += e
    df = pd.DataFrame(rows)
    INTERIM.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(events, columns=["cik", "form", "date", "items"]).to_parquet(
        INTERIM / "filing_events.parquet", index=False)

    # Multi-class firms such as Fox can report no usable float, so a current ticker for
    # common stock also counts. Dashes mark preferred shares. The ticker step removes
    # remaining debt and preferred tickers.
    common = df["current_tickers"].str.split(",").map(
        lambda ts: any(t and "-" not in t for t in ts))
    # Filters apply in order, so each count shows what that filter alone removed
    filters = [
        ("Has a 10-K filed before the peak", df["last_10k_end"].notna()),
        ("Latest 10-K is recent", df["last_10k_age_days"] <= MAX_10K_AGE_DAYS),
        ("Not a SPAC (SIC 6770)", df["sic"] != SPAC_SIC),
        ("Not a SPAC (most assets in trust)", ~(df["trust_share"] >= SPAC_TRUST_SHARE)),
        ("Not a SPAC (name at peak)", ~df["spac_name"]),
        ("Not a fund or asset-backed issuer", ~df["sic"].isin(FUND_SICS)),
        ("Public float above zero, or a common ticker", (df["public_float"].fillna(0) > 0) | common),
    ]
    counts = [{"step": "All companies", **df.groupby("crash").size().to_dict()}]
    keep = pd.Series(True, index=df.index)
    for label, mask in filters:
        keep &= mask
        counts.append({"step": label, **df[keep].groupby("crash").size().to_dict()})
    counts = pd.DataFrame(counts)
    counts.to_csv(INTERIM / "filter_counts.csv", index=False)

    # Keep everything, with the outcome, so the filters can be audited
    df["in_universe"] = keep
    df.to_parquet(INTERIM / "candidates_all.parquet", index=False)

    uni = df[keep].copy()
    uni.to_parquet(INTERIM / "universe.parquet", index=False)
    print(counts.to_string(index=False))
    print(f"\nrows = {len(uni):,}, unique firms = {uni['cik'].nunique():,}, "
          f"no current ticker = {(uni['current_tickers'] == '').mean():.1%}, "
          f"no SIC = {(uni['sic'] == '').sum():,}, {time.monotonic() - start:.0f} s")


if __name__ == "__main__":
    main()
