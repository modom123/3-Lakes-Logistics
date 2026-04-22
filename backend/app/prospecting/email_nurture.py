"""Step 50: Email nurture sequence (authored by Nexus).

7-email cadence over 30 days for leads that don't convert on first touch.
"""
from __future__ import annotations

NURTURE_SEQUENCE = [
    {"day": 0,  "subject": "Your $200/mo dispatch spot (1 of 1,000)",
     "body_md": "**{first_name}** — we're holding a Founders slot for {company_name}...\n\n- Flat $200/mo, locked for life\n- Full-service dispatch, 10% on loads\n- Weekly ACH payouts via Settler\n\n**[Claim spot →](https://3lakeslogistics.com/?utm={utm})**"},
    {"day": 2,  "subject": "{first_name}, 3 questions about your trucks",
     "body_md": "Quick one — how many of your {fleet_size} trucks run dry van vs reefer? I can pull your DOT {dot_number} and show you what loads we're covering this week."},
    {"day": 5,  "subject": "Carriers like yours are averaging 2.8 $/mi",
     "body_md": "Here's the last 30 days of rates from {equipment_type} loads we dispatched."},
    {"day": 10, "subject": "Quick reminder — Founders price locks at 1,000",
     "body_md": "Dry Van has {dry_van_remaining} spots left. Reefer {reefer_remaining}. Once we hit 1,000 the price goes to market rate forever."},
    {"day": 15, "subject": "Your CSA snapshot",
     "body_md": "I pulled your SAFER report — here's what brokers see."},
    {"day": 22, "subject": "Last call — locking Founders",
     "body_md": "We close Founders pricing at 1,000 carriers. You're number {queue_position} in line."},
    {"day": 30, "subject": "Switching you to our quarterly newsletter",
     "body_md": "No worries on the Founders spot. We'll send rate snapshots quarterly. Reply anytime if you change your mind."},
]
