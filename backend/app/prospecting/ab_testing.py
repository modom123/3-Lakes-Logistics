"""Step 49: A/B testing harness for SMS templates."""
from __future__ import annotations

import hashlib


TEMPLATES: dict[str, list[dict]] = {
    "founders_v1": [
        {"variant": "A", "body": "Hey {first_name}, just 1,000 Founders spots in our dispatch program — $200/mo locked for life. Want the link?"},
        {"variant": "B", "body": "{first_name}, we're holding {remaining} {trailer_type} Founders spots. Full dispatch, $200/mo. Interested?"},
    ],
}


def pick_variant(key: str, bucket_id: str) -> dict:
    """Deterministic bucket based on lead id so the same lead always sees the same variant."""
    variants = TEMPLATES[key]
    h = int(hashlib.md5(f"{key}:{bucket_id}".encode()).hexdigest(), 16)
    return variants[h % len(variants)]
