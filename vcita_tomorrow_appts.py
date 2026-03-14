"""
Probe: Ramsay staff_id + March 19, and dump all staff name/ID pairs.
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


def main():
    if not VCITA_TOKEN:
        log.error("VCITA_TOKEN not set")
        sys.exit(1)

    # Test: Ramsay staff_id + March 19
    log.info("=== Ramsay + 2026-03-19 ===")
    data = vcita_get("/appointments", {
        "per_page": "25",
        "page": "1",
        "staff_id": "qr87s9jbo5zwyruq",
        "start_date": "2026-03-19",
        "end_date": "2026-03-19",
    })
    if data:
        appts = data.get("data", {}).get("appointments", [])
        log.info(f"Got {len(appts)} appointments")
        for a in appts:
            log.info(f"  {a.get('title')} | {a.get('start_time')} | {a.get('staff_display_name')}")

    # Dump unique staff from first 3 pages of general results
    log.info("=== ALL STAFF IDS ===")
    staff = {}
    for pg in range(1, 4):
        d = vcita_get("/appointments", {"per_page": "25", "page": str(pg)})
        if not d:
            break
        for a in d.get("data", {}).get("appointments", []):
            name = a.get("staff_display_name", "?")
            sid = a.get("staff_id", "?")
            if name not in staff:
                staff[name] = sid

    for name, sid in sorted(staff.items()):
        log.info(f"  {name} -> {sid}")

    payload = json.dumps({"text": "Probe complete. Check deploy logs."}).encode()
    req = Request(SLACK_WEBHOOK_URL, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        log.info(f"Slack: {resp.status}")


if __name__ == "__main__":
    main()
