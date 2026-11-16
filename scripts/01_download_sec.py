# Download the SEC bulk files and the current ticker list.
# Safe to re-run: partial downloads resume and finished files are skipped.
# python 3.14.10, requests 2.34.2
import sys
import time
import zipfile

import requests

from config import SEC_DIR, SEC_USER_AGENT

BASE = "https://www.sec.gov"
# submissions.zip returned 403 on every attempt, so 01b_download_submissions.py
# gets the same filing histories from the per-company API
BULK_FILES = ["companyfacts.zip"]
CHUNK = 1024 * 1024
MAX_RETRIES = 5


def download(url, dest):
    """Stream url to dest through a .part file, resuming after failures."""
    part = dest.with_name(dest.name + ".part")
    for attempt in range(1, MAX_RETRIES + 1):
        have = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": SEC_USER_AGENT}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 416:  # the .part file is already complete
                    break
                r.raise_for_status()
                # 200 means the server ignored the Range request, so start over
                mode = "ab" if r.status_code == 206 else "wb"
                with open(part, mode) as f:
                    for chunk in r.iter_content(CHUNK):
                        f.write(chunk)
            break
        except requests.RequestException as e:
            print(f"  attempt {attempt} failed: {e}", flush=True)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(10 * attempt)
    part.replace(dest)


def main():
    if not SEC_USER_AGENT:
        sys.exit("SEC_USER_AGENT is missing from .env")
    SEC_DIR.mkdir(parents=True, exist_ok=True)

    failed = []
    for name in BULK_FILES:
        dest = SEC_DIR / name
        if dest.exists():
            print(f"{name}: already downloaded, skipping", flush=True)
        else:
            print(f"{name}: downloading", flush=True)
            try:
                download(f"{BASE}/Archives/edgar/daily-index/xbrl/{name}", dest)
            except requests.RequestException as e:
                print(f"{name}: FAILED: {e}", flush=True)
                failed.append(name)
                continue
        # Checks the archive's file list only, which is fast
        with zipfile.ZipFile(dest) as z:
            count = len(z.namelist())
        print(f"{name}: {dest.stat().st_size / 1e9:.2f} GB, {count:,} files", flush=True)
        time.sleep(1)

    download(f"{BASE}/files/company_tickers.json", SEC_DIR / "company_tickers.json")
    print("company_tickers.json: done", flush=True)

    if failed:
        sys.exit(f"Failed: {failed}")


if __name__ == "__main__":
    main()
