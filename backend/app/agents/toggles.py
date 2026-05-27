"""Agent on/off toggle store.

Reads and writes the `agent_toggles` table in Supabase.
Missing rows are treated as enabled so the system works even before
the migration is applied.
"""
from __future__ import annotations

from datetime import datetime, timezone


def is_enabled(agent_name: str) -> bool:
    """Return True if the agent is enabled (default: True if no row exists)."""
    try:
        from ..supabase_client import get_supabase
        result = (
            get_supabase()
            .table("agent_toggles")
            .select("enabled")
            .eq("agent_name", agent_name)
            .maybe_single()
            .execute()
        )
        if result.data:
            return bool(result.data["enabled"])
    except Exception:  # noqa: BLE001
        pass
    return True


def set_enabled(agent_name: str, enabled: bool, updated_by: str = "api") -> None:
    """Enable or disable an agent by upserting into agent_toggles."""
    from ..supabase_client import get_supabase
    get_supabase().table("agent_toggles").upsert(
        {
            "agent_name": agent_name,
            "enabled": enabled,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        },
        on_conflict="agent_name",
    ).execute()


def get_all_toggles(agent_names: list[str]) -> dict[str, bool]:
    """Return {agent_name: enabled} for every name in agent_names.

    Agents with no row in agent_toggles default to True.
    """
    try:
        from ..supabase_client import get_supabase
        result = (
            get_supabase()
            .table("agent_toggles")
            .select("agent_name,enabled")
            .execute()
        )
        stored = {row["agent_name"]: bool(row["enabled"]) for row in (result.data or [])}
    except Exception:  # noqa: BLE001
        stored = {}
    return {name: stored.get(name, True) for name in agent_names}
