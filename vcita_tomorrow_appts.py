"""
Find Diana's staff_id. Paginate until we see her name. Stop immediately when found.
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

    staff = {}
    page = 1
    found_diana = False

    while True:
        if page % 25 == 0:
            log.info(f"Page {page}, staff found so far: {len(staff)}")

        d = vcita_get("/appointments", {"per_page": "25", "page": str(page)})
        if not d:
            break
        appts = d.get("data", {}).get("appointments", [])
        if not appts:
            break

        for a in appts:
            name = a.get("staff_display_name", "")
            sid = a.get("staff_id", "")
            if name and name not in staff:
                staff[name] = sid
                log.info(f"NEW: {name} -> {sid}")
                if "diana" in name.lower() or "vetere" in name.lower():
                    found_diana = True

        if found_diana:
            log.info("Found Diana. Stopping.")
            break

        next_page = d.get("data", {}).get("next_page")
        if not next_page:
            break
        page = next_page

    log.info(f"=== ALL STAFF ({len(staff)}) after {page} pages ===")
    for name, sid in sorted(staff.items()):
        log.info(f"  {name} -> {sid}")

    msg = "Staff IDs:\n" + "\n".join(f"{name}: {sid}" for name, sid in sorted(staff.items()))
    payload = json.dumps({"text": msg}).encode()
    req = Request(SLACK_WEBHOOK_URL, data=payload)
    req.add_header("Content-Type", "application/json")
    with urlopen(req) as resp:
        log.info(f"Slack: {resp.status}")


if __name__ == "__main__":
    main()
