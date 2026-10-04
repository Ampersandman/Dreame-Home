from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Device:
    did: str
    model: str
    name: str
    owner_uid: str | None = field(default=None, repr=False)
    bind_domain: str | None = field(default=None, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> Device:
        info = raw.get("deviceInfo") or {}
        return cls(
            did=str(raw["did"]), model=str(raw.get("model") or "unknown"),
            name=str(raw.get("customName") or info.get("displayName") or raw.get("name") or raw.get("model") or "Dreame device"),
            owner_uid=str(raw["masterUid"]) if raw.get("masterUid") is not None else None,
            bind_domain=raw.get("bindDomain"), raw=dict(raw),
        )


@dataclass(frozen=True)
class Session:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    uid: str = field(repr=False)
    expires_at: float
    tenant_id: str = "000000"
    region: str | None = None
    language: str | None = None
    country: str | None = None
    domain: str | None = None


def decode_push(payload: bytes | str) -> dict[str, Any]:
    """Preserve unknown methods/properties as well as properties_changed."""
    import json

    raw = json.loads(payload)
    if not isinstance(raw, dict):
        raise ValueError("MQTT payload must be an object")
    data = raw.get("data")
    return data if isinstance(data, dict) else raw
