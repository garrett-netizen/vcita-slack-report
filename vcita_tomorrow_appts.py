"""
vcita Tomorrow Appointments -> Slack
DEBUG VERSION: Logging raw pagination data to diagnose why we stop at page 1.
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

    # Just fetch page 1 and dump all the metadata
    log.info("Fetching page 1 with per_page=100, sort=start_time, order=desc...")
    data = vcita_get("/appointments", {
        "per_page": "100",
        "page": "1",
        "sort": "start_time",
        "order": "desc",
    })

    # Log the top-level keys (not appointments themselves)
    top_level = {k: v for k, v in data.items() if k != "data"}
    log.info(f"Top-level keys (non-data): {json.dumps(top_level)}")

    inner = data.get("data", {})
    appts = inner.get("appointments", [])
    inner_meta = {k: v for k, v in inner.items() if k != "appointments"}
    log.info(f"Inner data keys (non-appointments): {json.dumps(inner_meta)}")
    log.info(f"Appointment count: {len(appts)}")

    if appts:
        first = appts[0].get("start_time", "?")
        last = appts[-1].get("start_time", "?")
        log.info(f"First appt start_time: {first}")
        log.info(f"Last appt start_time: {last}")

    # Now fetch page 2 explicitly
    log.info("Fetching page 2...")
    data2 = vcita_get("/appointments", {
        "per_page": "100",
        "page": "2",
        "sort": "start_time",
        "order": "desc",
    })

    inner2 = data2.get("data", {})
    appts2 = inner2.get("appointments", [])
    inner_meta2 = {k: v for k, v in inner2.items() if k != "appointments"}
    log.info(f"Page 2 inner meta: {json.dumps(inner_meta2)}")
    log.info(f"Page 2 appointment count: {len(appts2)}")

    if appts2:
        first2 = appts2[0].get("start_time", "?")
        last2 = appts2[-1].get("start_time", "?")
        log.info(f"Page 2 first appt start_time: {first2}")
        log.info(f"Page 2 last appt start_time: {last2}")

    # Send a simple test message
    payload = json.dumps({"text": "DEBUG: pagination test complete. Check deploy logs."}).encode()
    req = Request(SLACK_WEBHOOK_URL, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        log.info(f"Slack response: {resp.status}")

    log.info("Done.")


if __name__ == "__main__":
    main()
