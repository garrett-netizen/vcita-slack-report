"""
Brute force: Ben Thompson, every single appointment, find March 18 2026.
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

BEN = "dgj09ekwfjtj0r59"

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
    target = now_et.replace(year=2026, month=3, day=18, hour=0, minute=0, second=0, microsecond=0)
    target_start = target.astimezone(timezone.utc)
    target_end = target.replace(hour=23, minute=59, second=59).astimezone(timezone.utc)

    log.info(f"Target: 2026-03-18 UTC: {target_start} to {target_end}")
    log.info(f"Staff: Ben Thompson ({BEN})")

    matched = []
    total_fetched = 0
    page = 1

    while True:
        if page % 25 == 0:
            log.info(f"Progress: page {page}, fetched {total_fetched}, matches {len(matched)}")

        data = vcita_get("/appointments", {
            "per_page": "25",
            "page": str(page),
            "staff_id": BEN,
        })

        appts = data.get("data", {}).get("appointments", [])
        if not appts:
            log.info(f"Empty page at {page}. Done.")
            break

        total_fetched += len(appts)

        for a in appts:
            start_str = a.get("start_time", "")
            if not start_str:
                continue
            start_utc = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            if target_start <= start_utc <= target_end:
                title = a.get("title", "")
                state = (a.get("state") or "").lower()
                no_show = a.get("no_show", False)
                log.info(f"FOUND: {title} | {start_str} | state={state} | no_show={no_show}")
                if title in INCLUDED_TITLES and state not in ("cancelled", "canceled") and not no_show:
                    matched.append(a)
                    log.info(f"  -> MATCHED")

        next_page = data.get("data", {}).get("next_page")
        if not next_page:
            log.info(f"No next_page at page {page}. Done.")
            break
        page = next_page

    log.info(f"FINAL: {len(matched)} matches out of {total_fetched} total Ben appointments across {page} pages")

    msg = f"Ben brute force: {len(matched)} Tinnitus Relief Consultation(s) on March 18. Scanned {total_fetched} appointments across {page} pages."
    payload = json.dumps({"text": msg}).encode()
    req = Request(SLACK_WEBHOOK_URL, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        log.info(f"Slack: {resp.status}")
    log.info("Done.")


if __name__ == "__main__":
    main()
