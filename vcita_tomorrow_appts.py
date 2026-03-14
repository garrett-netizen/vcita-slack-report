"""
vcita Tomorrow Appointments -> Slack
Runs daily at 7pm ET. Counts tomorrow's scheduled discovery calls and posts to Slack.

Uses start_date/end_date API params to fetch only the target day's appointments.
vCita API caps at 25 per page, so we paginate within the filtered day.
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


def get_appointments_for_date(date_str):
    """Fetch all appointments for a specific date using API date filter."""
    all_appts = []
    page = 1
    max_pages = 20

    while page <= max_pages:
        log.info(f"Fetching page {page} for {date_str}...")
        data = vcita_get("/appointments", {
            "per_page": "25",
            "page": str(page),
            "start_date": date_str,
            "end_date": date_str,
        })

        appointments = data.get("data", {}).get("appointments", [])
        log.info(f"Page {page}: {len(appointments)} appointments")

        if not appointments:
            break

        all_appts.extend(appointments)

        next_page = data.get("data", {}).get("next_page")
        if not next_page:
            break
        page = next_page

    log.info(f"Total appointments for {date_str}: {len(all_appts)}")

    matched = []
    for appt in all_appts:
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

    # TEMP: Override to Wednesday March 18 for testing. Revert to tomorrow after test.
    target = now_et.replace(year=2026, month=3, day=18, hour=0, minute=0, second=0, microsecond=0)

    date_str = target.strftime("%Y-%m-%d")
    target_label = target.strftime("%A, %b %-d")

    log.info(f"Target: {target_label} ({date_str})")

    appointments = get_appointments_for_date(date_str)
    total = len(appointments)

    msg = f"""📅 *Tinnitus Relief Discovery Calls -- {target_label}*

*{total} discovery calls scheduled for tomorrow.*"""

    log.info(f"Sending to Slack:\n{msg}")
    status = send_slack_message(msg)
    log.info(f"Slack response: {status}")
    log.info("Done.")


if __name__ == "__main__":
    main()
