#!/usr/bin/env python3
"""
Rentcast API data refresh for the Asheville market dashboard.
Designed to run on the 1st and 15th of each month via cron.

Usage:
  python update_data.py             # normal run (only executes on 1st or 15th)
  python update_data.py --force     # bypass schedule check, still respects API budget
  python update_data.py --dry-run   # simulate without making any API calls
"""

import os
import sys
import json
import time
import logging
import argparse
import requests
import pandas as pd
from datetime import datetime, date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
CSV_PATH  = BASE_DIR / "asheville_market_data.csv"
USAGE_PATH = BASE_DIR / "api_usage.json"
LOG_PATH  = BASE_DIR / "update_log.txt"

# ── API config ────────────────────────────────────────────────────────────────
MONTHLY_LIMIT  = 50
WARN_THRESHOLD = 40   # surface a warning when usage hits this
CALLS_PER_RUN  = 15   # one call per zip code
API_BASE       = "https://api.rentcast.io/v1/markets"

ZIP_NEIGHBORHOODS = {
    "28801": "Downtown Asheville",
    "28803": "South Asheville",
    "28804": "North Asheville",
    "28806": "West Asheville",
    "28805": "East Asheville",
    "28715": "Candler",
    "28730": "Fairview",
    "28732": "Fletcher",
    "28748": "Leicester",
    "28778": "Swannanoa",
    "28787": "Weaverville",
    "28701": "Alexander",
    "28704": "Arden",
    "28709": "Barnardsville",
    "28711": "Black Mountain",
}


# ── Logging ───────────────────────────────────────────────────────────────────
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ── Usage tracking ────────────────────────────────────────────────────────────
def load_usage() -> dict:
    current_month = date.today().strftime("%Y-%m")
    if USAGE_PATH.exists():
        with open(USAGE_PATH) as f:
            usage = json.load(f)
        if usage.get("month") != current_month:
            logging.info(f"New month ({current_month}) — resetting API usage counter.")
            usage = _fresh_usage(current_month)
            save_usage(usage)
    else:
        usage = _fresh_usage(current_month)
        save_usage(usage)
    return usage


def _fresh_usage(month: str) -> dict:
    return {
        "month": month,
        "calls_used": 0,
        "limit": MONTHLY_LIMIT,
        "pulls": [],
    }


def save_usage(usage: dict):
    with open(USAGE_PATH, "w") as f:
        json.dump(usage, f, indent=2)


# ── API helpers ───────────────────────────────────────────────────────────────
def fetch_zip(zip_code: str, api_key: str) -> dict:
    resp = requests.get(
        API_BASE,
        params={"zipCode": zip_code, "dataType": "All", "historyRange": "6"},
        headers={"X-Api-Key": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def flatten_response(data: dict, zip_code: str, neighborhood: str) -> pd.DataFrame:
    flat = pd.json_normalize(data, sep=".")
    # Serialize nested dicts/lists so they survive CSV round-trips
    for col in flat.columns:
        if flat[col].dtype == object:
            flat[col] = flat[col].apply(
                lambda x: json.dumps(x) if isinstance(x, (dict, list)) else x
            )
    flat.insert(0, "zipCode", zip_code)
    flat.insert(1, "neighborhood", neighborhood)
    flat["pulled_at"] = datetime.now().isoformat()
    return flat


# ── CSV update ────────────────────────────────────────────────────────────────
def update_csv(new_df: pd.DataFrame):
    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, dtype={"zipCode": str})
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(CSV_PATH, index=False)
    logging.info(f"CSV updated — {len(combined)} total rows saved to {CSV_PATH.name}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Refresh Asheville market data from Rentcast.")
    parser.add_argument("--force",   action="store_true", help="Run regardless of today's date")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without making API calls")
    args = parser.parse_args()

    setup_logging()
    logging.info("=" * 60)
    logging.info("Asheville market data refresh starting")

    # Schedule check — skip unless it's the 1st or 15th (or --force/--dry-run)
    today = date.today()
    if not args.force and not args.dry_run and today.day not in (1, 15):
        logging.info(
            f"Today is the {today.day}th — scheduled days are the 1st and 15th. Exiting."
        )
        return

    # API key
    api_key = os.environ.get("RENTCAST_API_KEY")
    if not api_key and not args.dry_run:
        logging.error("RENTCAST_API_KEY environment variable is not set. Exiting.")
        sys.exit(1)

    # Load and display usage
    usage = load_usage()
    calls_used = usage["calls_used"]
    remaining  = usage["limit"] - calls_used
    logging.info(
        f"API usage this month: {calls_used}/{usage['limit']} calls used, "
        f"{remaining} remaining."
    )

    # Warn if close to limit
    if calls_used >= WARN_THRESHOLD:
        logging.warning(
            f"⚠️  Approaching monthly limit: {calls_used}/{usage['limit']} calls used."
        )

    # Budget check — abort if a full refresh would exceed the limit
    if remaining < CALLS_PER_RUN:
        logging.warning(
            f"Not enough API calls remaining ({remaining}) for a full refresh "
            f"({CALLS_PER_RUN} needed). Skipping to stay within monthly limit."
        )
        sys.exit(0)

    if args.dry_run:
        logging.info("[DRY RUN] Would fetch data for these zip codes:")
        for z, n in ZIP_NEIGHBORHOODS.items():
            logging.info(f"  {z}  {n}")
        logging.info("[DRY RUN] No API calls made. No CSV changes.")
        return

    # Fetch each zip code
    rows = []
    successful = 0
    failed_zips = []

    for zip_code, neighborhood in ZIP_NEIGHBORHOODS.items():
        try:
            logging.info(f"  Fetching {neighborhood} ({zip_code}) ...")
            data = fetch_zip(zip_code, api_key)
            row_df = flatten_response(data, zip_code, neighborhood)
            rows.append(row_df)
            successful += 1
            time.sleep(0.4)   # gentle rate limiting between calls
        except requests.HTTPError as e:
            logging.error(f"  HTTP error for {zip_code}: {e}")
            failed_zips.append(zip_code)
        except Exception as e:
            logging.error(f"  Unexpected error for {zip_code}: {e}")
            failed_zips.append(zip_code)

    # Write results
    if rows:
        new_df = pd.concat(rows, ignore_index=True)
        update_csv(new_df)

    # Persist updated usage
    usage["calls_used"] += successful
    usage["pulls"].append({
        "timestamp":            datetime.now().isoformat(),
        "successful_zips":      successful,
        "failed_zips":          failed_zips,
        "calls_charged":        successful,
        "monthly_total_after":  usage["calls_used"],
    })
    save_usage(usage)

    status = "✅ complete" if not failed_zips else f"⚠️  complete with {len(failed_zips)} failure(s)"
    logging.info(
        f"Refresh {status}: {successful} zip codes updated. "
        f"Monthly total: {usage['calls_used']}/{usage['limit']} calls."
    )
    if failed_zips:
        logging.warning(f"Failed zip codes (not charged): {failed_zips}")


if __name__ == "__main__":
    main()
