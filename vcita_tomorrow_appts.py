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


def get_target_appointments():
    """Fetch all appointments scheduled for the target day (ET)."""
    now_et = datetime.now(ET)

    # TEMP: Override to Tuesday March 17 for testing. Revert to tomorrow after test.
    target = now_et.replace(year=2026, month=3, day=17, hour=0, minute=0, second=0, microsecond=0)

    # Target day boundaries in UTC
    target_start = target.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    target_end = target.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(timezone.utc)

    log.info(f"Target window: {target_start} to {target_end}")

    target_appointments = []
    page = 1

    while True:
        log.info(f"Fetching appointments page {page}...")
        data = vcita_get("/appointments", {
            "per_page": str(PER_PAGE),
            "page": str(page),
            "sort": "start_time",
            "order": "asc",
        })

        appointments = data.get("data", {}).get("appointments", [])
        log.info(f"Page {page}: got {len(appointments)} appointments")

        if not appointments:
            break

        for appt in appointments:
            start_str = appt.get("start_time", "")
            if not start_str:
                continue

            start_utc = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

            # Skip anything before target day
            if start_utc < target_start:
                continue

            # Past target day, no need to keep going
            if start_utc > target_end:
                log.info("Passed target day. Stopping.")
                return target_appointments, target

            # Within target day window
            state = (appt.get("state") or "").lower()
            no_show = appt.get("no_show", False)
            title = appt.get("title", "")

            log.info(f"  {title} | {start_utc} | state={state}")

            if state not in ("cancelled", "canceled") and not no_show and title in INCLUDED_TITLES:
                log.info(f"  -> MATCHED")
                target_appointments.append(appt)

        next_page = data.get("data", {}).get("next_page")
        if not next_page:
            log.info("No more pages.")
            break
        page = next_page

    return target_appointments, target


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

    appointments, target = get_target_appointments()
    total = len(appointments)

    target_label = target.strftime("%A, %b %-d")

    msg = f"""📅 *Tinnitus Relief Discovery Calls -- {target_label}*

*{total} discovery calls scheduled for tomorrow.*"""

    log.info(f"Sending to Slack:\n{msg}")
    status = send_slack_message(msg)
    log.info(f"Slack response: {status}")
    log.info("Done.")


if __name__ == "__main__":
    main()
