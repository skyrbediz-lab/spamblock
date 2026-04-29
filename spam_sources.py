"""
Multi-source spam number fetcher.

Free sources (no API key needed):
  1. FTC Do Not Call complaint CSV (set FTC_FEED_URL env var to current weekly dump)
  2. Local seed list (curated known-bad numbers)
  3. Any HTTP CSV with a 'phone' column (set EXTRA_FEED_URLS, comma-separated)

Paid sources to add later when revenue justifies:
  - Hiya Reputation API (~$0.001/lookup)
  - Truecaller Search API
  - Nomorobo subscription feed

Run:  python spam_sources.py
"""
import csv
import io
import os
import sys
import httpx
import db


def fetch_csv(url: str, source_name: str) -> int:
    print(f"[{source_name}] fetching {url}")
    r = httpx.get(url, timeout=60, follow_redirects=True, headers={"User-Agent": "spamblock/1.0"})
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    count = 0
    for row in reader:
        phone = (
            row.get("phone")
            or row.get("Company_Phone_Number")
            or row.get("Phone")
            or row.get("number")
            or row.get("Number")
        )
        if phone:
            db.add_spam_number(phone, source_name)
            count += 1
    print(f"[{source_name}] imported {count} numbers")
    return count


def fetch_ftc():
    url = os.getenv("FTC_FEED_URL")
    if not url:
        print("[ftc] skipped (set FTC_FEED_URL to weekly dump from ftc.gov/policy/research/do-not-call-data)")
        return 0
    return fetch_csv(url, "ftc_dnc")


def fetch_extra():
    raw = os.getenv("EXTRA_FEED_URLS", "")
    total = 0
    for url in (u.strip() for u in raw.split(",") if u.strip()):
        try:
            total += fetch_csv(url, f"extra:{url[:50]}")
        except Exception as e:
            print(f"[extra] failed {url}: {e}")
    return total


def main():
    db.init_db()
    total = 0
    total += fetch_ftc()
    total += fetch_extra()
    print(f"\nDone. Imported {total} numbers across all sources.")
    if total == 0:
        print("\nNo external sources configured. Heuristic detector still active for unknown numbers.")
        print("Set FTC_FEED_URL or EXTRA_FEED_URLS to pull real data.")


if __name__ == "__main__":
    main()
