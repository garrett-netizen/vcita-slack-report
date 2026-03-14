"""
vcita Staff Appointment Scanner
Scans one staff member's vCita appointments for tomorrow's discovery calls.
Posts results to #vcita-data-dump Slack channel as structured JSON.

Deploy as 4 separate Railway cron services, each with a different STAFF_NAME env var:
  - Ramsay Poindexter
  - Ben Thompson
  - Garrett Thompson
  - Diana Vetere

Env vars needed:
  - VCITA_TOKEN: vCita API bearer token
  - STAFF_NAME: one of the 4 names above
  - DUMP_WEBHOOK_URL: Slack incoming webhook for #vcita-data-dump
"""

import os
import sys
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

VCITA_TOKEN = (os.environ.get("VCITA_TOKEN") or "").strip()
DUMP_WEBHOOK_URL = os.environ.get("DUMP_WEBHOOK_URL")
STAFF_NAME = (os.environ.get("STAFF_NAME") or "").strip()
VCITA_API_BASE = "https://api.vcita.biz/platform/v1/scheduling"

STAFF_IDS = {
    "Ramsay Poindexter": "qr87s9jbo5zwyruq",
    "Ben Thompson": "dgj09ekwfjtj0r59",
    "Garrett Thompson": "w2bdnhp0nwkbxaz4",
    "Diana Vetere": "nqk7nya8tvbo1qp6",
}

INCLUDED_TITLES = {"Tinnitus Relief Consultation", "Hyperacusis Consultation"}


def vcita_get(endpoint, params=None):
    url = f"{VCITA_API_BASE}{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    req = Request(url)
    req.add_header("Authorization", f"Bearer {VCITA_TOKEN}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def slack_post(webhook_url, msg):
    payload = json.dumps({"text": msg}).encode()
    req = Request(webhook_url, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        return resp.status


def get_staff_appointments(staff_name, staff_id, target_start, target_end):
    matched = []
    page = 1
    t0 = time.time()

    while True:
        if page % 50 == 0:
            elapsed = int(time.time() - t0)
            log.info(f"  {staff_name}: page {page}... ({elapsed}s)")

        data = vcita_get("/appointments", {
            "per_page": "25",
            "page": str(page),
            "staff_id": staff_id,
        })

        appts = data.get("data", {}).get("appointments", [])
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
                no_show = a.get("no_show", False)

                if title in INCLUDED_TITLES and state not in ("cancelled", "canceled") and not no_show:
                    matched.append({
                        "title": title,
                        "start_time": start_str,
                        "staff": staff_name,
                        "client": f"{a.get('client_first_name', '')} {a.get('client_last_name', '')}".strip(),
                    })
                    log.info(f"  MATCHED: {title} | {start_str} | {staff_name}")

        next_page = data.get("data", {}).get("next_page")
        if not next_page:
            break
        page = next_page

    elapsed = int(time.time() - t0)
    log.info(f"  {staff_name}: {len(matched)} match(es), {page} pages, {elapsed}s")
    return matched


def main():
    if not VCITA_TOKEN:
        log.error("VCITA_TOKEN not set")
        sys.exit(1)
    if not DUMP_WEBHOOK_URL:
        log.error("DUMP_WEBHOOK_URL not set")
        sys.exit(1)
    if not STAFF_NAME:
        log.error("STAFF_NAME not set")
        sys.exit(1)
    if STAFF_NAME not in STAFF_IDS:
        log.error(f"Unknown STAFF_NAME: {STAFF_NAME}")
        sys.exit(1)

    staff_id = STAFF_IDS[STAFF_NAME]
    now_et = datetime.now(ET)

    # TEMP: Override to Thursday March 19 for testing. Revert to tomorrow after test.
    target = now_et.replace(year=2026, month=3, day=19, hour=0, minute=0, second=0, microsecond=0)

    target_start = target.astimezone(timezone.utc)
    target_end = target.replace(hour=23, minute=59, second=59).astimezone(timezone.utc)
    target_date = target.strftime("%Y-%m-%d")

    log.info(f"Target: {target_date}")
    log.info(f"Staff: {STAFF_NAME} ({staff_id})")

    matches = get_staff_appointments(STAFF_NAME, staff_id, target_start, target_end)

    result = {
        "source": "vcita",
        "staff": STAFF_NAME,
        "date": target_date,
        "count": len(matches),
        "appointments": matches,
    }

    dump_msg = f"vcita|{target_date}|{STAFF_NAME}|{json.dumps(result)}"
    slack_post(DUMP_WEBHOOK_URL, dump_msg)

    log.info(f"Posted to #vcita-data-dump: {len(matches)} match(es) for {STAFF_NAME} on {target_date}")
    log.info("Done.")


if __name__ == "__main__":
    main()
