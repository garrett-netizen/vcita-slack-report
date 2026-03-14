"""
Probe: fetch all staff members to get their IDs.
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
VCITA_API_BASE = "https://api.vcita.biz/platform/v1"


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


def main():
    if not VCITA_TOKEN:
        log.error("VCITA_TOKEN not set")
        sys.exit(1)

    # Try /staff endpoint
    log.info("=== Trying /staff ===")
    data = vcita_get("/staff")
    if data:
        staff_list = data.get("data", {}).get("staff", data.get("data", []))
        if isinstance(staff_list, list):
            for s in staff_list:
                name = s.get("display_name", s.get("name", "?"))
                sid = s.get("id", s.get("uid", "?"))
                log.info(f"  {name} -> {sid}")
        else:
            log.info(f"  Raw data keys: {list(data.get('data', {}).keys())}")
            log.info(f"  Raw: {json.dumps(data.get('data', {}))[:500]}")

    # Try /business/staff
    log.info("=== Trying /business/staff ===")
    data2 = vcita_get("/business/staff")
    if data2:
        log.info(f"  Keys: {list(data2.keys())}")
        log.info(f"  Raw: {json.dumps(data2)[:500]}")

    # Try /scheduling/staff
    log.info("=== Trying /scheduling/staff ===")
    data3 = vcita_get("/scheduling/staff")
    if data3:
        staff_list = data3.get("data", {}).get("staff", data3.get("data", []))
        if isinstance(staff_list, list):
            for s in staff_list:
                name = s.get("display_name", s.get("name", "?"))
                sid = s.get("id", s.get("uid", "?"))
                log.info(f"  {name} -> {sid}")
        else:
            log.info(f"  Raw: {json.dumps(data3)[:500]}")

    payload = json.dumps({"text": "Staff ID probe complete. Check deploy logs."}).encode()
    req = Request(SLACK_WEBHOOK_URL, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        log.info(f"Slack: {resp.status}")


if __name__ == "__main__":
    main()
