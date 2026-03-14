"""
vcita Tomorrow Appointments -> Slack
Runs daily at 7pm ET. Counts tomorrow's Tinnitus Relief Discovery Calls and posts to Slack.

Brute forces all appointments per staff member (vCita API has no reliable
date filtering or sort). Filters to target date + matching titles in code.
Small delay between API calls to avoid Cloudflare rate limiting.
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
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
VCITA_API_BASE = "https://api.vcita.biz/platform/v1/scheduling"

STAFF = {
    "Ramsay Poindexter": "qr87s9jbo5zwyruq",
    "Ben Thompson": "dgj09ekwfjtj0r59",
    "Garrett Thompson": "w2bdnhp0nwkbxaz4",
    "Diana Vetere": "nqk7nya8tvbo1qp6",
}

INCLUDED_TITLES = {"Tinnitus Relief Consultation", "Hyperacusis Consultation"}

API_DELAY = 0.3  # seconds between API calls


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
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        log.error(f"vCita API error {e.code}: {body}")
        raise


def get_staff_appointments(staff_name, staff_id, target_start, target_end):
    """Brute force all appointments for one staff member, return matches in target window."""
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
                    matched.append(a)
                    log.info(f"  MATCHED: {title} | {start_str} | {staff_name}")

        next_page = data.get("data", {}).get("next_page")
        if not next_page:
            break
        page = next_page
        time.sleep(API_DELAY)

    elapsed = int(time.time() - t0)
    log.info(f"  {staff_name}: {len(matched)} match(es), {page} pages, {elapsed}s")
    return matched


def send_slack_message(msg):
    payload = json.dumps({"text": msg}).encode()
    req = Request(SLACK_WEBHOOK_URL, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        return resp.status


def main():
    if not VCITA_TOKEN:
        log.error("VCITA_TOKEN not set")
        sys.exit(1)
    if not SLACK_WEBHOOK_URL:
        log.error("SLACK_WEBHOOK_URL not set")
        sys.exit(1)

    now_et = datetime.now(ET)

    # TEMP: Override to Thursday March 19 for testing. Revert to tomorrow after test.
    target = now_et.replace(year=2026, month=3, day=19, hour=0, minute=0, second=0, microsecond=0)

    target_start = target.astimezone(timezone.utc)
    target_end = target.replace(hour=23, minute=59, second=59).astimezone(timezone.utc)
    target_label = target.strftime("%A, %b %-d")

    log.info(f"Target: {target_label} (UTC: {target_start} to {target_end})")

    all_matched = []
    total_start = time.time()

    for name, sid in STAFF.items():
        log.info(f"Scanning {name}...")
        matches = get_staff_appointments(name, sid, target_start, target_end)
        all_matched.extend(matches)

    total_elapsed = int(time.time() - total_start)
    total = len(all_matched)

    log.info(f"Total: {total} matches, {total_elapsed}s elapsed")

    msg = f"""📅 *Tinnitus Relief Discovery Calls -- {target_label}*

*{total} discovery calls scheduled for tomorrow.*"""

    log.info(f"Sending to Slack:\n{msg}")
    status = send_slack_message(msg)
    log.info(f"Slack response: {status}")
    log.info("Done.")


if __name__ == "__main__":
    main()
