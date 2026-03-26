"""Light Manager Blinds integration."""

import logging

from aiohttp import web

from homeassistant.components.webhook import async_register, async_unregister
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_LM_AIR_HOST, CONF_BLINDS, CONF_BLIND_NAME
from .lm_air import LightManagerAir

log = logging.getLogger(__name__)

PLATFORMS = ["cover"]
WEBHOOK_ID = "rollo_webhook"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Light Manager Blinds from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    lm_air = LightManagerAir(entry.data[CONF_LM_AIR_HOST])
    hass.data[DOMAIN][entry.entry_id] = {
        "lm_air": lm_air,
        "entry": entry,
        "covers": {},  # populated by cover.py
    }

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register webhook for remote control
    async_register(
        hass, DOMAIN, "Rollo Webhook", WEBHOOK_ID, _handle_webhook
    )
    log.info("Webhook registered: /api/webhook/%s", WEBHOOK_ID)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    async_unregister(hass, WEBHOOK_ID)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _handle_webhook(hass: HomeAssistant, webhook_id: str, request: web.Request):
    """Handle webhook from Light Manager Air (remote control).

    URL: /api/webhook/rollo_webhook?cover=kueche&action=down
    """
    query = request.query
    cover_name = query.get("cover", "")
    action = query.get("action", "")

    if not cover_name or action not in ("up", "down", "stop"):
        log.warning("Invalid webhook: cover=%s action=%s", cover_name, action)
        return web.Response(status=400, text="Invalid parameters")

    # Find the cover entity by name
    for entry_data in hass.data.get(DOMAIN, {}).values():
        covers = entry_data.get("covers", {})
        # Match by slug (kueche) or by full name (Küche)
        for slug, cover in covers.items():
            if slug == cover_name or cover.name.lower() == cover_name.lower():
                log.info("Webhook: %s -> %s (external)", cover.name, action)
                await cover.async_external_command(action)
                return web.Response(text="OK")

    log.warning("Webhook: cover '%s' not found", cover_name)
    return web.Response(status=404, text="Cover not found")
