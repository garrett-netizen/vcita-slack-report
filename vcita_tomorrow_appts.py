"""
Final test: Ramsay Poindexter, March 19, 2026.
Query by staff_id only. Paginate all pages. Filter to 2026-03-19 in code.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

VCITA_TOKEN = (os.environ.get("VCITA_TOKEN") or "").strip()
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
VCITA_API_BASE = "https://api.vcita.biz/platform/v1/scheduling"

RAMSAY_STAFF_ID = "qr87s9jbo5zwyruq"


def vcita_get(endpoint, params=None):
    url = f"{VCITA_API_BASE}{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    req = Request(url)
    req.add_header("Authorization", f"Bearer {VCITA_TOKEN}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        log.error(f"vCita API error {e.code}: {body}")
        raise


def main():
    if not VCITA_TOKEN:
        log.error("VCITA_TOKEN not set")
        sys.exit(1)
    if not SLACK_WEBHOOK_URL:
        log.error("SLACK_WEBHOOK_URL not set")
        sys.exit(1)

    now_et = datetime.now(ET)
    target = now_et.replace(year=2026, month=3, day=19, hour=0, minute=0, second=0, microsecond=0)
    target_start = target.astimezone(timezone.utc)
    target_end = target.replace(hour=23, minute=59, second=59).astimezone(timezone.utc)

    log.info(f"Target: 2026-03-19 (UTC: {target_start} to {target_end})")
    log.info(f"Staff: Ramsay Poindexter ({RAMSAY_STAFF_ID})")

    all_appts = []
    page = 1
    max_pages = 100

    while page <= max_pages:
        log.info(f"Fetching page {page}...")
        data = vcita_get("/appointments", {
            "per_page": "25",
            "page": str(page),
            "staff_id": RAMSAY_STAFF_ID,
        })

        appts = data.get("data", {}).get("appointments", [])
        log.info(f"Page {page}: {len(appts)} appointments")

        if not appts:
            break

        for a in appts:
            start_str = a.get("start_time", "")
            if not start_str:
                continue
            start_utc = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

            if target_start <= start_utc <= target_end:
                title = a.get("title", "")
                state = (a.get("state") or "").lower()
                log.info(f"  IN WINDOW: {title} | {start_str} | state={state}")
                all_appts.append(a)

        next_page = data.get("data", {}).get("next_page")
        if not next_page:
            log.info("No more pages.")
            break
        page = next_page

    log.info(f"Total Ramsay appointments on 2026-03-19: {len(all_appts)}")
    for a in all_appts:
        log.info(f"  {a.get('title')} | {a.get('start_time')}")

    payload = json.dumps({"text": f"Ramsay March 19 test: {len(all_appts)} appointments found. Check deploy logs."}).encode()
    req = Request(SLACK_WEBHOOK_URL, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        log.info(f"Slack: {resp.status}")
    log.info("Done.")


if __name__ == "__main__":
    main()
