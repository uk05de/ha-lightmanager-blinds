"""Config flow for Light Manager Blinds."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_LM_AIR_HOST,
    CONF_BLINDS,
    CONF_BLIND_NAME,
    CONF_LM_AIR_ID_UP,
    CONF_LM_AIR_ID_DOWN,
    CONF_LM_AIR_ID_STOP,
    CONF_RUNTIME_UP,
    CONF_RUNTIME_DOWN,
)
from .lm_air import LightManagerAir


class LightManagerBlindsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Light Manager Blinds."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step — enter LM Air IP."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_LM_AIR_HOST]
            lm_air = LightManagerAir(host)

            if await lm_air.test_connection():
                await self.async_set_unique_id(f"lm_air_{host}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Light Manager Air ({host})",
                    data={CONF_LM_AIR_HOST: host},
                    options={CONF_BLINDS: []},
                )
            else:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LM_AIR_HOST, default=""): str,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow handler."""
        return LightManagerBlindsOptionsFlow(config_entry)


class LightManagerBlindsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow — add, edit, remove blinds."""

    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        """Main options menu."""
        blinds = self._entry.options.get(CONF_BLINDS, [])

        menu_options = ["add_blind"]
        if blinds:
            menu_options.append("remove_blind")

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={
                "count": str(len(blinds)),
            },
        )

    async def async_step_add_blind(self, user_input=None):
        """Add a new blind."""
        if user_input is not None:
            blinds = list(self._entry.options.get(CONF_BLINDS, []))
            blinds.append({
                CONF_BLIND_NAME: user_input[CONF_BLIND_NAME],
                CONF_LM_AIR_ID_UP: user_input[CONF_LM_AIR_ID_UP],
                CONF_LM_AIR_ID_DOWN: user_input[CONF_LM_AIR_ID_DOWN],
                CONF_LM_AIR_ID_STOP: user_input[CONF_LM_AIR_ID_STOP],
                CONF_RUNTIME_UP: user_input[CONF_RUNTIME_UP],
                CONF_RUNTIME_DOWN: user_input[CONF_RUNTIME_DOWN],
            })

            return self.async_create_entry(
                title="",
                data={CONF_BLINDS: blinds},
            )

        return self.async_show_form(
            step_id="add_blind",
            data_schema=vol.Schema({
                vol.Required(CONF_BLIND_NAME): str,
                vol.Required(CONF_LM_AIR_ID_UP): int,
                vol.Required(CONF_LM_AIR_ID_DOWN): int,
                vol.Required(CONF_LM_AIR_ID_STOP): int,
                vol.Required(CONF_RUNTIME_UP, default=20.0): vol.Coerce(float),
                vol.Required(CONF_RUNTIME_DOWN, default=14.0): vol.Coerce(float),
            }),
        )

    async def async_step_remove_blind(self, user_input=None):
        """Remove a blind."""
        blinds = list(self._entry.options.get(CONF_BLINDS, []))

        if user_input is not None:
            name_to_remove = user_input["blind"]
            blinds = [b for b in blinds if b[CONF_BLIND_NAME] != name_to_remove]
            return self.async_create_entry(
                title="",
                data={CONF_BLINDS: blinds},
            )

        blind_names = {b[CONF_BLIND_NAME]: b[CONF_BLIND_NAME] for b in blinds}

        return self.async_show_form(
            step_id="remove_blind",
            data_schema=vol.Schema({
                vol.Required("blind"): vol.In(blind_names),
            }),
        )
