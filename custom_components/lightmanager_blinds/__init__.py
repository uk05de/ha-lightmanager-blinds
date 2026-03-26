"""Light Manager Blinds integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_LM_AIR_HOST
from .lm_air import LightManagerAir

log = logging.getLogger(__name__)

PLATFORMS = ["cover"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Light Manager Blinds from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    lm_air = LightManagerAir(entry.data[CONF_LM_AIR_HOST])
    hass.data[DOMAIN][entry.entry_id] = {
        "lm_air": lm_air,
        "entry": entry,
    }

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)
