"""Dreame's nonstandard request canonicalization, reproduced from upstream."""

import base64
import hashlib
import json
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad


def splice(obj: dict[str, Any], top: bool = True) -> str:
    parts = []
    for key in sorted(obj):
        value = obj[key]
        if isinstance(value, dict):
            inner = splice(value, False)
            parts.append(f"{key}=[{inner}]" if inner else f"{key}=]")
        elif isinstance(value, list):
            if top:
                parts.append(f"{key}={json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)}")
        elif isinstance(value, bool):
            parts.append(f"{key}={'true' if value else 'false'}")
        elif value is None:
            parts.append(f"{key}=null")
        elif top:
            parts.append(f"{key}={value}")
        else:
            parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
    return "&".join(parts)


def sign(params: dict[str, Any], key: str, timestamp_ms: int) -> dict[str, Any]:
    base = splice(params) + str(timestamp_ms) + key
    return {**params, "sign": hashlib.md5(base.encode("utf-8")).hexdigest(), "timestamp": timestamp_ms}


def region_header(region: str, language: str, country: str, key: str) -> str:
    data = pad(f"{region}|{language}|{country}".encode("utf-8"), 16)
    return base64.b64encode(AES.new(key.encode("utf-8"), AES.MODE_ECB).encrypt(data)).decode("ascii")
