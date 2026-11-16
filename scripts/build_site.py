# Builds the project page (docs/index.html) from the processed tables.
# The page is one self-contained HTML file: the template is in site_template.html,
# and this script fills in the data as JSON. Run from the scripts folder:
#   ../.venv/bin/python build_site.py
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "docs" / "index.html"
TEMPLATE = Path(__file__).with_name("site_template.html")

CRASHES = ["covid_2020", "rates_2022", "tariff_2025"]
LABELS = ["recovered_12m", "beat_market"]

FEATURES = {
    "volatility_12m": "Volatility (12 months)",
    "momentum_12_1": "Momentum (12 to 1 months)",
    "beta": "Beta against SPY",
    "log_market_value": "Market value",
    "log_assets": "Total assets",
    "cash_to_assets": "Cash to assets",
    "current_ratio": "Current ratio",
    "debt_to_assets": "Debt to assets",
    "liabilities_to_assets": "Liabilities to assets",
    "interest_coverage": "Interest coverage",
    "net_margin": "Net margin",
    "operating_margin": "Operating margin",
    "return_on_assets": "Return on assets",
    "ocf_to_assets": "Operating cash flow to assets",
    "revenue_growth": "Revenue growth",
    "asset_growth": "Asset growth",
}

# Model results, copied from the outputs of notebooks/02_classification.ipynb.
# Rows are the training crash and columns the test crash; the diagonal is
# 5-fold cross-validation grouped by firm.
TRANSFER = {
    "recovered_12m": {
        "lgbm": [[0.678, 0.457, 0.517], [0.456, 0.703, 0.602], [0.456, 0.579, 0.674]],
        "baseline": [[0.623, 0.468, 0.443], [0.463, 0.670, 0.618], [0.426, 0.633, 0.651]],
    },
    "beat_market": {
        "lgbm": [[0.714, 0.443, 0.449], [0.488, 0.731, 0.534], [0.446, 0.542, 0.678]],
    },
}
WITHIN = {  # within-crash AUC by model
    "recovered_12m": {
        "baseline": [0.623, 0.670, 0.651], "logit": [0.647, 0.701, 0.670],
        "forest": [0.683, 0.709, 0.676], "lgbm": [0.678, 0.703, 0.674],
    },
    "beat_market": {
        "baseline": [0.645, 0.667, 0.649], "logit": [0.684, 0.719, 0.670],
        "forest": [0.708, 0.730, 0.679], "lgbm": [0.714, 0.731, 0.678],
    },
}
# LightGBM trained on the other two crashes, with firm-grouped bootstrap 95% CIs
OTHER_TWO = {
    "recovered_12m": [[0.422, 0.400, 0.446], [0.518, 0.500, 0.538], [0.546, 0.526, 0.566]],
    "beat_market": [[0.452, 0.431, 0.471], [0.486, 0.467, 0.506], [0.478, 0.457, 0.498]],
}


def kaplan_meier(days, event, cap=549, step=7):
    """Share of firms recovered (1 - survival) at each step, recovery as the event."""
    days = np.asarray(days)
    event = np.asarray(event)
    grid = np.arange(0, cap + 1, step)
    if len(grid) == 0 or grid[-1] != cap:
        grid = np.append(grid, cap)
    times = np.unique(days[event == 1])
    surv, s = {}, 1.0
    for t in times:
        at_risk = (days >= t).sum()
        if at_risk:
            s *= 1 - ((days == t) & (event == 1)).sum() / at_risk
        surv[t] = s
    out, s, i = [], 1.0, 0
    for g in grid:
        while i < len(times) and times[i] <= g:
            s = surv[times[i]]
            i += 1
        out.append(round(1 - s, 4))
    median = next((int(t) for t in times if surv[t] <= 0.5), None)
    return {"t": grid.tolist(), "y": out, "median": median, "n": int(len(days))}


def main():
    firms = pd.read_parquet(PROCESSED / "firm_crash.parquet")
    arch = pd.read_parquet(PROCESSED / "archetypes.parquet")
    firms = firms.merge(arch[["cik", "crash", "archetype_name"]], on=["cik", "crash"], how="left")

    # Recovery and beat-SPY rate by within-crash tercile of each feature
    terciles = {}
    for f in FEATURES:
        terciles[f] = {}
        for c in CRASHES:
            d = firms[(firms.crash == c) & firms[f].notna()]
            q = pd.qcut(d[f].rank(method="first"), 3, labels=False)
            g = d.groupby(q)[LABELS].mean()
            terciles[f][c] = {
                lab: [round(float(v), 4) for v in g[lab]] for lab in LABELS
            }
            terciles[f][c]["n"] = int(len(d))

    # Recovery curves: all firms, by archetype, and by sector
    groups = {"all": ("All firms", None)}
    for a in sorted(firms.archetype_name.dropna().unique()):
        groups[f"arch:{a}"] = (a, ("archetype_name", a))
    for s in firms.sic_division.value_counts().index:
        if (firms.sic_division == s).sum() >= 100:
            groups[f"sector:{s}"] = (s, ("sic_division", s))
    curves = {}
    for key, (name, filt) in groups.items():
        d = firms if filt is None else firms[firms[filt[0]] == filt[1]]
        curves[key] = {"name": name, "crash": {
            c: kaplan_meier(d.loc[d.crash == c, "recovery_days"], d.loc[d.crash == c, "recovered_event"])
            for c in CRASHES
        }}

    # Archetype outcomes by crash
    archetypes = []
    for a, d in firms.groupby("archetype_name"):
        row = {"name": a, "n": int(len(d))}
        for lab in LABELS:
            row[lab] = [round(float(d.loc[d.crash == c, lab].mean()), 4) for c in CRASHES]
        archetypes.append(row)

    # Headline numbers by crash
    summary = []
    for c in CRASHES:
        d = firms[firms.crash == c]
        summary.append({
            "crash": c, "n": int(len(d)),
            "recovered_12m": round(float(d.recovered_12m.mean()), 4),
            "beat_market": round(float(d.beat_market.mean()), 4),
            "median_drawdown": round(float(d.drawdown.median()), 4),
            "failed": int((d.exit_status == "failed").sum()),
            "acquired": int((d.exit_status == "acquired").sum()),
        })

    # Firm table, stored as columns to keep the page small
    f = firms.sort_values(["ticker", "crash"])
    firm_cols = {
        "ticker": f.ticker.tolist(),
        "name": f.name.str.strip().tolist(),
        "crash": [CRASHES.index(c) for c in f.crash],
        "sector": f.sic_division.tolist(),
        "arch": f.archetype_name.str.slice(0, 2).tolist(),
        "dd": (f.drawdown * 1000).round().astype(int).tolist(),
        "rec": f.recovered_12m.tolist(),
        "days": [int(x) if e else None for x, e in zip(f.recovery_days, f.recovered_event)],
        "xs": [None if pd.isna(x) else int(round(x * 1000)) for x in f.excess_return],
        "exit": f.exit_status.tolist(),
    }

    funnel = pd.read_csv(INTERIM / "label_counts.csv")

    data = {
        "crashes": CRASHES,
        "features": FEATURES,
        "transfer": TRANSFER,
        "within": WITHIN,
        "otherTwo": OTHER_TWO,
        "terciles": terciles,
        "curves": curves,
        "archetypes": archetypes,
        "summary": summary,
        "firms": firm_cols,
        "funnelLabels": funnel.to_dict(orient="list"),
        "built": pd.Timestamp.today().strftime("%Y-%m-%d"),
    }
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False)
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", payload)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"Wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    for c in CRASHES:
        k = curves["all"]["crash"][c]
        print(c, "recovered by 18 months:", k["y"][-1], "median days:", k["median"])


if __name__ == "__main__":
    main()
