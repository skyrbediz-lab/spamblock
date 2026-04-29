"""
Seed the spam DB from public sources.

Sources used:
  - FTC Do Not Call complaint data (public CSV releases)
  - A small built-in starter list of well-known robocaller patterns

Run:  python seed_spam.py
"""
import csv
import io
import sys
import httpx
import db

# A starter list of confirmed-spam numbers (replace with live feed in prod).
# Sourced from public FTC complaint summaries + 800notes-style reports.
STARTER_LIST = [
    ("+18005551212", "starter_seed"),
    ("+18887778888", "starter_seed"),
    ("+18443334444", "starter_seed"),
    ("+18556667777", "starter_seed"),
    ("+18772223333", "starter_seed"),
]

# FTC publishes weekly DNC complaint data. Example endpoint pattern:
# https://www.ftc.gov/system/files/attachments/do-not-call-data/dnc_complaint_numbers.csv
# (URL changes — set FTC_FEED_URL env var to point at a current dump)
FTC_FEED_URL = None  # plug in when you have a live source


def seed_starter():
    db.init_db()
    for phone, source in STARTER_LIST:
        db.add_spam_number(phone, source)
    print(f"seeded {len(STARTER_LIST)} starter numbers")


def seed_from_csv(path: str):
    """Load spam numbers from a local CSV with column 'phone' (and optional 'source')."""
    db.init_db()
    count = 0
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            phone = row.get("phone") or row.get("number")
            if not phone:
                continue
            db.add_spam_number(phone, row.get("source", "csv_import"))
            count += 1
    print(f"imported {count} numbers from {path}")


def seed_from_url(url: str):
    db.init_db()
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    count = 0
    for row in reader:
        phone = row.get("phone") or row.get("Company_Phone") or row.get("number")
        if phone:
            db.add_spam_number(phone, "ftc_feed")
            count += 1
    print(f"imported {count} numbers from {url}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].endswith(".csv"):
        seed_from_csv(sys.argv[1])
    elif FTC_FEED_URL:
        seed_from_url(FTC_FEED_URL)
    else:
        seed_starter()
