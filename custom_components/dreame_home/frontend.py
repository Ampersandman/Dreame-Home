"""Load the laundry card and scoped HACS branding compatibility module."""

import asyncio
from pathlib import Path
from urllib.parse import quote

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.loader import async_get_integration

from .const import DOMAIN

DATA_FRONTEND = "dreame_home_frontend"
CARD_PATH = "/dreame_home/dreame-home-laundry-card.js"
BRANDING_PATH = "/dreame_home/dreame-home-branding.js"
PHOTO_NAMES = ("washer.png", "dryer.png")
BRAND_NAMES = ("icon.png", "icon@2x.png", "dark_icon.png", "dark_icon@2x.png")


async def async_register_frontend(hass):
    """Register explicitly named public assets once per HA instance."""
    state = hass.data.setdefault(DATA_FRONTEND, {
        "lock": asyncio.Lock(), "static_registered": False, "url": None,
    })
    integration = await async_get_integration(hass, DOMAIN)
    version = quote(str(integration.version or "0"), safe="")
    async with state["lock"]:
        if not state["static_registered"]:
            # Each public asset has an explicit route; no directory is exposed.
            frontend = Path(__file__).parent / "frontend"
            await hass.http.async_register_static_paths([
                StaticPathConfig(CARD_PATH, str(frontend / "dreame-home-laundry-card.js"), True),
                StaticPathConfig(BRANDING_PATH, str(frontend / "dreame-home-branding.js"), True),
                *(StaticPathConfig(f"/dreame_home/{name}", str(frontend / "assets" / name), True)
                  for name in PHOTO_NAMES),
                *(StaticPathConfig(f"/dreame_home/brand/{name}", str(frontend.parent / "brand" / name), True)
                  for name in BRAND_NAMES),
            ])
            state["static_registered"] = True
        for key, path in (("url", CARD_PATH), ("branding_url", BRANDING_PATH)):
            url = f"{path}?v={version}"
            previous = state.get(key)
            if previous == url:
                continue
            add_extra_js_url(hass, url)
            if previous is not None:
                remove_extra_js_url(hass, previous)
            state[key] = url
