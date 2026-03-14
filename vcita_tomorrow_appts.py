"""
vcita Tomorrow Appointments -> Slack
Runs daily at 7pm ET. Counts tomorrow's scheduled appointments and posts to Slack.
"""

import os
import sys
import json
import logging
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
PER_PAGE = 100

INCLUDED_TITLES = {"Tinnitus Relief Consultation", "Hyperacusis Consultation"}


def vcita_get(endpoint, params=None):
    """Make an authenticated GET request to vCita API."""
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


def get_appointments_for_date(target):
    """Fetch all matching appointments for a specific date (ET)."""
    target_start = target.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    target_end = target.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(timezone.utc)

    log.info(f"Target window (UTC): {target_start} to {target_end}")

    all_in_window = []
    page = 1
    max_pages = 50

    while page <= max_pages:
        log.info(f"Fetching page {page}...")
        data = vcita_get("/appointments", {
            "per_page": str(PER_PAGE),
            "page": str(page),
            "sort": "start_time",
            "order": "desc",
        })

        appointments = data.get("data", {}).get("appointments", [])
        log.info(f"Page {page}: {len(appointments)} appointments")

        if not appointments:
            break

        earliest_on_page = None

        for appt in appointments:
            start_str = appt.get("start_time", "")
            if not start_str:
                continue

            start_utc = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

            if earliest_on_page is None or start_utc < earliest_on_page:
                earliest_on_page = start_utc

            if target_start <= start_utc <= target_end:
                all_in_window.append(appt)

        log.info(f"Page {page} earliest: {earliest_on_page}")
        log.info(f"Running matches so far: {len(all_in_window)}")

        if earliest_on_page and earliest_on_page < target_start:
            log.info("Earliest on page is before target start. Done paginating.")
            break

        next_page = data.get("data", {}).get("next_page")
        if not next_page:
            log.info("No more pages.")
            break
        page = next_page

    matched = []
    for appt in all_in_window:
        state = (appt.get("state") or "").lower()
        no_show = appt.get("no_show", False)
        title = appt.get("title", "")

        if state in ("cancelled", "canceled") or no_show:
            continue
        if title not in INCLUDED_TITLES:
            continue

        matched.append(appt)
        log.info(f"MATCHED: {title} | {appt.get('start_time')} | {appt.get('staff_display_name')}")

    return matched


def send_slack_message(msg):
    """Post a message to Slack via incoming webhook."""
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

    # TEMP: Override to Wed March 18 and Thu March 19 for testing.
    wed = now_et.replace(year=2026, month=3, day=18, hour=0, minute=0, second=0, microsecond=0)
    thu = now_et.replace(year=2026, month=3, day=19, hour=0, minute=0, second=0, microsecond=0)

    log.info("=== Fetching Wednesday March 18 ===")
    wed_appts = get_appointments_for_date(wed)
    log.info("=== Fetching Thursday March 19 ===")
    thu_appts = get_appointments_for_date(thu)

    wed_label = wed.strftime("%A, %b %-d")
    thu_label = thu.strftime("%A, %b %-d")

    msg = f"""📅 *Tinnitus Relief Discovery Calls*

*{wed_label}:* {len(wed_appts)} discovery calls
*{thu_label}:* {len(thu_appts)} discovery calls"""

    log.info(f"Sending to Slack:\n{msg}")
    status = send_slack_message(msg)
    log.info(f"Slack response: {status}")
    log.info("Done.")


if __name__ == "__main__":
    main()
