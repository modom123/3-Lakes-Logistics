"""Social — post to Facebook, Instagram, LinkedIn, TikTok, YouTube using Claude-generated content."""
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
Keep posts under 280 characters for Facebook/Instagram/TikTok, under 150 for TikTok hooks,
and under 700 for LinkedIn/YouTube. No hashtags unless asked. No emojis unless they add real value."""

_USER_PROMPT_TPL = """\
Write one social media post themed around "{theme}" for {platform}.
Theme meanings:
  open_loads: We have open loads moving — drivers should partner with us
  founder_program: $300/mo lifetime lock, keep 100% of load earnings
  industry_tips: A practical trucking tip that builds trust

Platform style notes:
  TikTok: Start with a hook (first 5 words grab attention), max 150 chars, punchy
  YouTube: Community post style — conversational, slightly longer, ends with a question
  Facebook: Clear value statement, friendly
  Instagram: Visual language, short and punchy
  LinkedIn: Professional tone, specific numbers/facts preferred

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


def _post_tiktok(text: str) -> dict[str, Any]:
    s = get_settings()
    if not s.tiktok_access_token or not s.tiktok_open_id:
        log_agent("social", "tiktok_skip", result="credentials not configured")
        return {"status": "skipped", "reason": "credentials not configured"}
    if not s.tiktok_image_url:
        log_agent("social", "tiktok_skip", result="TIKTOK_IMAGE_URL not set")
        return {"status": "skipped", "reason": "TIKTOK_IMAGE_URL not configured — set a public branded image URL"}
    try:
        r = httpx.post(
            "https://open.tiktokapis.com/v2/post/publish/content/init/",
            headers={
                "Authorization": f"Bearer {s.tiktok_access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "post_info": {
                    "title": text[:2200],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                    "auto_add_music": True,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "photo_images": [s.tiktok_image_url],
                    "photo_cover_index": 0,
                },
                "post_mode": "DIRECT_POST",
                "media_type": "PHOTO",
            },
            timeout=20,
        )
        r.raise_for_status()
        return {"status": "ok", "publish_id": r.json().get("data", {}).get("publish_id")}
    except Exception as exc:  # noqa: BLE001
        log_agent("social", "tiktok_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


def _post_youtube(text: str) -> dict[str, Any]:
    """Post a YouTube Community post (text) to the channel's community tab."""
    s = get_settings()
    if not s.youtube_access_token:
        log_agent("social", "youtube_skip", result="credentials not configured")
        return {"status": "skipped", "reason": "credentials not configured"}
    try:
        r = httpx.post(
            "https://www.googleapis.com/youtube/v3/posts",
            params={"part": "snippet"},
            headers={
                "Authorization": f"Bearer {s.youtube_access_token}",
                "Content-Type": "application/json",
            },
            json={"snippet": {"type": "textPost", "textOriginalContent": text}},
            timeout=20,
        )
        r.raise_for_status()
        return {"status": "ok", "post_id": r.json().get("id")}
    except Exception as exc:  # noqa: BLE001
        log_agent("social", "youtube_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


def post_all() -> dict[str, Any]:
    day_of_week = datetime.now(timezone.utc).weekday()  # 0=Mon
    theme = _THEMES[day_of_week]

    fb_text = _generate_post(theme, "Facebook")
    ig_text = _generate_post(theme, "Instagram")
    li_text = _generate_post(theme, "LinkedIn")
    tt_text = _generate_post(theme, "TikTok")
    yt_text = _generate_post(theme, "YouTube")

    fb_result = _post_facebook(fb_text)
    ig_result = _post_instagram(ig_text)
    li_result = _post_linkedin(li_text)
    tt_result = _post_tiktok(tt_text)
    yt_result = _post_youtube(yt_text)

    log_agent(
        "social", "post_all",
        result=(
            f"fb={fb_result['status']} ig={ig_result['status']} "
            f"li={li_result['status']} tt={tt_result['status']} yt={yt_result['status']}"
        ),
    )
    return {
        "agent": "social",
        "theme": theme,
        "facebook":  fb_result,
        "instagram": ig_result,
        "linkedin":  li_result,
        "tiktok":    tt_result,
        "youtube":   yt_result,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    return post_all()
