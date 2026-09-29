# ─────────────────────────────────────────────────────────────
# File:     backend/scripts/launch_readiness.py
# Created:  2026-09-29 22:31 UTC
# Purpose:  CLI go / no-go before opening for business.
# ─────────────────────────────────────────────────────────────
"""Print the launch readiness checklist.

    cd backend && python -m scripts.launch_readiness [--verify-stripe] [--leads]

Exit code 0 = ready, 1 = blocking items open.
"""
from __future__ import annotations

import argparse
import sys

from app.launch_readiness import check


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-stripe", action="store_true", help="read price ids from Stripe and check amounts")
    ap.add_argument("--leads", action="store_true", help="count callable leads in Supabase")
    a = ap.parse_args()
    r = check(verify_stripe=a.verify_stripe, include_leads=a.leads)
    for section, blocking in (("BLOCKING", True), ("RECOMMENDED", False)):
        print(f"\n{section}")
        for i in r["items"]:
            if i["blocking"] is blocking:
                print(f"  [{'x' if i['ok'] else ' '}] {i['name']}" + ("" if i["ok"] else f"\n        → {i['fix']}"))
    print(f"\n{'READY TO LAUNCH' if r['ready'] else 'NOT READY'} — "
          f"{r['blocking_open']} blocking, {r['recommended_open']} recommended open")
    return 0 if r["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
