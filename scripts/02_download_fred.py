# Download market and macro series from FRED. No API key is needed.
# python 3.14.10, pandas 2.3.3, requests 2.34.2
import io

import pandas as pd
import requests

from config import CRASHES, FRED_DIR, FRED_SERIES

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


def main():
    FRED_DIR.mkdir(parents=True, exist_ok=True)
    for series in FRED_SERIES:
        r = requests.get(URL.format(series), timeout=120)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), na_values=".")
        df.to_csv(FRED_DIR / f"{series}.csv", index=False)

        dates = df.iloc[:, 0]
        print(f"{series}: {len(df):,} rows, {dates.iloc[0]} to {dates.iloc[-1]}, "
              f"{df.iloc[:, 1].isna().sum()} blank")

        # Every crash must fall inside the series
        first_peak = min(c["peak"] for c in CRASHES.values())
        if dates.iloc[0] > first_peak:
            raise SystemExit(f"{series} starts after the first crash peak")


if __name__ == "__main__":
    main()
