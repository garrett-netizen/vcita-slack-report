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
PER_PAGE = 25


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


def get_tomorrow_appointments():
    """Fetch all appointments scheduled for tomorrow (ET)."""
    now_et = datetime.now(ET)
    tomorrow = now_et + timedelta(days=1)

    # Tomorrow's date boundaries in UTC
    tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(timezone.utc)

    tomorrow_appointments = []
    page = 1

    while True:
        log.info(f"Fetching appointments page {page}...")
        data = vcita_get("/appointments", {
            "per_page": str(PER_PAGE),
            "page": str(page),
            "sort": "start_time",
            "order": "desc",
        })

        appointments = data.get("data", {}).get("appointments", [])

        if not appointments:
            break

        for appt in appointments:
            log.info(json.dumps(appt, indent=2))
            start_str = appt.get("start_time", "")
            if not start_str:
                continue

            # Parse start_time (comes as ISO 8601 UTC)
            start_utc = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

            # If appointment is before tomorrow, we are done (sorted desc)
            if start_utc < tomorrow_start:
                log.info("Reached appointments before tomorrow. Stopping.")
                return tomorrow_appointments, tomorrow

            # If appointment is within tomorrow's window
            if tomorrow_start <= start_utc <= tomorrow_end:
                state = (appt.get("state") or "").lower()
                no_show = appt.get("no_show", False)

                # Only count scheduled/confirmed appointments
                if state not in ("cancelled", "canceled") and not no_show:
                    tomorrow_appointments.append(appt)

        next_page = data.get("data", {}).get("next_page")
        if not next_page:
            break
        page = next_page

    return tomorrow_appointments, tomorrow


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
    total = len(appointments)

    tomorrow_label = tomorrow.strftime("%A, %b %-d")

    msg = f"""📅 *vCita Appointments -- {tomorrow_label}*

*Tomorrow's Scheduled Appointments: {total}*"""

    log.info(f"Sending to Slack:\n{msg}")
    status = send_slack_message(msg)
    log.info(f"Slack response: {status}")
    log.info("Done.")


if __name__ == "__main__":
    main()
