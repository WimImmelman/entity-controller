# SPDX-License-Identifier: GPL-3.0-or-later
"""The global on/off switch: one entity that overrides every controller at once."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    DATA_ENABLED,
    GLOBAL_SWITCH_NAME,
    GLOBAL_SWITCH_UNIQUE_ID,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the switch platform (loaded by the integration, not from YAML)."""
    if discovery_info is None:
        return
    async_add_entities([EntityControllerGlobalSwitch(hass)])


def set_global_enabled(hass, enabled):
    """Store the global flag and tell every controller about the change.

    Shared by the switch entity and the tests. Controllers read the flag
    through ``Model.is_globally_enabled()`` whenever they evaluate their
    override state, and ``global_enabled_changed()`` moves the ones that are
    already running into or out of ``overridden`` right away.
    """
    data = hass.data.setdefault(DOMAIN, {})
    data[DATA_ENABLED] = bool(enabled)
    for device in list(data.get("devices", [])):
        model = getattr(device, "model", None)
        if model is not None:
            model.global_enabled_changed(bool(enabled))


class EntityControllerGlobalSwitch(SwitchEntity, RestoreEntity):
    """``switch.entity_controller``: ON is normal operation, OFF overrides every controller.

    The switch is created by the integration itself, so it exists whatever the
    YAML says and cannot be forgotten on a new controller. Its state is
    restored across restarts and is not touched by ``entity_controller.reload``.
    """

    _attr_has_entity_name = False
    _attr_name = GLOBAL_SWITCH_NAME
    _attr_unique_id = GLOBAL_SWITCH_UNIQUE_ID
    _attr_should_poll = False

    def __init__(self, hass):
        self.hass = hass
        self._attr_is_on = True

    @property
    def icon(self):
        return "mdi:motion-sensor" if self.is_on else "mdi:motion-sensor-off"

    @property
    def extra_state_attributes(self):
        devices = self.hass.data.get(DOMAIN, {}).get("devices", [])
        return {"controllers": len(devices)}

    async def async_added_to_hass(self):
        """Restore the last state; a missing one means enabled."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        enabled = not (last is not None and last.state == STATE_OFF)
        if not enabled:
            _LOGGER.info("Entity Controller was switched off before the restart; controllers stay overridden")
        self._apply(enabled)

    async def async_turn_on(self, **kwargs):
        self._apply(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._apply(False)
        self.async_write_ha_state()

    def _apply(self, enabled):
        self._attr_is_on = enabled
        set_global_enabled(self.hass, enabled)
