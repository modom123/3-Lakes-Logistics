"""Step 54: Social listener for Reddit/Facebook/X keywords."""
from __future__ import annotations

import time
from typing import Any

import httpx

from ..logging_service import log_agent
from ..supabase_client import get_supabase

SIGNAL_KEYWORDS = [
    "looking for dispatcher", "need dispatch help", "owner operator dispatch",
    "new mc number", "just got my authority", "dispatch percentage",
    "factoring company recommendation", "load board suggestions",
]

_REDDIT_SUBS = [
    "Truckers", "TruckDrivers", "owner_operators",
    "FreightBrokers", "trucking",
]
_REDDIT_QUERIES = ["dispatcher", "owner operator authority", "dispatch percentage"]
_REDDIT_HEADERS = {"User-Agent": "3LakesLogisticsBot/1.0 (+https://3lakeslogistics.com)"}


def match_signals(post_text: str) -> list[str]:
    t = (post_text or "").lower()
    return [kw for kw in SIGNAL_KEYWORDS if kw in t]


def scan_reddit(
    subreddits: list[str] | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Scan Reddit for owner-op/dispatch signal keywords via public JSON API.

    Uses Reddit's unauthenticated JSON endpoint — no credentials required.
    Returns a list of matched post dicts with signals attached.
    """
    subs = subreddits or _REDDIT_SUBS
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()

    with httpx.Client(headers=_REDDIT_HEADERS, timeout=12, follow_redirects=True) as client:
        for sub in subs:
            for query in _REDDIT_QUERIES:
                try:
                    url = (
                        f"https://www.reddit.com/r/{sub}/search.json"
                        f"?q={query}&sort=new&limit={limit}&t=week&restrict_sr=1"
                    )
                    r = client.get(url)
                    if r.status_code != 200:
                        continue
                    posts = r.json().get("data", {}).get("children", [])
                    for post in posts:
                        data = post.get("data", {})
                        post_id = data.get("id", "")
                        if post_id in seen:
                            continue
                        seen.add(post_id)
                        text = f"{data.get('title', '')} {data.get('selftext', '')}"
                        signals = match_signals(text)
                        if signals:
                            matched.append({
                                "source":       f"reddit/r/{sub}",
                                "post_id":      post_id,
                                "author":       data.get("author"),
                                "title":        data.get("title"),
                                "text_preview": text[:300],
                                "signals":      signals,
                                "permalink":    "https://reddit.com" + data.get("permalink", ""),
                                "created_utc":  data.get("created_utc"),
                            })
                    time.sleep(0.5)  # Reddit rate limit
                except Exception:  # noqa: BLE001
                    continue

    log_agent("scout", "reddit_scan",
              payload={"subs_scanned": len(subs), "matches": len(matched)})
    return matched


def ingest_signals(limit: int = 25) -> dict[str, Any]:
    """Scan Reddit and upsert matched posts as leads in stage='new' / source='social'."""
    from .scoring import score_lead
    from .dedupe import is_duplicate

    posts = scan_reddit(limit=limit)
    sb = get_supabase()
    inserted = skipped = 0

    for post in posts:
        try:
            # Use post_id as source_ref for deduplication
            existing = (
                sb.table("leads")
                  .select("id")
                  .eq("source_ref", post["post_id"])
                  .maybe_single()
                  .execute().data
            )
            if existing:
                skipped += 1
                continue

            lead: dict[str, Any] = {
                "source":         "social",
                "source_ref":     post["post_id"],
                "company_name":   post.get("author") or "Reddit User",
                "contact_name":   post.get("author"),
                "stage":          "new",
                "social_signals": post.get("signals", []),
                "home_state":     "",
            }
            lead["score"] = score_lead(lead)
            sb.table("leads").insert(lead).execute()
            inserted += 1
        except Exception:  # noqa: BLE001
            skipped += 1

    return {"scanned": len(posts), "inserted": inserted, "skipped": skipped}
