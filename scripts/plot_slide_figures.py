# Dark versions of the deck's figures, styled like the project page (docs/index.html) in
# dark mode. The report keeps the light figures from the notebooks and the other plot
# scripts; these are drawn only for the slides.
# Each figure is drawn at the size it fills on the slide, so 12 pt here is 12 pt there.
# Output: figures/slides/*.png. Needs the raw price, fails, and FRED files (data/raw).
#   Section 1: style            Section 2: data figures (S&P 500, label, price check)
#   Section 3: model figures    (SHAP ranks, volatility thirds, recovery curves, archetypes)
# python 3.14.10, pandas 2.3.3, matplotlib 3.11.2, lightgbm 4.7.0, shap 0.54.1
import textwrap

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from build_site import FEATURES as FEATURE_NAMES, kaplan_meier
from config import CRASHES, PRICE_DIR, PROCESSED, RAW
from helpers import FIGURES, load_firms, make_model, model_columns
from plot_method_figures import CHECK_CASES, CHECK_TICKER, LABEL_CRASH, WINDOW, load_fails
from plot_sp500_crashes import sp500_paths

OUT = FIGURES / "slides"
ORDER = list(CRASHES)
NAME = {"covid_2020": "COVID-19 2020", "rates_2022": "Rate hikes 2022", "tariff_2025": "Tariffs 2025"}
SHORT = {"covid_2020": "2020", "rates_2022": "2022", "tariff_2025": "2025"}

# --- Section 1: Style (the page's dark-mode tokens) ---
BG, SURFACE, RAISED = "#0f1419", "#161c22", "#1d252d"
INK, INK2, MUTED = "#e9edf1", "#aeb8c2", "#7f8a95"
GRID, AXIS = "#232a31", "#3a434c"
COLOR = {"covid_2020": "#3987e5", "rates_2022": "#d95926", "tariff_2025": "#199e70"}
GOOD, BAD = "#3fc79a", "#f0a1a0"
SANS = "Helvetica Neue"


def set_dark_style():
    mpl.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 250, "font.family": SANS, "font.size": 12,
        "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG,
        "text.color": INK, "axes.labelcolor": MUTED, "axes.labelsize": 11.5, "axes.edgecolor": AXIS,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 11, "ytick.labelsize": 11,
        "xtick.major.size": 0, "ytick.major.size": 0, "xtick.major.pad": 6, "ytick.major.pad": 6,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 1, "axes.axisbelow": True,
        "lines.linewidth": 2.2, "lines.solid_capstyle": "round",
        "legend.frameon": False, "legend.fontsize": 11.5, "legend.labelcolor": INK2,
        "legend.handlelength": 1.1, "legend.handleheight": 0.3,
    })


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    fig.savefig(path)  # fixed canvas, so the figure fills its slot exactly
    plt.close(fig)
    print(path)


def pct(ax, axis="y"):
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(mpl.ticker.PercentFormatter(1, decimals=0))


# --- Section 2: Data figures ---

def sp500():
    fig, ax = plt.subplots(figsize=(6.7, 4.75), layout="constrained")
    ax.axhline(100, color=AXIS, lw=1, ls=(0, (3, 3)))
    ax.text(24, 101, "pre-crash peak", color=MUTED, ha="right", va="bottom", fontsize=10.5)
    for crash, p in sp500_paths().items():
        ax.plot(p["path"].index, p["path"].values, color=COLOR[crash], zorder=3)
        ax.plot(p["trough_month"], 100 * (1 + p["drop"]), "o", color=COLOR[crash], mec=BG, mew=2, ms=9, zorder=4)
        drop = f"{p['drop']:.0%}".replace("-", "−")
        off, ha = {"covid_2020": ((0, -14), "center"), "rates_2022": ((0, -14), "center"),
                   "tariff_2025": ((10, -2), "left")}[crash]
        ax.annotate(drop, (p["trough_month"], 100 * (1 + p["drop"])), xytext=off, textcoords="offset points",
                    ha=ha, va="top", fontsize=11, color=COLOR[crash], fontweight="bold")
        ax.text(p["path"].index[-1] + 0.3, p["path"].values[-1], SHORT[crash], color=COLOR[crash],
                fontsize=11, va="center", fontweight="bold")
    ax.set_xlim(-1, 25.5)
    ax.set_ylim(60, 145)
    ax.set_xticks(range(0, 25, 6))
    ax.set_xlabel("Months since the S&P 500 peak")
    ax.set_ylabel("S&P 500, peak = 100")
    ax.text(0, -0.2, "FRED SP500, daily close. Dots mark each trough.", transform=ax.transAxes,
            fontsize=10, color=MUTED)
    save(fig, "sp500_crashes")


def label_example():
    labels = pd.read_parquet(PROCESSED / "labels.parquet")
    c = CRASHES[LABEL_CRASH]
    peak, trough = pd.Timestamp(c["peak"]), pd.Timestamp(c["trough"])
    end12, end18 = trough + pd.DateOffset(months=12), trough + pd.DateOffset(months=18)
    firms = [("AAPL", "Apple", COLOR["covid_2020"]), ("DIS", "Disney", "#e34948")]

    fig, ax = plt.subplots(figsize=(7.7, 3.95), layout="constrained")
    ax.axhline(1, color=AXIS, lw=1, ls=(0, (3, 3)), zorder=1)
    ax.axvspan(trough, end12, color=SURFACE, zorder=0)
    first_day = None
    for ticker, name, color in firms:
        row = labels[(labels["ticker"] == ticker) & (labels["crash"] == LABEL_CRASH)].iloc[0]
        px = pd.read_parquet(PRICE_DIR / "yahoo" / f"{ticker}.parquet")["Adj Close"]
        px.index = pd.to_datetime(px.index).tz_localize(None).normalize()
        first_day = px[:peak].index[-30]
        rel = px[px.index >= first_day - pd.Timedelta(days=40)][:end18] / row["pre_price"]
        ax.plot(rel.index, rel.values, color=color, lw=2, zorder=3)
        if row["recovered_12m"]:
            d = pd.Timestamp(row["recovery_date"])
            ax.plot(d, rel.loc[d], "o", color=color, mec=BG, mew=2, ms=10, zorder=4)
            ax.annotate(f"{name}: back on day {row['recovery_days']}\nrecovered_12m = 1", (d, rel.loc[d]),
                        xytext=(-12, 24), textcoords="offset points", ha="right", fontsize=11,
                        color=color, fontweight="bold")
        else:
            ax.text(pd.Timestamp("2022-02-15"), 0.55, f"{name}: never back\nrecovered_12m = 0",
                    ha="left", va="top", fontsize=11, color=color, fontweight="bold")
    ax.axvspan(first_day, peak, color=RAISED, zorder=0)
    for x, text, ha in [(peak, " peak", "left"), (trough, " trough", "left"),
                        (end12, "trough + 12 mo ", "right"), (end18, "+ 18 mo ", "right")]:
        ax.axvline(x, color=AXIS, lw=1, zorder=2)
        ax.text(x, 1.36 if x == end18 else 1.45, text, ha=ha, va="bottom", fontsize=10.5, color=MUTED)
    ax.annotate("pre-crash price = highest close\nin the 30 trading days to the peak", (peak, 1.0),
                xytext=(peak + pd.Timedelta(days=25), 1.28), fontsize=10.5, color=INK2, va="center",
                arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
    ax.text(trough + (end12 - trough) / 2, 0.47, "label window", ha="center", fontsize=10.5, color=MUTED)
    ax.set_ylim(0.42, 1.55)
    pct(ax)
    ax.set_ylabel("Price / pre-crash price")
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    save(fig, "label_example")


def price_check_example():
    check = pd.read_parquet(RAW.parent / "interim" / "price_check.parquet")
    fails = load_fails(CHECK_TICKER)
    px = pd.read_parquet(PRICE_DIR / "yahoo" / f"{CHECK_TICKER}.parquet")["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None).normalize()

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.85), layout="constrained")
    for ax, (crash, title) in zip(axes, CHECK_CASES):
        peak = pd.Timestamp(CRASHES[crash]["peak"])
        row = check[(check["ticker"] == CHECK_TICKER) & (check["crash"] == crash)].iloc[0]
        ax.plot(px[peak - WINDOW: peak + WINDOW], color=MUTED, lw=1.8, label="Yahoo close (today's CZR)")
        f = fails[peak - WINDOW: peak + WINDOW]
        ax.plot(f.index, f.values, "o", ms=4, color=INK, alpha=0.8, mew=0, label="SEC fails price (CZR then)")
        ax.axvline(peak, color=AXIS, lw=1)
        ok = row["check"] == "verified"
        ax.set_title(f"{title}\n", loc="left", fontsize=12, color=INK, pad=4)
        ax.text(0, 1.015, f"{'Verified' if ok else 'Rejected'}: {row['agree']:.0%} of {row['ftd_days']} dates agree",
                transform=ax.transAxes, fontsize=11.5, fontweight="bold", va="bottom", color=GOOD if ok else BAD)
        if not ok:
            ax.annotate("merger: the ticker\nmoves to Eldorado", (pd.Timestamp("2020-07-20"), 38),
                        xytext=(pd.Timestamp("2019-07-01"), 20), ha="left", fontsize=10, color=MUTED,
                        arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_formatter(lambda v, _: f"${v:.0f}")
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower left", ncol=2)
    save(fig, "price_check_example")


# --- Section 3: Model figures ---

def shap_ranks(firms):
    """Rank of each feature by mean |SHAP| in each crash (same model as 02_classification)."""
    full, _ = model_columns(firms)
    rank = {}
    for crash in ORDER:
        d = firms[firms["crash"] == crash].reset_index(drop=True)
        import shap
        m = make_model("lgbm", full).fit(d, d["recovered_12m"])
        X = m.named_steps["prep"].transform(d)
        names = m.named_steps["prep"].get_feature_names_out()
        sv = shap.TreeExplainer(m.named_steps["model"]).shap_values(X)
        sv = pd.DataFrame(sv[1] if isinstance(sv, list) else sv, columns=names)
        group = [n.split("__", 1)[1] for n in names]
        group = ["sector" if g.startswith("sic_division") or g == "is_financial" else g.replace("_missing", "")
                 for g in group]
        rank[crash] = sv.abs().T.groupby(group).sum().T.mean().rank(ascending=False)
    rank = pd.DataFrame(rank)
    order = rank.mean(axis=1).sort_values().index[:12][::-1]  # top 12, most important at the top

    fig, ax = plt.subplots(figsize=(5.35, 4.1), layout="constrained")
    ax.axvspan(0.5, 5.5, color=SURFACE, zorder=0)
    ax.text(3, len(order) - 0.45, "top 5", ha="center", va="bottom", fontsize=10.5, color=MUTED)
    for i, f in enumerate(order):
        r = rank.loc[f, ORDER]
        ax.plot([r.min(), r.max()], [i, i], color=AXIS, lw=1.5, zorder=1)
        for crash in ORDER:
            ax.plot(r[crash], i, "o", color=COLOR[crash], ms=8, mec=BG, mew=1.5, zorder=3)
    ax.set_yticks(range(len(order)), [FEATURE_NAMES.get(f, "Sector") for f in order], fontsize=10.5, color=INK2)
    ax.set_xlim(0.5, 17.5)
    ax.set_ylim(-0.6, len(order) + 0.15)
    ax.set_xticks([1, 5, 10, 15])
    ax.grid(False)
    ax.set_xlabel("Rank by mean |SHAP|, 1 = most important")
    handles = [mpl.lines.Line2D([], [], ls="", marker="o", ms=8, color=COLOR[c]) for c in ORDER]
    fig.legend(handles, [SHORT[c] for c in ORDER], loc="outside upper right", ncol=3, handletextpad=0.2)
    save(fig, "shap_ranks")


def spread(ys, gap=0.045):
    """Nudge label positions apart so close values don't overlap."""
    out, last = {}, -1
    for k, v in sorted(ys.items(), key=lambda kv: kv[1]):
        out[k] = last = max(v, last + gap)
    return out


def volatility_flip(firms):
    firms = firms.copy()
    firms["third"] = firms.groupby("crash")["volatility_12m"].transform(
        lambda s: pd.qcut(s, 3, labels=False))
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.95), sharey=True, layout="constrained")
    titles = {"recovered_12m": "Back to the pre-crash price within 12 months", "beat_market": "Beat SPY over the same window"}
    x = np.arange(3)
    for ax, (label, title) in zip(axes, titles.items()):
        g = firms.groupby(["crash", "third"])[label].mean()
        starts = spread({c: g[c].values[0] for c in ORDER})
        for crash in ORDER:
            y = g[crash].values
            ax.plot(x, y, marker="o", ms=8, mec=BG, mew=2, color=COLOR[crash])
            ax.text(x[-1] + 0.1, y[-1], f"{SHORT[crash]}  {y[-1]:.0%}", va="center", fontsize=11,
                    color=COLOR[crash], fontweight="bold")
            ax.text(x[0] - 0.1, starts[crash], f"{y[0]:.0%}", va="center", ha="right", fontsize=11, color=COLOR[crash])
        ax.set_xticks(x, ["Calmest third", "Middle", "Most volatile third"])
        ax.set_xlim(-0.45, 2.75)
        ax.set_title(title, loc="left", fontsize=12.5, color=INK, pad=10)
    axes[0].set_ylim(0, 1)
    pct(axes[0])
    axes[0].set_ylabel("Share of firms")
    save(fig, "volatility_flip")


def km_by_crash(firms):
    fig, ax = plt.subplots(figsize=(4.4, 2.3), layout="constrained")
    for crash in ORDER:
        d = firms[firms["crash"] == crash]
        k = kaplan_meier(d["recovery_days"], d["recovered_event"])
        ax.step(k["t"], k["y"], where="post", color=COLOR[crash], lw=1.8)
        ax.text(k["t"][-1] + 8, k["y"][-1], f"{SHORT[crash]} · {k['median']}d", va="center", fontsize=9.5,
                color=COLOR[crash], fontweight="bold")
    ax.set_xlim(0, 700)
    ax.set_xticks([0, 180, 365, 549])
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.5, 1])
    pct(ax)
    ax.tick_params(labelsize=9.5)
    ax.set_xlabel("Days after the trough · median days", fontsize=9.5)
    ax.set_title("Share back at the pre-crash price", loc="left", fontsize=10.5, color=INK2)
    save(fig, "km_by_crash")


def archetype_recovery(firms):
    arch = pd.read_parquet(PROCESSED / "archetypes.parquet")
    d = firms.merge(arch[["cik", "crash", "archetype_name"]], on=["cik", "crash"])
    rates = d.groupby(["archetype_name", "crash"])["recovered_12m"].mean().unstack()[ORDER]
    fig, ax = plt.subplots(figsize=(4.4, 2.55), layout="constrained")
    x = np.arange(len(rates))
    for j, crash in enumerate(ORDER):
        xs = x + (j - 1) * 0.26
        ax.bar(xs, rates[crash].values, 0.24, color=COLOR[crash])
        for xi, v in zip(xs, rates[crash].values):
            ax.text(xi, v + 0.03, f"{v:.0%}", ha="center", fontsize=8, color=INK2)
    names = [n.split(": ", 1)[1] for n in rates.index]
    ax.set_xticks(x, [textwrap.fill(n[0].upper() + n[1:], 20) for n in names], fontsize=8.5, color=INK2)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.5, 1])
    pct(ax)
    ax.tick_params(axis="y", labelsize=9.5)
    ax.set_title("Recovered in 12 months, by archetype", loc="left", fontsize=10.5, color=INK2)
    save(fig, "archetype_recovery")


if __name__ == "__main__":
    set_dark_style()
    sp500()
    label_example()
    price_check_example()
    firms = load_firms()
    shap_ranks(firms)
    volatility_flip(firms)
    km_by_crash(firms)
    archetype_recovery(firms)
