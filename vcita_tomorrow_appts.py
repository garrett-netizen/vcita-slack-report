"""
vCita API probe: test undocumented filter parameters.
"""

import os
import sys
import json
import logging
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

VCITA_TOKEN = (os.environ.get("VCITA_TOKEN") or "").strip()
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
VCITA_API_BASE = "https://api.vcita.biz/platform/v1/scheduling"


def vcita_get(endpoint, params=None):
    url = f"{VCITA_API_BASE}{endpoint}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"

    log.info(f"GET {url}")
    req = Request(url)
    req.add_header("Authorization", f"Bearer {VCITA_TOKEN}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0")

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        log.error(f"HTTP {e.code}: {body[:500]}")
        return None


def test_params(label, params):
    log.info(f"=== TEST: {label} ===")
    data = vcita_get("/appointments", params)
    if data is None:
        log.info("FAILED (error)")
        return
    appts = data.get("data", {}).get("appointments", [])
    meta = {k: v for k, v in data.get("data", {}).items() if k != "appointments"}
    log.info(f"Got {len(appts)} appointments. Meta: {json.dumps(meta)}")
    if appts:
        log.info(f"First: {appts[0].get('title')} | {appts[0].get('start_time')}")
        log.info(f"Last: {appts[-1].get('title')} | {appts[-1].get('start_time')}")


def main():
    if not VCITA_TOKEN:
        log.error("VCITA_TOKEN not set")
        sys.exit(1)

    # Test 1: staff_id filter (Ramsay Poindexter)
    test_params("staff_id=qr87s9jbo5zwyruq", {
        "per_page": "25",
        "page": "1",
        "staff_id": "qr87s9jbo5zwyruq",
    })

    # Test 2: start_time_from / start_time_to
    test_params("start_time_from/to March 18", {
        "per_page": "25",
        "page": "1",
        "start_time_from": "2026-03-18T00:00:00Z",
        "start_time_to": "2026-03-19T00:00:00Z",
    })

    # Test 3: from/to (shorter param names)
    test_params("from/to March 18", {
        "per_page": "25",
        "page": "1",
        "from": "2026-03-18T00:00:00Z",
        "to": "2026-03-19T00:00:00Z",
    })

    # Test 4: start_date / end_date
    test_params("start_date/end_date March 18", {
        "per_page": "25",
        "page": "1",
        "start_date": "2026-03-18",
        "end_date": "2026-03-18",
    })

    # Test 5: date_from / date_to
    test_params("date_from/date_to March 18", {
        "per_page": "25",
        "page": "1",
        "date_from": "2026-03-18",
        "date_to": "2026-03-18",
    })

    # Test 6: service_id filter (Tinnitus Relief Consultation)
    test_params("service_id=rs869fhcozi2442v", {
        "per_page": "25",
        "page": "1",
        "service_id": "rs869fhcozi2442v",
    })

    # Send completion notice
    payload = json.dumps({"text": "API probe complete. Check deploy logs."}).encode()
    req = Request(SLACK_WEBHOOK_URL, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        log.info(f"Slack: {resp.status}")


if __name__ == "__main__":
    main()
