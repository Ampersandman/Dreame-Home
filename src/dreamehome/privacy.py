"""Remove common credentials and personal identifiers from shareable captures."""

import hashlib
import json
import secrets

SENSITIVE = {
    "password", "accesstoken", "refreshtoken", "authorization", "dreameauth", "token",
    "ssecurity", "iotid", "iotkey", "streamkey", "signingkey", "aeskey", "secret",
    "username", "email", "phone", "mobilenumber", "uid", "masteruid", "masteruid2uuid",
    "did", "id", "mac", "sn", "serial", "serialnumber", "localip", "ip", "ssid",
    "bssid", "mastername", "customname", "name", "latitude", "longitude", "address",
}


def redactor():
    salt = secrets.token_bytes(16)

    def redact(value, key=""):
        normalized = key.lower().replace("_", "").replace("-", "")
        if normalized in SENSITIVE and value not in (None, ""):
            encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
            return "<redacted:" + hashlib.sha256(salt + encoded).hexdigest()[:10] + ">"
        if isinstance(value, dict):
            semantic_key = value.get("k", value.get("key"))
            sensitive_setting = isinstance(semantic_key, str) and semantic_key.lower().replace("_", "").replace("-", "") in SENSITIVE
            return {k: redact(v, semantic_key if sensitive_setting and k in ("v", "value") else str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        if isinstance(value, str):
            if value.startswith(("https://", "http://")):
                return "<redacted-url>"
            if value.lstrip().startswith(("{", "[")):
                try:
                    return json.dumps(redact(json.loads(value)), ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    pass
        return value

    return redact
