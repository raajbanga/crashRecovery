# Download SEC fails-to-deliver files and Tiingo's ticker list for ticker matching.
# The fails files show which ticker a company name used on a given date, including dead firms.
# python 3.14.10, pandas 2.3.3, requests 2.34.2
# Output: data/interim/ftd_symbols.parquet, data/raw/prices/supported_tickers.zip
import io
import re
import time
import zipfile

import pandas as pd
import requests

from config import INTERIM, PRICE_DIR, RAW, SEC_USER_AGENT

PAGE = "https://www.sec.gov/data/foiadocsfailsdatahtm"
TIINGO_LIST = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
FIRST_YEAR = 2019
FTD_DIR = RAW / "sec" / "ftd"


def main():
    FTD_DIR.mkdir(parents=True, exist_ok=True)
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = SEC_USER_AGENT

    r = s.get(PAGE, timeout=60)
    r.raise_for_status()
    links = sorted(set(re.findall(r'href="(/files/[^"]*cnsfails(\d{4})\d{2}[ab]\.zip)"', r.text)))
    links = [link for link, year in links if int(year) >= FIRST_YEAR]
    print(f"{len(links)} files listed since {FIRST_YEAR}", flush=True)

    frames = []
    for link in links:
        dest = FTD_DIR / link.rsplit("/", 1)[1]
        if not dest.exists():
            time.sleep(0.2)
            got = s.get("https://www.sec.gov" + link, timeout=120)
            got.raise_for_status()
            dest.write_bytes(got.content)
        with zipfile.ZipFile(dest) as z:
            raw = z.read(z.namelist()[0])
        df = pd.read_csv(io.BytesIO(raw), sep="|", dtype=str, encoding="latin-1",
                         on_bad_lines="skip", keep_default_na=False)
        df.columns = [c.strip().upper() for c in df.columns]
        df = df[["SETTLEMENT DATE", "CUSIP", "SYMBOL", "DESCRIPTION"]]
        df.columns = ["date", "cusip", "symbol", "description"]
        frames.append(df[df["date"].str.fullmatch(r"\d{8}")])

    all_rows = pd.concat(frames, ignore_index=True)
    all_rows["date"] = pd.to_datetime(all_rows["date"], format="%Y%m%d")
    symbols = (all_rows.groupby(["symbol", "description", "cusip"], as_index=False)
               .agg(first=("date", "min"), last=("date", "max"), days=("date", "nunique")))
    symbols = symbols[symbols["symbol"].str.strip() != ""]
    INTERIM.mkdir(parents=True, exist_ok=True)
    symbols.to_parquet(INTERIM / "ftd_symbols.parquet", index=False)
    print(f"{len(all_rows):,} rows, {symbols['symbol'].nunique():,} symbols, "
          f"{all_rows['date'].min().date()} to {all_rows['date'].max().date()}", flush=True)

    got = requests.get(TIINGO_LIST, timeout=120)
    got.raise_for_status()
    (PRICE_DIR / "supported_tickers.zip").write_bytes(got.content)
    print("Tiingo ticker list saved", flush=True)


if __name__ == "__main__":
    main()
