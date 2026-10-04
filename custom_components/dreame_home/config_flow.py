"""Account authentication, with refresh-token persistence only."""

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, TextSelector, TextSelectorConfig, TextSelectorType

from .api.catalog import load_catalog
from .api.client import DreameHomeClient
from .api.exceptions import AuthenticationError, DreameError, RateLimitError
from .const import CONF_ACCOUNT_UID, CONF_MQTT, CONF_REFRESH_TOKEN, CONF_REGION, CONF_VISITOR_ID, DOMAIN, REGIONS
from .transport import AiohttpTransport

# Match the schema implementation used by the running HA flow framework.
# Core is migrating from voluptuous to probatio; never mix their marker/error types.
schema_api = getattr(data_entry_flow, "vol", None)
if schema_api is None:
    import probatio as schema_api


class DreameHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _authenticate(self, user_input):
        await self.hass.async_add_executor_job(load_catalog, "api")
        api = DreameHomeClient(
            user_input[CONF_USERNAME], user_input[CONF_PASSWORD],
            region=user_input[CONF_REGION],
            transport=AiohttpTransport(async_get_clientsession(self.hass)),
        )
        await api.list_devices()  # Validates authentication and complete pagination.
        session = api.session
        return {
            CONF_USERNAME: user_input[CONF_USERNAME], CONF_REGION: user_input[CONF_REGION],
            CONF_ACCOUNT_UID: session.uid, CONF_REFRESH_TOKEN: session.refresh_token,
            CONF_VISITOR_ID: api.visitor_id, CONF_MQTT: user_input.get(CONF_MQTT, True),
        }

    async def async_step_user(self, user_input=None):
        return await self._credentials("user", user_input)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._credentials("reauth_confirm", user_input)

    async def _credentials(self, step_id, user_input):
        errors = {}
        existing = self._get_reauth_entry() if step_id == "reauth_confirm" else None
        defaults = existing.data if existing else {}
        if user_input is not None:
            try:
                data = await self._authenticate(user_input)
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except RateLimitError:
                errors["base"] = "rate_limited"
            except DreameError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"dreame:{data[CONF_REGION]}:{data[CONF_ACCOUNT_UID]}")
                if existing:
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(existing, data_updates=data)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Dreame Home ({data[CONF_REGION].upper()})", data=data)
        fields = {
            schema_api.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            schema_api.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            schema_api.Required(CONF_REGION, default=defaults.get(CONF_REGION, "eu")): SelectSelector(SelectSelectorConfig(options=list(REGIONS))),
            schema_api.Optional(CONF_MQTT, default=defaults.get(CONF_MQTT, True)): bool,
        }
        return self.async_show_form(step_id=step_id, data_schema=schema_api.Schema(fields), errors=errors)
