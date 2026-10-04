"""Verified HTTPS transport, injectable for HA and offline contract tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ssl
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

from .exceptions import TransportError


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    headers: dict[str, str]


class Transport(Protocol):
    async def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> Response: ...


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_https_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("An HTTPS URL without embedded credentials is required")


class HttpsTransport:
    """Stdlib backend; blocking I/O runs in a worker. TLS verification is mandatory.

    Does not reproduce upstream's custom TLS fingerprint. Regional cloud
    acceptance needs live validation. Redirects are not followed with credentials.
    """

    def __init__(self):
        self._context = ssl.create_default_context()

    async def request(self, method, url, headers, body, timeout) -> Response:
        validate_https_url(url)
        return await asyncio.to_thread(self._request, method, url, headers, body, timeout)

    def _request(self, method, url, headers, body, timeout):
        opener = build_opener(HTTPSHandler(context=self._context), _NoRedirects())
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with opener.open(req, timeout=timeout) as response:
                return Response(response.status, response.read(), {k.lower(): v for k, v in response.headers.items()})
        except HTTPError as error:
            with error:
                return Response(error.code, error.read(), {k.lower(): v for k, v in error.headers.items()})
        except (URLError, OSError, ValueError):
            raise TransportError("Verified HTTPS request failed") from None
