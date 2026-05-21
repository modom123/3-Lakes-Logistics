"""Social — post to Facebook, Instagram, LinkedIn using Claude-generated content."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

_THEMES = ["open_loads", "founder_program", "industry_tips", "open_loads", "founder_program", "industry_tips", "open_loads"]

_SYSTEM_PROMPT = """\
You write short social media posts for 3 Lakes Logistics, a trucking dispatch company
that helps owner-operators and small fleets run more profitably.
Tone: confident, blue-collar, friendly. No corporate jargon.
Keep posts under 280 characters for Facebook/Instagram and under 700 for LinkedIn.
Do not use hashtags unless asked. Do not use emojis unless they add real value."""

_USER_PROMPT_TPL = """\
Write one social media post themed around "{theme}" for {platform}.
Theme meanings:
  open_loads: We have open loads moving — drivers should partner with us
  founder_program: $300/mo lifetime lock, keep 100% of load earnings
  industry_tips: A practical trucking tip that builds trust

Return only the post text, nothing else."""


def _generate_post(theme: str, platform: str) -> str:
    s = get_settings()
    if not s.anthropic_api_key:
        return f"3 Lakes Logistics — moving loads and building careers. #{theme}"

    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "system": _SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": _USER_PROMPT_TPL.format(theme=theme, platform=platform)}
                ],
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as exc:  # noqa: BLE001
        log_agent("social", "generate_post_failed", error=str(exc))
        return f"3 Lakes Logistics — {theme.replace('_', ' ')}. Call us today."


def _post_facebook(text: str) -> dict[str, Any]:
    s = get_settings()
    if not s.facebook_page_id or not s.facebook_access_token:
        log_agent("social", "facebook_skip", result="credentials not configured")
        return {"status": "skipped", "reason": "credentials not configured"}
    try:
        r = httpx.post(
            f"https://graph.facebook.com/v19.0/{s.facebook_page_id}/feed",
            params={"access_token": s.facebook_access_token},
            json={"message": text},
            timeout=15,
        )
        r.raise_for_status()
        return {"status": "ok", "post_id": r.json().get("id")}
    except Exception as exc:  # noqa: BLE001
        log_agent("social", "facebook_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


def _post_instagram(text: str) -> dict[str, Any]:
    s = get_settings()
    if not s.instagram_account_id or not s.facebook_access_token:
        log_agent("social", "instagram_skip", result="credentials not configured")
        return {"status": "skipped", "reason": "credentials not configured"}
    try:
        # Step 1: create media container
        r1 = httpx.post(
            f"https://graph.facebook.com/v19.0/{s.instagram_account_id}/media",
            params={"access_token": s.facebook_access_token},
            json={"caption": text, "media_type": "REELS"},
            timeout=15,
        )
        # Instagram text-only requires an image; fall back to caption-only container
        if r1.status_code >= 400:
            r1 = httpx.post(
                f"https://graph.facebook.com/v19.0/{s.instagram_account_id}/media",
                params={"access_token": s.facebook_access_token},
                json={"caption": text},
                timeout=15,
            )
        r1.raise_for_status()
        creation_id = r1.json().get("id")

        # Step 2: publish
        r2 = httpx.post(
            f"https://graph.facebook.com/v19.0/{s.instagram_account_id}/media_publish",
            params={"access_token": s.facebook_access_token},
            json={"creation_id": creation_id},
            timeout=15,
        )
        r2.raise_for_status()
        return {"status": "ok", "post_id": r2.json().get("id")}
    except Exception as exc:  # noqa: BLE001
        log_agent("social", "instagram_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


def _post_linkedin(text: str) -> dict[str, Any]:
    s = get_settings()
    if not s.linkedin_access_token or not s.linkedin_organization_id:
        log_agent("social", "linkedin_skip", result="credentials not configured")
        return {"status": "skipped", "reason": "credentials not configured"}
    try:
        body = {
            "author": f"urn:li:organization:{s.linkedin_organization_id}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        r = httpx.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={
                "Authorization": f"Bearer {s.linkedin_access_token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=15,
        )
        r.raise_for_status()
        return {"status": "ok", "post_id": r.headers.get("x-restli-id")}
    except Exception as exc:  # noqa: BLE001
        log_agent("social", "linkedin_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


def post_all() -> dict[str, Any]:
    day_of_week = datetime.now(timezone.utc).weekday()  # 0=Mon
    theme = _THEMES[day_of_week]

    fb_text = _generate_post(theme, "Facebook")
    ig_text = _generate_post(theme, "Instagram")
    li_text = _generate_post(theme, "LinkedIn")

    fb_result = _post_facebook(fb_text)
    ig_result = _post_instagram(ig_text)
    li_result = _post_linkedin(li_text)

    log_agent(
        "social", "post_all",
        result=f"fb={fb_result['status']} ig={ig_result['status']} li={li_result['status']}",
    )
    return {
        "agent": "social",
        "theme": theme,
        "facebook": fb_result,
        "instagram": ig_result,
        "linkedin": li_result,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    return post_all()
