"""Cover platform for Light Manager Blinds."""

import asyncio
import logging
import time

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
    ATTR_POSITION,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    CONF_BLINDS,
    CONF_BLIND_NAME,
    CONF_LM_AIR_ID_UP,
    CONF_LM_AIR_ID_DOWN,
    CONF_LM_AIR_ID_STOP,
    CONF_RUNTIME_UP,
    CONF_RUNTIME_DOWN,
)

log = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cover entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    lm_air = data["lm_air"]
    blinds = entry.options.get(CONF_BLINDS, [])

    entities = []
    covers_registry = hass.data[DOMAIN][entry.entry_id]["covers"]

    # Build set of expected unique_ids from current config
    expected_unique_ids = set()
    for blind_config in blinds:
        entity = LightManagerBlind(lm_air, blind_config, entry.entry_id)
        entities.append(entity)
        expected_unique_ids.add(entity.unique_id)
        # Register for webhook lookup by slug
        covers_registry[entity.slug] = entity

    # Remove stale entities and devices from the registries
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    expected_device_ids = {(DOMAIN, f"lm_blind_{e.slug}") for e in entities}

    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if reg_entry.unique_id not in expected_unique_ids:
            log.info("Removing stale entity: %s", reg_entry.entity_id)
            ent_reg.async_remove(reg_entry.entity_id)

    for dev_entry in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if not dev_entry.identifiers & expected_device_ids:
            log.info("Removing stale device: %s", dev_entry.name)
            dev_reg.async_remove_device(dev_entry.id)

    async_add_entities(entities)


class LightManagerBlind(CoverEntity, RestoreEntity):
    """Representation of a blind controlled via Light Manager Air."""

    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )
    _attr_has_entity_name = True

    def __init__(self, lm_air, config: dict, entry_id: str):
        self._lm_air = lm_air
        self._name = config[CONF_BLIND_NAME]
        self._id_up = config[CONF_LM_AIR_ID_UP]
        self._id_down = config[CONF_LM_AIR_ID_DOWN]
        self._id_stop = config[CONF_LM_AIR_ID_STOP]
        self._runtime_up = config[CONF_RUNTIME_UP]
        self._runtime_down = config[CONF_RUNTIME_DOWN]

        self._position = 0  # 0 = closed, 100 = open
        self._moving = None  # None, "up", "down"
        self._move_start_time = None
        self._move_start_position = None
        self._move_task = None

        self.slug = self._name.lower().replace(" ", "_").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        self._attr_unique_id = f"lm_blind_{self.slug}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"lm_blind_{self.slug}")},
            "name": self._name,
            "manufacturer": "jbmedia",
            "model": "Light Manager Air",
        }

    @property
    def name(self) -> str:
        return self._name

    @property
    def current_cover_position(self) -> int:
        """Return current position (0=closed, 100=open)."""
        if self._moving and self._move_start_time:
            return self._calculate_live_position()
        return round(self._position)

    @property
    def is_closed(self) -> bool:
        return self.current_cover_position == 0

    @property
    def is_opening(self) -> bool:
        return self._moving == "up"

    @property
    def is_closing(self) -> bool:
        return self._moving == "down"

    async def async_added_to_hass(self) -> None:
        """Restore previous state on HA restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            pos = last_state.attributes.get(ATTR_POSITION)
            if pos is not None:
                self._position = pos
                log.info("Restored %s position to %d%%", self._name, self._position)

    # --- Commands ---

    async def async_open_cover(self, **kwargs) -> None:
        """Open the cover."""
        await self._start_move("up")

    async def async_close_cover(self, **kwargs) -> None:
        """Close the cover."""
        await self._start_move("down")

    async def async_stop_cover(self, **kwargs) -> None:
        """Stop the cover."""
        await self._stop_move()

    async def async_set_cover_position(self, **kwargs) -> None:
        """Move to a specific position."""
        target = kwargs.get(ATTR_POSITION, 0)

        if target == self._position:
            return

        if target > self._position:
            direction = "up"
            runtime = self._runtime_up
            distance = target - self._position
        else:
            direction = "down"
            runtime = self._runtime_down
            distance = self._position - target

        move_duration = (distance / 100.0) * runtime
        await self._start_move(direction, duration=move_duration)

    # --- External control (webhook from remote) ---

    async def async_external_command(self, action: str) -> None:
        """Handle external command from webhook (remote control)."""
        log.warning("DEBUG %s: external command '%s', current state: moving=%s, position=%s, task=%s",
                    self._name, action, self._moving, self._position, self._move_task is not None)
        if action in ("up", "down"):
            await self._start_move(action, external=True)
        elif action == "stop":
            await self._stop_move(external=True)

    # --- Movement logic ---

    async def _start_move(self, direction: str, duration: float = None,
                          external: bool = False) -> None:
        """Start moving the blind.

        Args:
            direction: "up" or "down"
            duration: optional movement duration in seconds
            external: if True, skip sending command to LM Air (remote already did it)
        """
        # Stop any current movement first
        if self._moving:
            await self._stop_move(external=external)

        runtime = self._runtime_up if direction == "up" else self._runtime_down

        full_movement = duration is None
        if full_movement:
            if direction == "up":
                duration = ((100 - self._position) / 100.0) * runtime
            else:
                duration = (self._position / 100.0) * runtime

        if duration <= 0:
            log.warning("DEBUG %s: duration <= 0 (%.2f), skipping move", self._name, duration)
            return

        # Drift correction: add buffer only when fully opening (mechanical end stop)
        if full_movement and direction == "up":
            duration += 1.5

        if not external:
            lm_id = self._id_up if direction == "up" else self._id_down
            success = await self._lm_air.send_command(lm_id)
            if not success:
                log.error("Failed to send %s command for %s", direction, self._name)
                return

        self._moving = direction
        self._move_start_time = time.monotonic()
        self._move_start_position = self._position
        self.async_write_ha_state()

        source = "external" if external else "HA"
        log.info("%s: moving %s for %.1fs (from %d%%, %s)",
                 self._name, direction, duration, self._position, source)

        # Schedule auto-stop (always send stop command, even for external moves)
        log.warning("DEBUG %s: scheduling auto-stop in %.1fs", self._name, duration)
        self._move_task = self.hass.async_create_task(
            self._auto_stop(duration)
        )

    async def _auto_stop(self, duration: float) -> None:
        """Auto-stop after duration."""
        await asyncio.sleep(duration)
        log.warning("DEBUG %s: auto-stop fired after %.1fs, sending stop command", self._name, duration)
        self._move_task = None  # Clear self-reference before stopping
        await self._stop_move()

    async def _stop_move(self, external: bool = False) -> None:
        """Stop movement and update position."""
        log.warning("DEBUG %s: _stop_move called, external=%s, moving=%s, task=%s",
                    self._name, external, self._moving, self._move_task is not None)
        if self._move_task and not self._move_task.done():
            self._move_task.cancel()
            self._move_task = None

        # Calculate final position
        if self._moving and self._move_start_time:
            self._position = self._calculate_live_position()

        # Send stop command (skip if triggered by remote)
        if not external:
            log.warning("DEBUG %s: sending stop command to LM Air (id=%s)", self._name, self._id_stop)
            await self._lm_air.send_command(self._id_stop)
        else:
            log.warning("DEBUG %s: skipping stop command (external)", self._name)

        log.warning("DEBUG %s: stopped at %d%%", self._name, self._position)

        self._moving = None
        self._move_start_time = None
        self._move_start_position = None
        self.async_write_ha_state()

    def _calculate_live_position(self) -> float:
        """Calculate current position based on elapsed time."""
        if not self._move_start_time or not self._moving:
            return self._position

        elapsed = time.monotonic() - self._move_start_time
        runtime = self._runtime_up if self._moving == "up" else self._runtime_down
        distance_percent = (elapsed / runtime) * 100.0

        if self._moving == "up":
            pos = self._move_start_position + distance_percent
        else:
            pos = self._move_start_position - distance_percent

        return max(0.0, min(100.0, pos))
