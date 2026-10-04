"""Use Home Assistant's managed, verified HTTP session."""

import asyncio

from aiohttp import ClientError, ClientSession, ClientTimeout

from .api.exceptions import TransportError
from .api.transport import Response, validate_https_url


class AiohttpTransport:
    def __init__(self, session: ClientSession):
        self.session = session

    async def request(self, method, url, headers, body, timeout):
        validate_https_url(url)
        try:
            async with self.session.request(
                method, url, headers=headers, data=body,
                timeout=ClientTimeout(total=timeout), allow_redirects=False,
            ) as response:
                return Response(response.status, await response.read(),
                                {key.lower(): value for key, value in response.headers.items()})
        except (ClientError, asyncio.TimeoutError, OSError):
            raise TransportError("Verified HTTPS request failed") from None
