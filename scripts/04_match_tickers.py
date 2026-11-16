# Link each firm in each crash to the ticker that has its price history at the peak.
# Source 1: the SEC's current ticker for the firm.
# Source 2: company names matched to fails-to-deliver files around the peak date,
#           following the CUSIP through later tickers (HTZ to HTZGQ).
# A ticker counts only if Tiingo's list shows it trading before and at the peak.
# Identity check: tickers get reused, so a ticker whose fails name at the peak is clearly
# another company is skipped, and a ticker two firms claim goes to the one whose name at
# the peak matches (Ambac's current ticker OSG belonged to Overseas Shipholding in 2020).
# python 3.14.10, pandas 2.3.3
# Output: data/interim/ticker_map.parquet
import json
import re
import zipfile
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from config import CRASHES, INTERIM, PRICE_DIR, SEC_DIR

MIN_DAYS_BEFORE_PEAK = 30
FTD_WINDOW = pd.Timedelta(days=270)  # fails are sparse, so allow a margin around the peak
MIN_KEY_LEN = 3  # short names (CIT, DISH) only ever match exactly
PREFIX_LEN = 6
MIN_KEY_OVERLAP = 0.75  # shorter name must be most of the longer (Paramount vs Paramount Global)
FTD_NAME_LIMIT = 28  # fails descriptions cut off at 30 characters, so long ones may be partial
# Share classes such as BRK-B count as common stock. Preferred shares look like ATH-PA.
COMMON_TICKER = re.compile(r"[A-Z]{1,5}(-[A-OQ-Z])?")
# Five-letter tickers ending in these letters are usually notes, preferred, units or warrants
NOT_COMMON_TICKER = re.compile(r"[A-Z]{4}[LMNOPRUWZ]")
COMMON_EXCEPTIONS = {"GOOGL"}


def is_common(ticker):
    if ticker in COMMON_EXCEPTIONS:
        return True
    return bool(COMMON_TICKER.fullmatch(ticker)) and not NOT_COMMON_TICKER.fullmatch(ticker)
LIVE_MARGIN = pd.Timedelta(days=7)
ACTIVE = pd.Timedelta(days=30)  # fails entries this close to the peak show who owned a ticker
SAME_FIRM = 0.6  # name similarity at or above this counts as the same company
# Firms checked by hand that the name rules can't reach
MANUAL = {
    "0001618921": "WBA",   # fails name is misspelled "WALGREEN BOOTS ALLIANCE"
    "0000813828": "PARA",  # fails name is misspelled "PARAMOUNT GOBAL"
    "0000801337": "WBS",   # fails name adds "WATERBURY CN"
}

DROP_WORDS = set("""INC INCORPORATED CORP CORPORATION CO COMPANY LTD LIMITED LLC LP PLC
    HOLDINGS HLDGS HLDG HOLDING GROUP GRP THE COM STK STOCK COMMON NEW CL CLASS A SHS SH
    DE MD NV CAL ORD""".split())
NOT_COMMON = re.compile(
    r"\b(?:PFD|PREF|PREFERRED|WT|WTS|WARRANT|WARRANTS|RIGHT|RIGHTS|RTS|UNIT|UNITS|NOTE|NOTES"
    r"|DEB|ETF|FD|FUND|DEP|DEPOSITARY)\b")


# Security wording that follows the company name in fails descriptions. NEW only counts
# at the end ("CORP NEW", or cut off as "NEW C"), since it also starts names
# ("BLACKROCK NEW YORK MUNICIPAL").
SECURITY_TAIL = re.compile(
    r"\s+(?:(?:COM|COMMON|ORD|ORDINARY|CL|CL-[A-Z]|CLASS|SHS|SHARES|STK|PAR|REIT|ADR)\b"
    r"|NEW(?:\s+C[A-Z]*)?$|\().*$")
ABBREVIATIONS = {
    "FINL": "FINANCIAL", "FIN": "FINANCIAL", "PTNRS": "PARTNERS", "PARTNERSHIP": "PARTNERS",
    "BK": "BANK", "BANCSHS": "BANCSHARES", "BKS": "BANKS", "RES": "RESOURCES",
    "INTL": "INTERNATIONAL", "SVCS": "SERVICES", "SVC": "SERVICE", "SYS": "SYSTEMS",
    "TECHNOLOGY": "TECH", "TECHNOLOGIES": "TECH", "TECHS": "TECH",
    "PHARMACEUTICALS": "PHARMA", "PHARMACEUTICAL": "PHARMA", "MGMT": "MANAGEMENT",
    "TR": "TRUST", "ENTMT": "ENTERTAINMENT", "PPTYS": "PROPERTIES", "MTG": "MORTGAGE",
    "AMER": "AMERICAN", "NATL": "NATIONAL", "UTD": "UNITED", "INDS": "INDUSTRIES",
    "LABS": "LABORATORIES", "ENERGY": "ENERGY", "SOLUTIONS": "SOLUTIONS",
}


def name_key(name):
    words = re.sub(r"[^A-Z0-9 ]", " ", name.upper()).split()
    return "".join(ABBREVIATIONS.get(w, w) for w in words if w not in DROP_WORDS)


def ftd_key(description):
    return name_key(SECURITY_TAIL.sub("", description.upper()))


def load_tiingo():
    with zipfile.ZipFile(PRICE_DIR / "supported_tickers.zip") as z:
        df = pd.read_csv(z.open(z.namelist()[0]), dtype=str, keep_default_na=False)
    df = df[(df["assetType"] == "Stock") & (df["priceCurrency"] == "USD")].copy()
    df["start"] = pd.to_datetime(df["startDate"], errors="coerce")
    df["end"] = pd.to_datetime(df["endDate"], errors="coerce")
    df = df.dropna(subset=["start", "end"])
    latest = df["end"].max()
    index = {}
    for row in df.itertuples():
        index.setdefault(row.ticker.upper(), []).append((row.start, row.end, row.exchange))
    return index, latest


def covers(index, ticker, peak):
    """Tiingo record for this ticker that spans the peak, if any."""
    need = peak - pd.Timedelta(days=MIN_DAYS_BEFORE_PEAK)
    for start, end, exchange in index.get(ticker, []):
        if start <= need and end >= peak:
            return start, end, exchange
    return None


def firm_names(cik):
    """Current name plus former names with the dates each was used."""
    sub = json.loads((SEC_DIR / "submissions" / f"CIK{cik}.json").read_text())
    former = [(f["name"], pd.Timestamp(f.get("from", "1900-01-01")[:10]), pd.Timestamp(f["to"][:10]))
              for f in sub.get("formerNames") or [] if f.get("to")]
    return sub.get("name") or "", former


def names_in_use(current, former, peak):
    """Names in use around the peak. Old names can belong to unrelated firms later, and a
    name adopted long after the peak can belong to an unrelated firm before it
    (A-Mark, now Gold.com, must not match New Gold)."""
    lo, hi = peak - FTD_WINDOW, peak + FTD_WINDOW
    used = [n for n, start, end in former if end >= lo and start <= hi]
    last = max((end for _, _, end in former), default=None)
    if last is None or last <= hi or not used:
        used.append(current)
    return used


def names_near(current, former, peak):
    return {k for k in map(name_key, names_in_use(current, former, peak)) if len(k) >= MIN_KEY_LEN}


def name_words(name):
    name = SECURITY_TAIL.sub("", name.upper())
    return [ABBREVIATIONS.get(w, w) for w in re.sub(r"[^A-Z0-9 ]", " ", name).split()
            if w not in DROP_WORDS]


def name_score(a, b):
    """Similarity of two company names, 0 to 1. Takes the best of whole-name similarity,
    word-order-free similarity, and the share of words that start the same way, so
    "BLOCK H & R INC" and "H&R BLOCK INC" score high."""
    wa, wb = name_words(a), name_words(b)
    if not wa or not wb:
        return 1.0
    whole = SequenceMatcher(None, "".join(wa), "".join(wb)).ratio()
    unordered = SequenceMatcher(None, "".join(sorted(wa)), "".join(sorted(wb))).ratio()
    shared = len({w[:4] for w in wa} & {w[:4] for w in wb}) / min(len(wa), len(wb))
    return max(whole, unordered, shared)


def at_peak(by_symbol, ticker, peak):
    g = by_symbol.get(ticker)
    if g is None:
        return None
    g = g[(g["first"] <= peak + ACTIVE) & (g["last"] >= peak - ACTIVE)]
    return None if g.empty else g


def owner_score(by_symbol, ticker, names, peak):
    """Best similarity between the firm's names and the ticker's fails names at the peak.
    None if the fails data doesn't show the ticker at the peak."""
    g = at_peak(by_symbol, ticker, peak)
    if g is None:
        return None
    return max(name_score(n, d) for n in names for d in g["description"])


def held_by_other(by_symbol, ticker, cusip, names, peak):
    """True if the fails data shows the ticker under another company at the peak: a
    different issuer code and a different name. Reorganized firms get a new issuer code
    under the same name (TravelCenters of America LLC to Inc.)."""
    g = at_peak(by_symbol, ticker, peak)
    if g is None or (g["cusip"].str[:6] == cusip[:6]).any():
        return False
    return max(name_score(n, d) for n in names for d in g["description"]) < SAME_FIRM


def other_firms_ticker(by_symbol, ticker, names, peak):
    """True if the fails data shows a current ticker belonged to another company at the peak:
    the issuer code (first 6 CUSIP characters) differs from the ticker's latest one, and
    the names don't match. Both are needed: fails names lag renames (U-Haul is still
    "AMERCO"), and a reorganized firm can get a new issuer code."""
    g = at_peak(by_symbol, ticker, peak)
    if g is None:
        return False
    latest = by_symbol[ticker].sort_values("last")["cusip"].iloc[-1][:6]
    if (g["cusip"].str[:6] == latest).any():
        return False
    return max(name_score(n, d) for n in names for d in g["description"]) < SAME_FIRM


def same_name(key, fkey, description):
    """Exact match, or the fails name is a cut-off start of the firm's name.

    A fails name longer than the firm's name is a different company
    (Ashford Inc. is not Ashford Hospitality Trust), so that never matches.
    """
    if key == fkey:
        return True
    if not key.startswith(fkey):
        return False
    # A long description may be cut off mid-name, unless dropped words shrank it to one
    # word ("FRONTIER GROUP HLDGS INC COM" is "FRONTIER", which isn't Frontier Communications)
    cut_off = len(description) >= FTD_NAME_LIMIT and len(name_words(description)) > 1
    return len(fkey) / len(key) >= MIN_KEY_OVERLAP or cut_off


def main():
    uni = pd.read_parquet(INTERIM / "universe.parquet")
    ftd = pd.read_parquet(INTERIM / "ftd_symbols.parquet")
    tiingo, latest = load_tiingo()

    ftd = ftd[~ftd["description"].str.upper().str.contains(NOT_COMMON)
              & ftd["symbol"].str.fullmatch(r"[A-Z]{1,5}")].copy()
    ftd["key"] = ftd["description"].map(ftd_key)
    ftd = ftd[ftd["key"].str.len() >= MIN_KEY_LEN]
    by_prefix = {p: g for p, g in ftd.groupby(ftd["key"].str[:PREFIX_LEN])}
    symbols_by_cusip = ftd.groupby("cusip")["symbol"].agg(set).to_dict()
    by_symbol = {s: g for s, g in pd.read_parquet(INTERIM / "ftd_symbols.parquet").groupby("symbol")}

    names = {cik: firm_names(cik) for cik in uni["cik"].unique()}

    rows = []
    for row in uni.itertuples():
        peak = pd.Timestamp(CRASHES[row.crash]["peak"])
        ticker, source, record, desc, skipped = None, "none", None, None, None
        current, former = names[row.cik]
        # Any name the firm used up to the peak is the same firm, however old
        own = [n for n, start, _ in former if start <= peak] + names_in_use(current, former, peak)

        # Source 1: current SEC ticker, first listed common share, unless the fails data
        # shows it belonged to another company at the peak
        for t in [x for x in row.current_tickers.split(",") if is_common(x)]:
            record = covers(tiingo, t.upper(), peak)
            if record:
                if other_firms_ticker(by_symbol, t.upper(), own, peak):
                    skipped, record = t.upper(), None
                    continue
                ticker, source = t.upper(), "sec_current"
                break

        if not ticker and row.cik in MANUAL:
            record = covers(tiingo, MANUAL[row.cik], peak)
            if record:
                ticker, source = MANUAL[row.cik], "manual"

        # Source 2: name match in fails data near the peak
        if not ticker:
            found = []
            # Fails names often cut REIT ("WHITESTONE REIT COM" is "WHITESTONE"), so try both
            keys = {name_key(n) for name in names_in_use(current, former, peak)
                    for n in [name, re.sub(r"\bREIT\b", "", name, flags=re.I)]}
            for key in keys:
                if len(key) < MIN_KEY_LEN:
                    continue
                group = by_prefix.get(key[:PREFIX_LEN])
                if group is None:
                    continue
                near = group[(group["first"] <= peak + FTD_WINDOW)
                             & (group["last"] >= peak - FTD_WINDOW)]
                found += [r for r in near.itertuples()
                          if same_name(key, r.key, r.description)]
            for r in sorted(found, key=lambda x: -x.days):
                tries = [r.symbol] + sorted(symbols_by_cusip.get(r.cusip, set()) - {r.symbol})
                tries += [s + "Q" for s in tries]
                tries = [t for t in tries if is_common(t) or t.endswith("Q")]
                # A later ticker on the same CUSIP may have been another issuer's at the
                # peak (Ambac's CUSIP now trades as OSG, Overseas Shipholding's in 2020)
                tries = [t for t in tries
                         if not held_by_other(by_symbol, t, r.cusip, own + [r.description], peak)]
                for t in tries:
                    record = covers(tiingo, t, peak)
                    if record:
                        ticker, source, desc = t, "ftd_name", r.description
                        break
                if ticker:
                    break

        start, end, exchange = record if ticker else (None, None, None)
        rows.append({"cik": row.cik, "crash": row.crash, "name": row.name_at_peak,
                     "ticker": ticker, "source": source, "ftd_description": desc,
                     "skipped_other_firm": skipped,
                     "owner_score": owner_score(by_symbol, ticker, [row.name_at_peak], peak) if ticker else None,
                     "exchange": exchange, "price_start": start, "price_end": end,
                     # Only the SEC's current link is expected on Yahoo. The download
                     # step tries Yahoo first and uses Tiingo for whatever is missing.
                     "still_trading": source == "sec_current" and end >= latest - LIVE_MARGIN})
    out = pd.DataFrame(rows)

    # One ticker can't belong to two firms in the same crash. The firm whose name at the
    # peak matches the ticker's fails name wins (the old owner of a reused ticker).
    # Otherwise the SEC's own link wins (a parent over a subsidiary filer). If neither
    # applies, keep neither.
    dup = out["ticker"].notna() & out.duplicated(["crash", "ticker"], keep=False)
    has_sec = (out[out["source"] == "sec_current"]
               .groupby(["crash", "ticker"]).size().rename("n").reset_index())
    out = out.merge(has_sec, how="left", on=["crash", "ticker"])
    sec_wins = (out["source"] == "sec_current") & (out["n"] == 1)
    score = out["owner_score"].astype(float).fillna(-1)
    best = score.groupby([out["crash"], out["ticker"]]).transform("max")
    n_best = (score == best).groupby([out["crash"], out["ticker"]]).transform("sum")
    by_name = dup & (best >= SAME_FIRM) & (n_best == 1)
    out["conflict"] = dup & ~np.where(by_name, score == best, sec_wins)
    out = out.drop(columns="n")
    dup = out["conflict"]
    out.to_parquet(INTERIM / "ticker_map.parquet", index=False)

    ok = out[out["ticker"].notna() & ~out["conflict"]]
    print(pd.crosstab(out["crash"], out["source"], margins=True).to_string())
    print(f"\nconflicts: {dup.sum():,} rows; current tickers skipped as another firm's: "
          f"{out['skipped_other_firm'].notna().sum():,}")
    print(f"matched: {len(ok):,} of {len(out):,} rows ({len(ok) / len(out):.1%}), "
          f"{ok['ticker'].nunique():,} unique tickers")
    print(ok.groupby("crash")["still_trading"].agg(["size", "sum"]).to_string())


if __name__ == "__main__":
    main()
