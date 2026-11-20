# Two figures that explain how the data was built (used on the slides).
#   Section 1: label_example.png       how the recovery label is read off one stock's prices
#   Section 2: price_check_example.png  how the fails-price check catches a reused ticker
# Needs the raw price and fails files (data/raw), so run it after 05 and 06.
# python 3.14.10, pandas 2.3.3, matplotlib 3.11.2
import zipfile

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import CRASHES, PRICE_DIR, PROCESSED, RAW
from helpers import BASELINE, INK, MUTED, save_figure, set_style

# --- Section 1: The label on two real stocks (2022 crash) ---

LABEL_CRASH = "rates_2022"
LABEL_FIRMS = [("AAPL", "Apple", "#2a78d6"), ("DIS", "Disney", "#b0302f")]


def label_example():
    labels = pd.read_parquet(PROCESSED / "labels.parquet")
    c = CRASHES[LABEL_CRASH]
    peak, trough = pd.Timestamp(c["peak"]), pd.Timestamp(c["trough"])
    end12, end18 = trough + pd.DateOffset(months=12), trough + pd.DateOffset(months=18)

    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.axhline(1, color=BASELINE, lw=1, ls="--", zorder=1)
    ax.axvspan(trough, end12, color="#eef2f6", zorder=0)
    first_day = None
    for ticker, name, color in LABEL_FIRMS:
        row = labels[(labels["ticker"] == ticker) & (labels["crash"] == LABEL_CRASH)].iloc[0]
        px = pd.read_parquet(PRICE_DIR / "yahoo" / f"{ticker}.parquet")["Adj Close"]
        px.index = pd.to_datetime(px.index).tz_localize(None).normalize()
        window_start = px[:peak].index[-30]  # the 30 trading days up to the peak
        first_day = window_start
        rel = px[px.index >= window_start - pd.Timedelta(days=40)][:end18] / row["pre_price"]
        ax.plot(rel.index, rel.values, color=color, lw=1.8, zorder=3)
        if row["recovered_12m"]:
            d = pd.Timestamp(row["recovery_date"])
            ax.plot(d, rel.loc[d], "o", color=color, mec="white", mew=2, ms=9, zorder=4)
            ax.annotate(f"{name}: back on day {row['recovery_days']}\nrecovered_12m = 1", (d, rel.loc[d]),
                        xytext=(-10, 26), textcoords="offset points", ha="right", fontsize=9.5,
                        color=color, fontweight="bold")
        else:
            ax.text(pd.Timestamp("2022-02-15"), 0.545, f"{name}: never back\nrecovered_12m = 0",
                    ha="left", va="top", fontsize=9.5, color=color, fontweight="bold")
    ax.axvspan(first_day, peak, color="#dce1e6", zorder=0)
    for x, text, ha in [(peak, " market peak", "left"), (trough, " market trough", "left"),
                        (end12, "trough + 12 months ", "right"), (end18, "+ 18 (survival cap) ", "right")]:
        ax.axvline(x, color=MUTED, lw=0.9, zorder=2)
        y = 1.36 if x == end18 else 1.44
        ax.text(x, y, text, ha=ha, va="bottom", fontsize=8.5, color=MUTED)
    ax.annotate("pre-crash price = highest close\nin the 30 trading days to the peak", (peak, 1.0),
                xytext=(peak + pd.Timedelta(days=25), 1.30), fontsize=8.5, color=INK, va="center",
                arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
    ax.text(trough + (end12 - trough) / 2, 0.47, "label window", ha="center", fontsize=9.5, color=MUTED)
    ax.set_ylim(0.42, 1.52)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_ylabel("Price / pre-crash price")
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_title("Rate hikes (2022): one recovered within 12 months, one didn't")
    print(save_figure(fig, "label_example"))


# --- Section 2: The fails-price check on a reused ticker ---
# CZR was old Caesars until the July 2020 merger; Eldorado then took the name and ticker.
# Yahoo's CZR history is Eldorado's, so it fails for old Caesars in 2020 and passes for the
# merged firm in 2022.

CHECK_TICKER = "CZR"
CHECK_CASES = [("covid_2020", "2020: old Caesars, ticker since reused"),
               ("rates_2022", "2022: the firm that holds CZR now")]
WINDOW = pd.Timedelta(days=270)  # same window as 05_check_prices.py


def load_fails(ticker):
    frames = []
    for path in sorted((RAW / "sec" / "ftd").glob("cnsfails*.zip")):
        with zipfile.ZipFile(path) as z:
            df = pd.read_csv(z.open(z.namelist()[0]), sep="|", dtype=str, encoding="latin-1",
                             on_bad_lines="skip", keep_default_na=False)
        df.columns = [col.strip().upper() for col in df.columns]
        frames.append(df[df["SYMBOL"] == ticker][["SETTLEMENT DATE", "PRICE"]])
    f = pd.concat(frames)
    f.columns = ["date", "price"]
    f["date"] = pd.to_datetime(f["date"], format="%Y%m%d", errors="coerce")
    f["price"] = pd.to_numeric(f["price"], errors="coerce")
    return f.dropna().drop_duplicates("date").set_index("date")["price"].sort_index()


def price_check_example():
    check = pd.read_parquet(RAW.parent / "interim" / "price_check.parquet")
    fails = load_fails(CHECK_TICKER)
    px = pd.read_parquet(PRICE_DIR / "yahoo" / f"{CHECK_TICKER}.parquet")["Close"]
    px.index = pd.to_datetime(px.index).tz_localize(None).normalize()

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, (crash, title) in zip(axes, CHECK_CASES):
        peak = pd.Timestamp(CRASHES[crash]["peak"])
        row = check[(check["ticker"] == CHECK_TICKER) & (check["crash"] == crash)].iloc[0]
        y = px[peak - WINDOW: peak + WINDOW]
        f = fails[peak - WINDOW: peak + WINDOW]
        ax.plot(y.index, y.values, color="#7c8794", lw=1.6, label="Yahoo close (today's CZR)")
        ax.plot(f.index, f.values, "o", ms=4, color=INK, alpha=0.7,
                label="SEC fails price (CZR at the time)")
        ax.axvline(peak, color=MUTED, lw=0.9)
        ax.text(peak, ax.get_ylim()[1], " peak", va="top", fontsize=8.5, color=MUTED)
        ok = row["check"] == "verified"
        verdict = "Verified" if ok else "Rejected"
        ax.set_title(title, fontsize=11.5, pad=24)
        ax.text(0, 1.03, f"{verdict}: {row['agree']:.0%} of {row['ftd_days']} fails dates agree (needs 80%)",
                transform=ax.transAxes, fontsize=10, fontweight="bold", va="bottom",
                color="#1c7a50" if ok else "#b0302f")
        if not ok:
            ax.annotate("merger: the ticker\nmoves to Eldorado", (pd.Timestamp("2020-07-20"), 38),
                        xytext=(pd.Timestamp("2019-08-01"), 24), ha="left", fontsize=8.5, color=MUTED,
                        arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_formatter(lambda v, _: f"${v:.0f}")
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    axes[0].legend(loc="upper left", bbox_to_anchor=(0, -0.12), ncol=2, fontsize=9.5)
    print(save_figure(fig, "price_check_example"))
    print(check[check["ticker"] == CHECK_TICKER][["cik", "crash", "agree", "ftd_days", "check"]])


if __name__ == "__main__":
    set_style()
    label_example()
    price_check_example()
