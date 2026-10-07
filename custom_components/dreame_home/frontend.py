"""Load the bundled laundry dashboard card without a separate resource install."""

import asyncio
from pathlib import Path
from urllib.parse import quote

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.loader import async_get_integration

from .const import DOMAIN

DATA_FRONTEND = "dreame_home_frontend"
CARD_PATH = "/dreame_home/dreame-home-laundry-card.js"
PHOTO_NAMES = ("washer.png", "dryer.png")


async def async_register_frontend(hass):
    """Register the public module and two photos once per HA instance."""
    state = hass.data.setdefault(DATA_FRONTEND, {
        "lock": asyncio.Lock(), "static_registered": False, "url": None,
    })
    integration = await async_get_integration(hass, DOMAIN)
    url = f"{CARD_PATH}?v={quote(str(integration.version or '0'), safe='')}"
    async with state["lock"]:
        if not state["static_registered"]:
            # Each public asset has an explicit route; no directory is exposed.
            frontend = Path(__file__).parent / "frontend"
            await hass.http.async_register_static_paths([
                StaticPathConfig(CARD_PATH, str(frontend / "dreame-home-laundry-card.js"), True),
                *(StaticPathConfig(f"/dreame_home/{name}", str(frontend / "assets" / name), True)
                  for name in PHOTO_NAMES),
            ])
            state["static_registered"] = True
        if state["url"] == url:
            return
        add_extra_js_url(hass, url)
        if state["url"] is not None:
            remove_extra_js_url(hass, state["url"])
        state["url"] = url
