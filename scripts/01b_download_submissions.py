# Download each company's filing history from the SEC per-company API.
# Used because the bulk submissions.zip returned 403.
# Safe to re-run: companies already saved are skipped.
# python 3.14.10, requests 2.34.2
# Usage: python 01b_download_submissions.py [--limit N]
import argparse
import json
import sys
import time
import zipfile

import requests

from config import SEC_DIR, SEC_USER_AGENT

API = "https://data.sec.gov/submissions/{}"
MIN_GAP = 0.125  # at most 8 requests a second, under the SEC's limit of 10
MAX_REFUSALS = 5  # stop, rather than keep pushing, if the SEC keeps refusing

OUT = SEC_DIR / "submissions"


class Client:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = SEC_USER_AGENT
        self.last = 0.0
        self.refusals = 0

    def get(self, name):
        """Return parsed JSON, or None if the SEC has no such file."""
        while True:
            wait = MIN_GAP - (time.monotonic() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            try:
                r = self.session.get(API.format(name), timeout=60)
            except requests.RequestException as e:
                print(f"  network error on {name}: {e}", flush=True)
                time.sleep(10)
                continue
            if r.status_code == 404:
                return None
            if r.status_code in (403, 429, 503):
                self.refusals += 1
                print(f"  HTTP {r.status_code} on {name} "
                      f"({self.refusals}/{MAX_REFUSALS})", flush=True)
                if self.refusals >= MAX_REFUSALS:
                    sys.exit("SEC keeps refusing requests, stopping. Re-run later to resume.")
                time.sleep(60)
                continue
            r.raise_for_status()
            self.refusals = 0
            return r.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if not SEC_USER_AGENT:
        sys.exit("SEC_USER_AGENT is missing from .env")
    OUT.mkdir(parents=True, exist_ok=True)

    # The company list comes from the companyfacts archive: CIK##########.json
    with zipfile.ZipFile(SEC_DIR / "companyfacts.zip") as z:
        names = sorted(n for n in z.namelist() if n.startswith("CIK") and n.endswith(".json"))
    if args.limit:
        names = names[:args.limit]

    client = Client()
    start = time.monotonic()
    fetched = missing = pages = 0
    for i, name in enumerate(names, 1):
        dest = OUT / name
        if dest.exists():
            continue
        data = client.get(name)
        if data is None:
            missing += 1
            continue
        # Busy filers keep older filings in extra pages
        data["older_pages"] = []
        for page in data.get("filings", {}).get("files", []):
            older = client.get(page["name"])
            if older is not None:
                data["older_pages"].append(older)
                pages += 1
        # Write then rename, so an interrupted run never leaves a partial file
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(dest)
        fetched += 1
        if fetched % 500 == 0:
            rate = fetched / (time.monotonic() - start)
            print(f"{i:,}/{len(names):,} checked, {fetched:,} fetched, "
                  f"{rate:.1f} companies/s", flush=True)

    saved = len(list(OUT.glob("CIK*.json")))
    print(f"Done: {fetched:,} fetched, {pages:,} older pages, {missing:,} not found, "
          f"{saved:,} saved in total, {time.monotonic() - start:.0f} s", flush=True)


if __name__ == "__main__":
    main()
