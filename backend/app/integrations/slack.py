"""Slack incoming webhooks (step 89)."""
from __future__ import annotations

import httpx

from ..logging_service import get_logger
from ..settings import get_settings

_log = get_logger("3ll.slack")


def post_ops(text: str, blocks: list[dict] | None = None) -> bool:
    return _post(get_settings().slack_webhook_ops, text, blocks)


def post_alert(text: str, blocks: list[dict] | None = None) -> bool:
    return _post(get_settings().slack_webhook_alerts, text, blocks)


def _post(url: str, text: str, blocks: list[dict] | None) -> bool:
    if not url:
        _log.info("SLACK[dev] %s", text)
        return False
    try:
        payload = {"text": text}
        if blocks:
            payload["blocks"] = blocks
        r = httpx.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("slack post failed: %s", exc)
        return False
