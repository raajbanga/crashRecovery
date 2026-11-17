# S&P 500 indexed to each crash's peak (used on the slides).
# python 3.14.10, pandas 2.3.3, matplotlib 3.11.2
# Output: figures/sp500_crashes.png
import matplotlib.pyplot as plt
import pandas as pd

from config import CRASHES, RAW
from helpers import BASELINE, CRASH_COLORS, CRASH_LABELS, CRASH_SHORT, MUTED, save_figure, set_style

MONTH = 30.4375  # days


def sp500_paths(months_after=24):
    """S&P 500 indexed to 100 at each crash's peak, by months since the peak."""
    sp = pd.read_csv(RAW / "fred" / "SP500.csv", parse_dates=["observation_date"])
    sp = sp.dropna().set_index("observation_date")["SP500"]
    paths = {}
    for crash, c in CRASHES.items():
        peak, trough = pd.Timestamp(c["peak"]), pd.Timestamp(c["trough"])
        window = sp[peak - pd.Timedelta(days=31): peak + pd.Timedelta(days=round(months_after * MONTH))]
        path = 100 * window / sp[peak]
        path.index = (path.index - peak).days / MONTH
        back = sp[trough:][sp[trough:] >= sp[peak]]
        paths[crash] = {"path": path, "drop": sp[trough] / sp[peak] - 1,
                        "trough_month": (trough - peak).days / MONTH,
                        "months_back": (back.index[0] - peak).days / MONTH if len(back) else None}
    return paths


def main():
    set_style()
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.axhline(100, color=BASELINE, lw=1, ls="--", zorder=1)
    ax.text(23.8, 101, "pre-crash peak", color=MUTED, ha="right", va="bottom", fontsize=9)
    for crash, p in sp500_paths().items():
        color = CRASH_COLORS[crash]
        back = (f"peak regained in {p['months_back']:.0f} months" if p["months_back"]
                else "not regained in 24 months")
        drop = f"{p['drop']:.0%}".replace("-", "\u2212")  # typographic minus
        label = f"{CRASH_LABELS[crash]}: {drop} at the trough, {back}"
        ax.plot(p["path"].index, p["path"].values, color=color, label=label, zorder=3)
        ax.plot(p["trough_month"], 100 * (1 + p["drop"]), "o", color=color, mec="white", mew=2,
                ms=8, zorder=4)
        end = p["path"].iloc[-1]
        ax.text(p["path"].index[-1] + 0.25, end, CRASH_SHORT[crash], color=MUTED, fontsize=9,
                va="center", fontweight="bold")
    ax.set_xlim(-1, 25)
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlabel("Months since the S&P 500 peak")
    ax.set_ylabel("S&P 500 (peak = 100)")
    ax.set_title("Three crashes, three different recoveries")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.15), fontsize=9.5, handlelength=1.5)
    ax.text(0, -0.44, "Source: FRED SP500, daily close. Dots mark each trough.",
            transform=ax.transAxes, fontsize=8.5, color=MUTED)
    print(save_figure(fig, "sp500_crashes"))


if __name__ == "__main__":
    main()
