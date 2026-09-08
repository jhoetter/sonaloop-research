from __future__ import annotations

import base64
import copy
import hashlib
from io import BytesIO
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from . import config
from .config import load_env, utc_now_iso
from .services import stable_id
from .storage import Store
from ._persona_native import persona_profile_version, persona_version
from .persona_surface_contract import MAX_AVATAR_BYTES, MAX_AVATAR_DIMENSION


# The single, helpful degradation message (cold start without an OPENAI_API_KEY is normal):
# avatars are optional eye-candy, never a blocker — everything else works without the key.
AVATAR_DISABLED_NOTE = (
    "avatars disabled — no OPENAI_API_KEY configured (optional; used only for avatar images "
    "and embedding-based recall). Set it in the environment or in <data dir>/.env "
    "(`sonaloop info` shows the data dir), then retry. Everything else works without it."
)


def avatars_enabled() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _post_json(url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = resp.read(MAX_AVATAR_BYTES * 2 + 1)
        if len(payload) > MAX_AVATAR_BYTES * 2:
            raise ValueError("image provider response exceeds the delivery limit")
        result = json.loads(payload)
        request_id = resp.headers.get("x-request-id", "")
        if re.fullmatch(r"[A-Za-z0-9_-]{1,200}", request_id):
            result["_request_id"] = request_id
        return result


def validate_avatar_png(data: bytes) -> tuple[int, int]:
    """Decode the complete native image before publishing or embedding it."""
    from PIL import Image
    if not isinstance(data, bytes) or len(data) > MAX_AVATAR_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("avatar must be a PNG within the delivery limit")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or not all(0 < n <= MAX_AVATAR_DIMENSION for n in image.size):
                raise ValueError("avatar dimensions exceed the delivery limit")
            size = image.size
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
        return size
    except Exception as exc:
        raise ValueError("avatar PNG is invalid or exceeds its dimensions limit") from exc


def build_avatar_prompt(persona: dict[str, Any], style: str | None = None) -> str:
    role = persona["role"]["title"]
    company = persona["company_context"]["industry"]
    working_style = persona["personality"]["working_style"]
    traits = persona.get("identity_traits", {})
    gender = traits.get("gender_presentation", "unspecified")
    age_range = traits.get("age_range", "unspecified")
    _constraints = traits.get("avatar_constraints", [])
    constraints = "; ".join(_constraints) if isinstance(_constraints, list) else str(_constraints)
    avatar_profile = traits.get("avatar_profile", {})
    if isinstance(avatar_profile, dict):
        visual_profile = (
            f"Distinct visual profile: {avatar_profile.get('hair', 'distinct professional hairstyle')}; "
            f"{avatar_profile.get('glasses', 'individual eyewear choice')}; "
            f"{avatar_profile.get('expression', 'individual professional expression')}; "
            f"{avatar_profile.get('clothing', 'distinct professional clothing')}; "
            f"{avatar_profile.get('role_cue', 'role-appropriate office background')}."
        )
    else:
        # avatar_profile authored as free text (or empty) — use it directly.
        profile_text = str(avatar_profile).strip() or "distinct professional appearance for this role"
        notes = traits.get("appearance_notes")
        visual_profile = f"Distinct visual profile: {profile_text}." + (f" {notes}." if notes else "")
    identity_clause = f" named {persona['display_name']}"
    if gender != "unspecified":
        identity_clause += f", with {gender} gender presentation"
    if age_range != "unspecified":
        identity_clause += f", age range {age_range}"
    return (
        f"Create a professional editorial avatar portrait of a fictional person{identity_clause}, "
        f"working in the role of {role} in {company}. "
        f"The person should feel {working_style}. Neutral studio background, natural expression, "
        f"clean modern business look, no text, no logos, no photorealistic claim of a real person. "
        f"{visual_profile} "
        f"Hard constraints: {constraints or 'do not contradict the display name, role, or provided identity traits'}. "
        f"Style: {style or 'polished semi-realistic professional avatar'}. "
        f"Same overall illustration language as the other personas, but a clearly different face, hair, clothing, and silhouette."
    )


def get_persona_avatar_content(
        persona_id: str, store: Store | None = None) -> tuple[bytes, dict[str, Any]]:
    """Return one persona's PNG portrait from the ACTIVE runtime partition.

    The persona record is resolved through the current Store/RLS scope first. Its
    portable ``data/avatars/<file>.png`` reference is then contained inside the active
    workspace's filesystem partition, so a stable catalog persona id never becomes a
    cross-workspace file capability.
    """
    store = store or Store()
    lookup = getattr(store, "get_persona_for_active_workspace", store.get_persona)
    persona = lookup(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    stored_path = str((persona.get("avatar") or {}).get("path") or "").strip()
    if not stored_path:
        raise FileNotFoundError(f"Persona has no avatar: {persona_id}")

    raw = Path(stored_path)
    tenant_mode = config.postgres_row_tenancy_enabled()
    if tenant_mode:
        # Shared deployments accept only the virtual path written by generation and
        # snapshot import. Absolute paths and nested/traversal spellings fail closed.
        parts = raw.parts
        if (len(parts) != 3 or parts[:2] != ("data", "avatars")
                or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,191}\.png",
                    parts[2],
                    re.IGNORECASE,
                )):
            raise ValueError(f"unsafe tenant avatar path: {stored_path!r}")

    rel = stored_path.removeprefix("data/")
    partition = config.partition_dir().resolve()
    candidate = (partition / rel).resolve()
    allowed_root = (partition / "avatars").resolve() if tenant_mode else partition
    if not candidate.is_relative_to(allowed_root) or candidate.suffix.lower() != ".png":
        raise ValueError(f"avatar path escapes the active partition: {stored_path!r}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    if candidate.stat().st_size > 8 * 1024 * 1024:
        raise ValueError(f"avatar exceeds the 8 MiB delivery limit: {stored_path!r}")
    data = candidate.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"avatar is not a PNG: {stored_path!r}")
    return data, persona


def generate_persona_avatar(persona_id: str, style: str | None = None, store: Store | None = None,
                            *, prompt: str | None = None, expected_version: str | None = None,
                            before_provider=None, before_persist=None) -> dict[str, Any]:
    load_env()
    store = store or Store()
    lookup = getattr(store, "get_persona_for_active_workspace", store.get_persona)
    persona = lookup(persona_id)
    if not persona:
        raise KeyError(f"Unknown persona: {persona_id}")
    if expected_version and persona_version(persona) != expected_version:
        from .storage._personas import PersonaWriteConflict
        raise PersonaWriteConflict("persona changed since it was read; refresh before writing")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(AVATAR_DISABLED_NOTE)
    model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
    # Default to the active workspace runtime.  Local mode's partition is DATA_DIR,
    # preserving the historical data/avatars location exactly.
    partition = config.partition_dir()
    env_dir = os.getenv("AVATAR_OUTPUT_DIR")
    if env_dir:
        configured = Path(env_dir)
        if config.postgres_row_tenancy_enabled():
            # A process-wide override must not collapse every workspace back into
            # one directory.  Treat relative values as partition-relative (and
            # accept the common virtual "data/..." spelling); absolute values must
            # already name a location inside this active partition.
            if not configured.is_absolute():
                parts = configured.parts
                if parts and parts[0] == "data":
                    configured = Path(*parts[1:])
                configured = partition / configured
            out_dir = configured.resolve()
            if not out_dir.is_relative_to(partition.resolve()):
                raise ValueError("AVATAR_OUTPUT_DIR must stay inside the active workspace partition")
        else:
            out_dir = configured
            if not out_dir.is_absolute():
                out_dir = config.ROOT / out_dir
    else:
        out_dir = partition / "avatars"
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_persona = copy.deepcopy(persona)
    if prompt is not None:
        prompt_persona.setdefault("identity_traits", {})["avatar_profile"] = prompt
    prompt = build_avatar_prompt(prompt_persona, style)
    if before_provider:
        before_provider()
    result = _post_json(
        "https://api.openai.com/v1/images/generations",
        {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024", "quality": "medium"},
        api_key,
    )
    data = result["data"][0]
    if data.get("b64_json"):
        img_bytes = base64.b64decode(data["b64_json"], validate=True)
    elif data.get("url"):
        # GPT Image returns inline bytes. A provider-returned URL must never
        # become a capability to read files, private hosts, or redirects.
        raise ValueError("image provider must return inline PNG bytes")
    else:
        raise RuntimeError("No image payload returned by OpenAI image generation.")
    slug = str(persona.get("slug") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", slug):
        raise ValueError(f"unsafe persona slug for avatar filename: {slug!r}")
    validate_avatar_png(img_bytes)
    image_sha = hashlib.sha256(img_bytes).hexdigest()
    filename = f"{slug}-{image_sha[:24]}.png"
    out_path = out_dir / filename
    try:
        with out_path.open("xb") as stream:
            stream.write(img_bytes)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if out_path.read_bytes() != img_bytes:
            raise ValueError("avatar content-address collision")
    # Persist a partition-VIRTUAL ref.  Each tenant's DB can keep the same
    # ``data/avatars/<file>`` value while readers resolve it inside that tenant.
    if out_path.resolve().is_relative_to(partition.resolve()):
        rel = "data/" + str(out_path.resolve().relative_to(partition.resolve()))
    elif out_path.is_relative_to(config.ROOT):
        rel = str(out_path.relative_to(config.ROOT))
    else:
        rel = str(out_path)
    avatar = {
        "path": rel,
        "prompt": prompt,
        "model": model,
        "validated_against": ["display_name", "role", "identity_traits"],
        "known_risks": [],
        "generated_at": utc_now_iso(),
        "sha256": image_sha,
        "profile_version": persona_profile_version(persona),
    }
    if re.fullmatch(r"[A-Za-z0-9_-]{1,200}", str(result.get("_request_id") or "")):
        avatar["request_id"] = result["_request_id"]
    usage = result.get("usage")
    if isinstance(usage, dict):
        avatar["usage"] = {k: v for k, v in usage.items()
                           if k in {"input_tokens", "output_tokens", "total_tokens"}
                           and type(v) is int and 0 <= v <= 10000000}
    persona["avatar"] = avatar
    persona["updated_at"] = utc_now_iso()
    if before_persist:
        before_persist()
    store.upsert_persona(persona, reason="generate_persona_avatar")
    return avatar
