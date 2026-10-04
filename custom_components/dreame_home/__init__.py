"""Read-only Dreame Home account integration."""

from homeassistant.const import CONF_USERNAME, EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.catalog import load_catalog
from .api.client import DreameHomeClient
from .const import CONF_ACCOUNT_UID, CONF_REFRESH_TOKEN, CONF_REGION, CONF_VISITOR_ID, PLATFORMS
from .coordinator import DreameCoordinator
from .transport import AiohttpTransport


async def async_setup_entry(hass, entry):
    # Catalog reads happen in an executor before synchronous constructors use them.
    for catalog in ("api", "models", "properties", "l9_washer", "l9_dryer"):
        await hass.async_add_executor_job(load_catalog, catalog)

    def persist_session(session):
        if str(session.uid) != entry.data[CONF_ACCOUNT_UID]:
            raise ConfigEntryAuthFailed("The authenticated Dreame account changed")
        if session.refresh_token != entry.data.get(CONF_REFRESH_TOKEN):
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_REFRESH_TOKEN: session.refresh_token})

    api = DreameHomeClient(
        entry.data[CONF_USERNAME], region=entry.data[CONF_REGION],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        visitor_id=entry.data[CONF_VISITOR_ID], on_session=persist_session,
        transport=AiohttpTransport(async_get_clientsession(hass)),
    )
    coordinator = DreameCoordinator(hass, entry, api)
    entry.runtime_data = coordinator

    async def shutdown(_event):
        await coordinator.async_stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown))
    try:
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_start_subscriptions()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.async_stop()
        raise
    return True


async def async_unload_entry(hass, entry):
    coordinator = entry.runtime_data
    # Keep observations and clients alive until platform removal succeeds, while
    # preventing MQTT from scheduling new entities during that awaited removal.
    coordinator.entity_discovery_suspended = True
    try:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    except BaseException:
        coordinator.entity_discovery_suspended = False
        coordinator.async_update_listeners()
        raise
    if not unloaded:
        coordinator.entity_discovery_suspended = False
        coordinator.async_update_listeners()
        return False
    await coordinator.async_stop()
    return True
