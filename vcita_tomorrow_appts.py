"""
vcita Tomorrow Appointments → Slack
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

VCITA_TOKEN = os.environ.get("VCITA_TOKEN")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
VCITA_API_BASE = "https://api.vcita.biz/v2"


def vcita_get(endpoint, params=None):
    """Make an authenticated GET request to vCita API."""
    url = f"{VCITA_API_BASE}{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"

    req = Request(url)
    req.add_header("Authorization", f"Bearer {VCITA_TOKEN}")
    req.add_header("Content-Type", "application/json")

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        log.error(f"vCita API error {e.code}: {body}")
        raise


def get_tomorrow_appointments():
    """Fetch all appointments scheduled for tomorrow (ET)."""
    now_et = datetime.now(ET)
    tomorrow = now_et + timedelta(days=1)

    # Tomorrow midnight to midnight in UTC for the API query
    tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)

    start_utc = tomorrow_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = tomorrow_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_appointments = []
    page = 0

    while True:
        log.info(f"Fetching appointments page {page}...")
        data = vcita_get("/appointments", {
            "updated_since": start_utc,
            "updated_until": end_utc,
            "page": str(page),
        })

        appointments = data.get("data", data.get("appointments", []))

        if not appointments:
            break

        all_appointments.extend(appointments)

        # vCita paginates at 25 per page
        if len(appointments) < 25:
            break
        page += 1

    log.info(f"Fetched {len(all_appointments)} total appointment records")
    return all_appointments, tomorrow


def filter_scheduled(appointments):
    """Filter to only scheduled/confirmed appointments (exclude cancelled, no-shows)."""
    excluded_statuses = {"cancelled", "canceled", "no_show", "noshow", "deleted"}
    scheduled = []
    for appt in appointments:
        status = (appt.get("status") or "").lower().replace(" ", "_")
        if status not in excluded_statuses:
            scheduled.append(appt)
    return scheduled


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

    appointments, tomorrow = get_tomorrow_appointments()
    scheduled = filter_scheduled(appointments)
    total = len(scheduled)

    tomorrow_label = tomorrow.strftime("%A, %b %-d")
    day_of_week = tomorrow.strftime("%A")

    msg = f"""📅 *vCita Appointments — {tomorrow_label}*

*Tomorrow's Scheduled Appointments: {total}*"""

    log.info(f"Sending to Slack:\n{msg}")
    status = send_slack_message(msg)
    log.info(f"Slack response: {status}")
    log.info("Done.")


if __name__ == "__main__":
    main()
