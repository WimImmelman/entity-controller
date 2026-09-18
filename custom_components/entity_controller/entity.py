# SPDX-License-Identifier: GPL-3.0-or-later
"""EntityController: the Home Assistant entity that exposes a Model's state."""
import logging
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import entity
from homeassistant.helpers import event

from .model import Model, STARTUP_DELAY
from .const import (
    CONF_STATE_ENTITIES,
    CONF_DELAY,
    CONF_GRACEFUL_OFF,
)

_LOGGER = logging.getLogger(__name__)


class EntityController(entity.Entity):
    from .entity_services import (
        async_entity_service_activate as async_activate,
        async_entity_service_clear_block as async_clear_block,
        async_entity_service_enable_block as async_enable_block,
        async_entity_service_enable_stay_mode as async_enable_stay_mode,
        async_entity_service_disable_stay_mode as async_disable_stay_mode,
        async_entity_service_set_night_mode as async_set_night_mode,
    )

    def __init__(self, hass, config, machine, startup_delay=STARTUP_DELAY):
        self.attributes = {}
        self.may_update = False
        self.model = None
        self.context_id = None
        self.friendly_name = config.get(CONF_NAME, "Motion Light")
        if "friendly_name" in config:
            self.friendly_name = config.get("friendly_name")
        try:
            self.model = Model(hass, config, machine, self, startup_delay)
        except AttributeError as e:
            _LOGGER.error(
                "Configuration error! Please ensure you use plural keys for lists. e.g. sensors, entities." + e
            )
        event.async_call_later(hass, 1, self.do_update)

    @property
    def state(self):
        """Return the state of the entity."""
        return self.model.state

    @property
    def name(self):
        """Return the state of the entity."""
        return self.friendly_name

    @property
    def icon(self):
        """Return the entity icon."""
        if self.model.state == "idle":
            return "mdi:circle-outline"
        if self.model.state == "active":
            return "mdi:check-circle"
        if self.model.state == "active_timer":
            return "mdi:timer-outline"
        if self.model.state == "constrained":
            return "mdi:cancel"
        if self.model.state == "overridden":
            return "mdi:timer-off-outline"
        if self.model.state == "blocked":
            return "mdi:close-circle"
        return "mdi:eye"

    @property
    def state_attributes(self):
        """Return the state of the entity."""
        return self.attributes.copy()

    def reset_state(self):
        """ Reset state attributes by removing any state specific attributes when returning to idle state """
        _LOGGER.debug("Resetting state")
        att = {}

        PERSISTED_STATE_ATTRIBUTES = [
            "last_triggered_by",
            "last_triggered_at",
            CONF_STATE_ENTITIES,
            "control_entities",
            "sensor_entities",
            "hold_sensor_entities",
            "forced_sensor_entities",
            "override_entities",
            CONF_DELAY,
            "sensor_type",
            "mode",
            "start_time",
            "end_time",
            "lux_entity",
            "lux_threshold",
            "lux_bright_states",
            CONF_GRACEFUL_OFF,  # config echo, must survive the idle reset like the other config keys
        ]
        for k, v in self.attributes.items():
            if k in PERSISTED_STATE_ATTRIBUTES:
                att[k] = v

        self.attributes = att
        self.do_update()

    @callback
    def do_update(self, wait=False, **kwargs):
        """ Schedules an entity state update with HASS """
        # _LOGGER.debug("Scheduled update with HASS")
        if self.may_update:
            self.schedule_update_ha_state(True)

    def set_attr(self, k, v):
        if k == CONF_DELAY:
            v = str(v) + "s"
        self.attributes[k] = v

    # HA Callbacks
    async def async_added_to_hass(self):
        """Register update dispatcher."""
        self.may_update = True

    async def async_teardown(self):
        """Detach the controller from HA (used by the reload service).

        Stops the model (listeners, timers, persisted state) and removes the
        entity, so a rebuilt controller can take over the same entity id.
        """
        self.may_update = False
        if self.model is not None:
            await self.model.async_teardown()
        if self.hass is not None and self.entity_id is not None:
            await self.async_remove()

    @property
    def should_poll(self) -> bool:
        """EntityController will push its state to HA"""
        return False
