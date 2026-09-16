"""Validated, version-aware persona profile updates."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
from datetime import date
from typing import Any

from ..config import utc_now_iso
from ..llm_simulation import (
    validate_activity_payload,
    validate_day_plan_payload,
    validate_memory_deltas_payload,
    validate_plan_payload,
    validate_profile_payload,
)
from ..storage import Store
from ._common import *  # noqa: F401,F403

_EDITABLE_PERSONA_FIELDS = frozenset({
    "display_name", "source_description", "identity_traits", "segment", "demographics",
    "role", "company_context", "goals", "constraints", "tool_ids", "tools",
    "relationships", "personality", "pain_points", "success_criteria", "capabilities",
})
_IDENTITY_PERSONA_FIELDS = frozenset({
    "display_name", "source_description", "identity_traits", "segment", "demographics",
    "role", "company_context",
})
_ENRICHMENT_PERSONA_FIELDS = frozenset({
    "goals", "constraints", "tool_ids", "tools", "relationships", "personality",
    "pain_points", "success_criteria", "capabilities",
})
_MAX_ENRICHMENT_DAYS = 8


def _update_preview_token(persona: dict[str, Any], patch: dict[str, Any]) -> str:
    frozen = json.dumps({
        "persona_id": persona["id"],
        "updated_at": persona.get("updated_at"),
        "patch": patch,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "update-persona:" + hashlib.sha256(frozen.encode("utf-8")).hexdigest()[:24]


def _persona_update_impact(persona_id: str, store: Store) -> dict[str, int]:
    projects = [row for row in store.list_research_projects()
                if persona_id in (row.get("persona_ids") or [])]
    councils = [row for row in store.list_council_sessions()
                if persona_id in (row.get("persona_ids") or [])]
    return {
        "linked_projects": len(projects),
        "active_runs": sum(
            row.get("status") == "active"
            for project in projects for row in store.list_runs(project["id"])
        ),
        "historical_councils": len(councils),
        "historical_sessions": (
            len(store.list_usability_sessions(persona_id=persona_id))
            + len(store.list_prototype_sessions(persona_id=persona_id))
        ),
        "frozen_context_snapshots": len(store.list_persona_context_snapshots(persona_id)),
    }


def _validated_persona_patch(persona: dict[str, Any],
                             patch: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(patch, dict) or not patch:
        raise ValueError("persona patch must be a non-empty object")
    forbidden = sorted(set(patch) - _EDITABLE_PERSONA_FIELDS)
    if forbidden:
        raise ValueError(
            f"persona patch contains immutable/unknown fields {forbidden}; editable fields are "
            f"{sorted(_EDITABLE_PERSONA_FIELDS)}. Use record_persona_revision for slow identity drift.")
    clean = dict(patch)
    if "capabilities" in clean:
        clean["capabilities"] = merge_capabilities(  # noqa: F821 (bound)
            persona.get("capabilities"), clean["capabilities"])
    candidate = copy.deepcopy(persona)
    for key, value in clean.items():
        if isinstance(value, dict) and isinstance(candidate.get(key), dict):
            candidate[key].update(value)
        else:
            candidate[key] = value
    validate_profile_payload({key: candidate.get(key) for key in (
        "display_name", "identity_traits", "segment", "demographics", "role",
        "company_context", "goals", "constraints", "tool_ids", "tools",
        "relationships", "personality", "pain_points", "success_criteria",
    )})
    return clean, candidate


def preview_persona_update(persona_id: str, patch: dict[str, Any],
                           expected_updated_at: str | None = None,
                           store: Store | None = None) -> dict[str, Any]:
    """Validate a patch and show a bounded field-level diff without mutating."""
    store = store or Store()
    persona = store.get_persona_for_active_workspace(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if expected_updated_at and expected_updated_at != persona.get("updated_at"):
        raise ValueError("persona changed since it was read; refresh and preview against the current version")
    clean, candidate = _validated_persona_patch(persona, patch)
    changed = {key: {"before": persona.get(key), "after": candidate.get(key)}
               for key in clean if persona.get(key) != candidate.get(key)}
    changed_fields = sorted(changed)
    identity_fields = sorted(set(changed_fields) & _IDENTITY_PERSONA_FIELDS)
    confirmation_required = bool(identity_fields)
    return {"persona_id": persona["id"], "expected_updated_at": persona.get("updated_at"),
            "changed_fields": changed_fields, "changes": changed,
            "risk": {
                "level": "identity" if confirmation_required else "routine",
                "identity_fields": identity_fields,
                "confirmation_required": confirmation_required,
            },
            "impact": _persona_update_impact(persona["id"], store),
            "confirmation_token": (_update_preview_token(persona, clean)
                                   if confirmation_required else ""),
            "history_contract": {
                "past_sessions_unchanged": True,
                "frozen_context_snapshots_unchanged": True,
                "future_context_uses_updated_profile": True,
            },
            "no_op": not changed, "next_recommended_tool": "update_persona"}


def update_persona(persona_id: str, patch: dict[str, Any], reason: str,
                   expected_updated_at: str | None = None,
                   preview_token: str | None = None,
                   store: Store | None = None) -> dict[str, Any]:
    store = store or Store()
    persona = store.get_persona_for_active_workspace(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if not str(reason or "").strip():
        raise ValueError("persona update requires a non-empty reason")
    if expected_updated_at and expected_updated_at != persona.get("updated_at"):
        raise ValueError("persona changed since it was read; refresh and preview against the current version")
    patch, candidate = _validated_persona_patch(persona, patch)
    changed_fields = {key for key in patch if persona.get(key) != candidate.get(key)}
    identity_fields = changed_fields & _IDENTITY_PERSONA_FIELDS
    if identity_fields:
        expected_token = _update_preview_token(persona, patch)
        if not preview_token or not hmac.compare_digest(preview_token, expected_token):
            raise ValueError(
                "identity-changing persona updates require the exact confirmation_token from "
                "preview_persona_update for the current persona version and patch"
            )
    persona = candidate
    persona["updated_at"] = utc_now_iso()
    persona["soul"] = write_soul(persona, store)  # noqa: F821 (bound)
    store.upsert_persona(persona, reason=reason)
    emit_lifecycle_event(  # noqa: F821 (bound)
        "persona.updated", {"persona_id": persona["id"], "reason": reason}, store)
    from ..telemetry import capture_product_event
    capture_product_event(
        "persona_updated", subject_kind="persona", subject_id=persona["id"],
        properties={"changed_fields": sorted(str(key) for key in patch)[:20]})
    return persona


def begin_persona_enrichment(persona_id: str, request: str,
                             source_chat_id: str | None = None,
                             store: Store | None = None) -> dict[str, Any]:
    """Gather one bounded profile-and-lived-experience enrichment brief.

    This is the front door for requests such as "add her cooking hobby and the
    private August experiences from this chat". A chat is source material only;
    nothing becomes profile or lived memory until ``record_persona_enrichment``.
    """
    store = store or Store()
    persona = store.get_persona_for_active_workspace(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if not str(request or "").strip():
        raise ValueError("persona enrichment requires a non-empty request")
    chat_context = None
    if source_chat_id:
        chat = store.get_persona_chat(source_chat_id)
        if not chat or chat.get("persona_id") != persona["id"]:
            raise KeyError(f"Unknown chat for persona: {source_chat_id}")
        turns = []
        for turn in (chat.get("turns") or [])[-4:]:
            turns.append({
                "idx": turn.get("idx"),
                "user_message": str(turn.get("user_message") or "")[:2000],
                "persona_reply": str(turn.get("persona_reply") or "")[:4000],
                "created_at": turn.get("created_at"),
            })
        chat_context = {"id": chat["id"], "turns": turns}
    events = store.list_experience_events(persona["id"])
    existing_dates = sorted({str(row.get("timestamp") or "")[:10] for row in events
                             if str(row.get("timestamp") or "")[:10]})
    frame = {
        "persona_id": persona["id"],
        "persona_name": persona["display_name"],
        "request": str(request).strip(),
        "expected_updated_at": persona.get("updated_at"),
        "current_profile": {
            key: copy.deepcopy(persona.get(key))
            for key in sorted(_ENRICHMENT_PERSONA_FIELDS)
        },
        "existing_experience_dates": existing_dates[-120:],
        "source_chat": chat_context,
        "anti_steering": _ANTI_STEERING,  # noqa: F405 (bound)
    }
    instructions = (
        "Author one enrichment object {reason, profile_patch, days}. Keep profile_patch MINIMAL: "
        "only fields explicitly supported by the request, chosen from goals, constraints, tool_ids, "
        "tools, relationships, personality, pain_points, success_criteria, capabilities. Never replay "
        "the whole profile and never rewrite identity/role/demographics here. A chat reply is source "
        "material, not yet official memory. Put concrete dated experiences into days using the normal "
        "record_day shape: {date, workday_start_hour?, seed?, day_plan{mood_forecast,blocks[5-8]}, "
        "plan{summary,intentions,expected_milestones,mood_trajectory,sample_days}, "
        "activities{<exact block title>:{what_happened,conversation,key_quotes,actions_done,"
        "artifacts_touched,persona_thought,decision,open_loops,mood,energy_delta,pain_points}}, "
        "deltas?}. Use an unused date unless the caller explicitly intends a replacement. Preserve "
        "ordinary life, uncertainty and unresolved threads. " + _ANTI_STEERING  # noqa: F405 (bound)
    )
    return {
        "persona_id": persona["id"],
        "schema": "sonaloop.persona_enrichment.v1",
        "instructions": instructions,
        "frame": frame,
        "next_action": {
            "tool": "record_persona_enrichment",
            "arguments": {
                "persona_id": persona["id"],
                "expected_updated_at": persona.get("updated_at"),
            },
            "author_argument": "enrichment",
        },
    }


def _validate_enrichment_day(persona: dict[str, Any], day: dict[str, Any]) -> str:
    if not isinstance(day, dict):
        raise TypeError("each persona enrichment day must be an object")
    try:
        day_value = date.fromisoformat(str(day.get("date") or "")).isoformat()
    except ValueError as exc:
        raise ValueError("each persona enrichment day requires an ISO date") from exc
    day_plan = validate_day_plan_payload(day.get("day_plan") or {}, {
        "allowed_tools": persona["tools"],
    })
    validate_plan_payload(day.get("plan") or {}, "day")
    activities = day.get("activities")
    if not isinstance(activities, dict):
        raise TypeError("each persona enrichment day requires an activities object")
    titles = [block["title"] for block in day_plan["blocks"]]
    if set(activities) != set(titles):
        raise ValueError("persona enrichment activities must match the exact day-plan block titles")
    for block in day_plan["blocks"]:
        validate_activity_payload(activities[block["title"]], {
            "allowed_tools": persona["tools"],
            "allowed_pain_points": persona["pain_points"],
            "tool": block["tool"],
        })
    if day.get("deltas") is not None:
        validate_memory_deltas_payload(day["deltas"])
    if day.get("workday_start_hour") is not None:
        try:
            hour = int(day["workday_start_hour"])
        except (TypeError, ValueError) as exc:
            raise ValueError("workday_start_hour must be an integer from 0 to 23") from exc
        if not 0 <= hour <= 23:
            raise ValueError("workday_start_hour must be an integer from 0 to 23")
    return day_value


def record_persona_enrichment(persona_id: str, enrichment: dict[str, Any],
                              expected_updated_at: str | None = None,
                              allow_existing_dates: bool = False,
                              store: Store | None = None) -> dict[str, Any]:
    """Persist a host-authored minimal profile patch plus dated lived days.

    Identity-shaped changes remain on the state-bound ``update_persona`` preview
    path. All inputs are validated before the first write.
    """
    store = store or Store()
    persona = store.get_persona_for_active_workspace(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if expected_updated_at and expected_updated_at != persona.get("updated_at"):
        raise ValueError("persona changed since the enrichment brief; refresh and author against the current version")
    if not isinstance(enrichment, dict):
        raise TypeError("persona enrichment must be an object")
    reason = str(enrichment.get("reason") or "").strip()
    if not reason:
        raise ValueError("persona enrichment requires a non-empty reason")
    patch = enrichment.get("profile_patch") or {}
    if not isinstance(patch, dict):
        raise TypeError("profile_patch must be an object")
    forbidden = sorted(set(patch) - _ENRICHMENT_PERSONA_FIELDS)
    if forbidden:
        raise ValueError(
            f"persona enrichment cannot change identity fields {forbidden}; use update_persona, "
            "which returns its own state-bound confirmation preview"
        )
    clean_patch: dict[str, Any] = {}
    candidate = persona
    if patch:
        clean_patch, candidate = _validated_persona_patch(persona, patch)
    days = enrichment.get("days") or []
    if not isinstance(days, list):
        raise TypeError("persona enrichment days must be a list")
    if len(days) > _MAX_ENRICHMENT_DAYS:
        raise ValueError(f"persona enrichment accepts at most {_MAX_ENRICHMENT_DAYS} days per call")
    if not clean_patch and not days:
        raise ValueError("persona enrichment must contain a profile_patch or at least one day")
    normalized_dates = [_validate_enrichment_day(candidate, day) for day in days]
    if len(normalized_dates) != len(set(normalized_dates)):
        raise ValueError("persona enrichment cannot contain the same date twice")
    if not allow_existing_dates:
        occupied = []
        for day_value in normalized_dates:
            if store.list_experience_events(
                    persona["id"], f"{day_value}T00:00", f"{day_value}T23:59"):
                occupied.append(day_value)
        if occupied:
            raise ValueError(
                "persona enrichment dates already contain lived events: " + ", ".join(occupied)
                + "; choose unused dates or explicitly set allow_existing_dates=true"
            )

    preview = (preview_persona_update(persona["id"], clean_patch,
                                      persona.get("updated_at"), store=store)
               if clean_patch else None)
    profile_updated = bool(preview and not preview["no_op"])
    if profile_updated:
        persona = update_persona(
            persona["id"], clean_patch, reason, persona.get("updated_at"), store=store)

    from ._simulation import record_day
    recorded_days = []
    for item, day_value in zip(days, normalized_dates):
        recorded_days.append(record_day(
            persona["id"], day_value, item["day_plan"], item["plan"], item["activities"],
            item.get("deltas"), item.get("workday_start_hour"), item.get("seed"), store=store,
        ))
    return {
        "persona_id": persona["id"],
        "applied": True,
        "profile_updated": profile_updated,
        "changed_fields": [] if not preview else preview["changed_fields"],
        "days": recorded_days,
        "synthetic_notice": "Profile additions and lived days are synthetic unless backed by attached evidence.",
        "history_contract": {
            "past_sessions_unchanged": True,
            "frozen_context_snapshots_unchanged": True,
            "future_context_uses_enrichment": True,
        },
    }
