"""Step 49: A/B testing harness for SMS templates."""
from __future__ import annotations

import hashlib

TEMPLATES: dict[str, list[dict]] = {
    "founders_v1": [
        {"variant": "A",
         "body": "Hey {first_name}, just 1,000 Founders spots in our dispatch program — $200/mo locked for life. Want the link?"},
        {"variant": "B",
         "body": "{first_name}, we're holding {remaining} {trailer_type} Founders spots. Full dispatch, $200/mo. Interested?"},
    ],
    "dispatch_v2": [
        {"variant": "A",
         "body": "{first_name} — 3 Lakes Logistics here. We dispatch {trailer_type} owner-ops across 48 states, 10% flat. No hidden fees. Worth a quick call?"},
        {"variant": "B",
         "body": "Hey {first_name}, looking for a dispatcher? We handle everything — load booking, rate conf, check calls. Flat 10%. Reply YES to learn more."},
    ],
    "rate_highlight": [
        {"variant": "A",
         "body": "{first_name}, our {trailer_type} carriers averaged $2.85/mi last month. We handle dispatch, you keep 90%. Reply RATES for a full breakdown."},
        {"variant": "B",
         "body": "Hi {first_name} — quick question: what rate/mi are you averaging now? Our owner-ops on {trailer_type} are doing $2.80-3.10. We might be able to do better."},
    ],
    "win_back": [
        {"variant": "A",
         "body": "Hey {first_name}, it's been a while. We just opened {remaining} spots at our Founders rate — $200/mo, locked. Still interested? Reply YES."},
        {"variant": "B",
         "body": "{first_name} — prices went up to market rate for new carriers. If you locked in at $200 when we talked, that's still honored. Reply LOCK to claim it."},
    ],
    "referral_ask": [
        {"variant": "A",
         "body": "Hey {first_name}, know any other owner-ops looking for dispatch? Send them our way — their first month is on us ($200 value). Reply REFER to share the link."},
        {"variant": "B",
         "body": "{first_name}, we're growing our fleet. If you refer an owner-op who signs up, you both get a free month. Know anyone?"},
    ],
}


def pick_variant(key: str, bucket_id: str) -> dict:
    """Deterministic bucket based on lead id so the same lead always sees the same variant."""
    variants = TEMPLATES.get(key)
    if not variants:
        # Fall back to founders_v1 variant A rather than raising KeyError
        return TEMPLATES["founders_v1"][0]
    h = int(hashlib.md5(f"{key}:{bucket_id}".encode()).hexdigest(), 16)
    return variants[h % len(variants)]
