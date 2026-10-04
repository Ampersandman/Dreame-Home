"""Account-wide DreameHome API, extracted from the pinned upstream protocol.

This is a transport foundation, not a claim of washer/dryer compatibility.
All device IDs and property identifiers are preserved; no vacuum filtering.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlencode

from .catalog import load_catalog
from .exceptions import ApiError, AuthenticationError, IncompleteDiscoveryError, RateLimitError, TransportError
from .models import Device, Session
from .signing import region_header, sign
from .transport import HttpsTransport, Response, Transport, validate_https_url


class DreameHomeClient:
    def __init__(
        self, username: str = "", password: str = "", *, region: str = "eu",
        account_type: str = "dreame", refresh_token: str | None = None,
        transport: Transport | None = None, clock: Callable[[], float] = time.time,
        visitor_id: str | None = None, on_session: Callable[[Session], None] | None = None,
    ):
        config = load_catalog("api")
        if account_type not in config["profiles"]:
            raise ValueError("Account type must be dreame, mova or trouver")
        profile = config["profiles"][account_type]
        if region not in profile["regions"]:
            raise ValueError(f"Region must be one of {', '.join(profile['regions'])} (app server, not country code)")
        self.region = region
        self.account_type = account_type
        self.profile = profile
        self.base_url = f"https://{region}{self.profile['domain_suffix']}:{self.profile['port']}"
        self._endpoints = config["endpoints"]
        self._password_salt = config["password_salt"]
        self._username = username
        self._password = password
        self._refresh_token = refresh_token
        self._transport = transport or HttpsTransport()
        self._clock = clock
        self.visitor_id = visitor_id or hashlib.md5(secrets.token_bytes(16)).hexdigest()
        self._on_session = on_session
        self._session: Session | None = None
        self._auth_lock = asyncio.Lock()
        self._request_id = secrets.randbelow(100) + 1

    @property
    def session(self) -> Session | None:
        return self._session

    def _headers(self, content_type: str, authenticated: bool = False) -> dict[str, str]:
        p = self.profile
        session = self._session
        kr = self.region == "kr" and self.account_type == "dreame"
        headers = {"user-agent": p["user_agent"]}
        if not kr:
            meta = f"cv=a_{p['app_version']}"
            if p["browser_metadata"]:
                canvas = hashlib.md5((self._username + "c").encode()).hexdigest()[:8]
                webgl = hashlib.md5((self._username + "w").encode()).hexdigest()[:8]
                meta += f";canvasHash={canvas};webglHash={webgl};visitorIdHash={self.visitor_id}"
            headers["dreame-meta"] = meta
        # urllib backend does not transparently decompress; avoid advertising gzip.
        headers["accept-encoding"] = "identity"
        if session and session.region and session.language and session.country and not kr:
            headers["dreame-rlc"] = region_header(session.region, session.language, session.country, p["signing_key"])
        headers["tenant-id"] = session.tenant_id if session else p["tenant_id"]
        headers["authorization"] = p["basic_authorization"]
        if self.account_type == "mova":
            headers["dreame-psd"] = "new"
        headers["content-type"] = content_type
        if authenticated:
            if session is None:
                raise AuthenticationError("Login required")
            headers["dreame-auth"] = session.access_token
        return headers

    @staticmethod
    def _json(response: Response) -> dict[str, Any]:
        try:
            value = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TransportError("Cloud returned an invalid JSON response") from None
        if not isinstance(value, dict):
            raise TransportError("Cloud response must be an object")
        return value

    async def login(self) -> Session:
        async with self._auth_lock:
            return await self._login()

    async def _login(self) -> Session:
        for attempt in range(2):
            refresh = self._refresh_token
            prefix = "scope=all&platform=ANDROID&type=account"
            if refresh:
                body = f"grant_type=refresh_token&{prefix}&refresh_token={quote(refresh, safe='')}"
            else:
                if not self._username or not self._password:
                    raise AuthenticationError("A refresh token or username and password is required")
                hashed = hashlib.md5((self._password + self._password_salt).encode()).hexdigest()
                body = f"grant_type=password&{prefix}&username={quote(self._username, safe='')}&password={hashed}"
                if self._session and self._session.country and self._session.language:
                    body += f"&country={quote(self._session.country, safe='')}&lang={quote(self._session.language, safe='')}"
            response = await self._transport.request("POST", self.base_url + self._endpoints["login"], self._headers("application/x-www-form-urlencoded"), body.encode(), 10)
            if response.status == 429:
                raise RateLimitError(response.headers.get("retry-after"))
            if response.status in {400, 401, 403}:
                try:
                    invalid_refresh = "refresh token" in str(self._json(response).get("error_description", "")).lower()
                except TransportError:
                    invalid_refresh = False
                if refresh and invalid_refresh and self._username and self._password and attempt == 0:
                    self._refresh_token = None
                    continue
                self._session = None
                raise AuthenticationError("Dreame login rejected the credentials or refresh token")
            if response.status != 200:
                raise ApiError(status=response.status)
            data = self._json(response)
            try:
                session = Session(
                    access_token=data["access_token"], refresh_token=data["refresh_token"],
                    uid=str(data["uid"]), expires_at=self._clock() + int(data["expires_in"]),
                    tenant_id=str(data.get("tenant_id") or self.profile["tenant_id"]),
                    region=data.get("region"), language=data.get("lang"),
                    country=data.get("country"), domain=data.get("domain"),
                )
            except (KeyError, TypeError, ValueError):
                raise AuthenticationError("Login response is missing valid session fields") from None
            self._session = session
            self._refresh_token = session.refresh_token
            if self._on_session:
                self._on_session(session)
            return session
        raise AuthenticationError("Dreame login failed")

    async def ensure_session(self) -> Session:
        async with self._auth_lock:
            if self._session is None or self._session.expires_at - self._clock() <= 600:
                return await self._login()
            return self._session

    async def _post(self, path: str, params: dict[str, Any] | None, *, binary: bool = False):
        return await self._authenticated_request("POST", path, params, binary=binary)

    async def _authenticated_request(self, method: str, path: str, params: dict[str, Any] | None, *, binary: bool = False):
        await self.ensure_session()
        for attempt in range(2):
            old_session = self._session
            signed = sign(params, self.profile["signing_key"], int(self._clock() * 1000)) if params is not None and method == "POST" else None
            body = json.dumps(signed, separators=(",", ":")).encode() if signed is not None else None
            query = "?" + urlencode(params) if method == "GET" and params else ""
            response = await self._transport.request(method, self.base_url + path + query, self._headers("application/json", True), body, 15 if binary else 10)
            if response.status == 429:
                raise RateLimitError(response.headers.get("retry-after"))
            if response.status == 401:
                try:
                    code = self._json(response).get("code")
                except TransportError:
                    code = None
                if code not in (None, 401):
                    self._session = None
                    raise AuthenticationError("Dreame session invalidated; reauthentication required")
                if attempt == 0:
                    async with self._auth_lock:
                        if self._session is old_session:
                            await self._login()
                    continue
                self._session = None
                raise AuthenticationError("Dreame rejected the refreshed session")
            if response.status != 200:
                raise ApiError(status=response.status)
            if binary:
                return response.body
            data = self._json(response)
            code = data.get("code")
            if code not in (None, 0) or data.get("success") is False:
                if code == 401:
                    self._session = None
                    raise AuthenticationError("Dreame session invalidated")
                raise ApiError(code=code)
            return data
        raise AuthenticationError("Dreame request failed after refreshing")

    async def request(self, endpoint: str, params: dict[str, Any] | None = None):
        """Return the full envelope for an extracted endpoint, no guessed routes."""
        if endpoint not in self._endpoints or endpoint in {"login", "send_command", "device_file"}:
            raise ValueError("Use the dedicated login, RPC or binary-file method")
        return await self._post(self._endpoints[endpoint], params)

    async def list_devices_response(self, *, current: int | None = None, size: int = 100, include_shared: bool = True, language: str = "en") -> dict[str, Any]:
        """Raw envelope. No current reproduces Tasshack's bodyless request.

        Pagination arguments are corroborated by TA2k/ioBroker.dreame;
        these are additional evidence, not arguments present in Tasshack.
        """
        if current is None:
            return await self.request("list_devices")
        if current < 1 or not 1 <= size <= 100:
            raise ValueError("Current must be positive and page size between 1 and 100")
        params = {"sharedStatus": 1 if include_shared else 0, "current": current, "size": size, "lang": language}
        return await self.request("list_devices", params)

    async def device_pages(self, *, size: int = 100, include_shared: bool = True, max_pages: int = 100):
        """Enumerate list pages; detect ignored pagination instead of losing devices."""
        seen = set()
        for current in range(1, max_pages + 1):
            response = await self.list_devices_response(current=current, size=size, include_shared=include_shared)
            try:
                page = response["data"]["page"]
                records = page["records"]
                if not isinstance(records, list):
                    raise TypeError
                ids = {str(record["did"]) for record in records}
                total = int(page["total"]) if page.get("total") is not None else None
                pages = int(page["pages"]) if page.get("pages") is not None else None
                reported_current = int(page.get("current", current))
            except (KeyError, TypeError, ValueError):
                raise TransportError("Unexpected device list response shape") from None
            if reported_current != current or (records and not ids - seen):
                raise IncompleteDiscoveryError(len(seen), max(total or 0, len(seen) + 1))
            seen.update(ids)
            yield response
            if total is not None and len(seen) >= total:
                return
            if not records or (pages is not None and current >= pages) or (pages is None and total is None and len(records) < size):
                if total is not None and len(seen) < total:
                    raise IncompleteDiscoveryError(len(seen), total)
                return
        raise IncompleteDiscoveryError(len(seen), max(total or 0, len(seen) + 1))

    async def list_devices(self, **page_options) -> list[Device]:
        devices = {}
        async for response in self.device_pages(**page_options):
            for record in response["data"]["page"]["records"]:
                device = Device.from_record(record)
                devices[device.did] = device
        return list(devices.values())

    async def get_device_info(self, did: str) -> dict[str, Any]:
        return (await self.request("device_info", {"did": str(did)}))["data"]

    async def get_otc_info(self, did: str) -> dict[str, Any]:
        return (await self.request("otc_info", {"did": str(did)}))["data"]

    async def plugin_manifest(self, device: Device, *, os_code: int = 0, app_version: int | None = None):
        """Read the model's downloadable app-plugin metadata.

        Additional route corroborated by consolesplayingconsoles/dreamehome-client's mobile
        string-table research; this route is absent from the Tasshack catalog.
        Exact L9 downloads verified OS 0=iOS and 1=Android. OS 2 supplied a
        HarmonyOS vacuum bundle and empty laundry records. Defaults use the
        tested iOS lookup and verified DreameHome 2.6.6.3 version code.
        """
        return await self._plugin_manifest(device, "appplugin", os_code, app_version)

    async def h5_plugin_manifest(self, device: Device, *, os_code: int = 0, app_version: int | None = None):
        """H5 lookup route recovered from a publisher-verified DreameHome APK.

        The query contract is initially experimental; preserve the response
        envelope rather than assuming it matches the RN plugin schema.
        """
        return await self._plugin_manifest(device, "h5plugin", os_code, app_version)

    async def _plugin_manifest(self, device, plugin_kind, os_code, app_version):
        if isinstance(os_code, bool) or os_code not in (0, 1, 2):
            raise ValueError("Plugin OS code must be 0 (iOS), 1 (Android) or 2 (HarmonyOS)")
        default_version = 102060603 if self.account_type == "dreame" else int(self.profile["app_version"])
        version = app_version if app_version is not None else default_version
        if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
            raise ValueError("Plugin app version must be a positive numeric version code")
        return await self._authenticated_request("GET", "/dreame-product/upgrades/" + plugin_kind, {
            "model": device.model, "did": device.did, "os": os_code, "appVer": version,
        })

    async def rpc(self, device: Device, method: str, params: Any) -> Any:
        """Raw commands are explicit; arbitrary schemas are never inferred."""
        suffix = ""
        if device.bind_domain:
            suffix = "-" + device.bind_domain.split(".")[0]
            if not all(c.isalnum() or c in "-_" for c in suffix):
                raise ValueError("Unexpected bindDomain command shard")
        self._request_id += 1
        request_id = self._request_id
        did = device.did
        payload = {"did": did, "id": request_id, "data": {"did": did, "id": request_id, "method": method, "params": params}}
        response = await self._post(self._endpoints["send_command"].format(broker_suffix=suffix), payload)
        data = response.get("data")
        if not isinstance(data, dict) or "result" not in data:
            raise TransportError("RPC response has no result; request was not replayed")
        return data["result"]

    async def read_properties(self, device: Device, pairs: Iterable[tuple[int, int]], *, batch_size: int = 15) -> list[dict[str, Any]]:
        if not 1 <= batch_size <= 15:
            raise ValueError("Property batch size must be between 1 and 15")
        # The vacuum source uses opaque local enum IDs for read correlation.
        # Exact L9 app plugins instead put the actual device DID in each item.
        laundry = device.model in {"dreame.washer.l9nacn", "dreame.dryer.l9nacn"}
        params = [{"did": device.did if laundry else f"{siid}.{piid}", "siid": siid, "piid": piid} for siid, piid in pairs]
        results = []
        for start in range(0, len(params), batch_size):
            result = await self.rpc(device, "get_properties", params[start:start + batch_size])
            if not isinstance(result, list):
                raise TransportError("Property RPC result must be a list")
            results.extend(result)
        return results

    async def write_properties(self, device: Device, properties: Iterable[tuple[int, int, Any]]):
        return await self.rpc(device, "set_properties", [{"did": device.did, "siid": siid, "piid": piid, "value": value} for siid, piid, value in properties])

    async def action(self, device: Device, siid: int, aiid: int, inputs: list[Any] | None = None):
        return await self.rpc(device, "action", {"did": device.did, "siid": siid, "aiid": aiid, "in": inputs or []})

    async def cloud_properties(self, did: str, keys: str | list[str]):
        return (await self.request("cloud_properties", {"did": str(did), "keys": keys}))["data"]

    async def history(self, device: Device, key: str, *, kind: str = "prop", limit: int = 1, time_start: int = 1687019188):
        if kind not in {"prop", "event", "action"}:
            raise ValueError("History kind must be prop, event or action")
        siid, iid = key.split(".")
        session = await self.ensure_session()
        uid = device.owner_uid or session.uid
        field = {"prop": "piid", "event": "eiid", "action": "aiid"}[kind]
        payload = {"uid": uid, "did": device.did, "from": time_start or 1687019188, "limit": limit, "siid": siid, "region": self.region, "type": 3, field: iid}
        return (await self.request("history", payload))["data"]["list"]

    async def get_device_data(self, did: str, keys: list[str]):
        return (await self.request("get_device_data", {"did": str(did), "model": keys}))["data"]

    async def set_device_data(self, did: str, values: Any):
        return (await self.request("set_device_data", {"did": str(did), "model": values}))["result"]

    async def download_url(self, device: Device, object_name: str, *, interim: bool = True):
        payload = {"did": device.did, "model": device.model, "filename": object_name if interim else object_name[1:], "region": self.region}
        if not interim:
            session = await self.ensure_session()
            payload["uid"] = device.owner_uid or session.uid
        return (await self.request("download_url" if interim else "oss_download_url", payload))["data"]

    async def device_file(self, device: Device, file_name: str, file_type: str) -> bytes:
        session = await self.ensure_session()
        payload = {"did": device.did, "uid": device.owner_uid or session.uid, "fileinfo": json.dumps({"filename": file_name, "type": file_type}, separators=(",", ":"))}
        return await self._post(self._endpoints["device_file"], payload, binary=True)

    async def download(self, url: str) -> bytes:
        """Signed storage URL; never send account authentication headers."""
        validate_https_url(url)
        response = await self._transport.request("GET", url, {"user-agent": "okhttp/4.12.0", "accept-encoding": "identity"}, None, 10)
        if response.status != 200:
            raise ApiError(status=response.status)
        return response.body
