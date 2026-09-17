"""
This file is part of Entity Controller.

Entity Controller is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Entity Controller is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Entity Controller.  If not, see <https://www.gnu.org/licenses/>.

"""
"""
Entity controller component for Home Assistant.
Maintainer:       Wim Immelman (this fork)
Original author:  Daniel Mason (github.com/danobot/entity-controller)
Fork lineage:     github.com/pluskal/entity-controller (2026 features and fixes)
Version:          v9.13.1
Project Page:     https://github.com/WimImmelman/entity-controller
Documentation:    https://github.com/WimImmelman/entity-controller/blob/main/README.md
"""
import asyncio  # noqa: F401 - tests patch asyncio.run_coroutine_threadsafe through this package
import logging
from datetime import datetime

from homeassistant.const import SERVICE_RELOAD
from homeassistant.helpers import event  # noqa: F401 - tests patch event.async_* through this package
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.util import dt

from .entity import EntityController
from .entity_services import async_setup_entity_services
from .model import Model, STARTUP_DELAY
from .schema import MODE_SCHEMA, ENTITY_SCHEMA, PLATFORM_SCHEMA
from .state_machine import build_machine
from .const import (
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


DEPENDENCIES = ["light", "sensor", "binary_sensor", "cover", "fan", "media_player"]

VERSION = '9.13.1'

# A reload happens on a running HA where every entity is already known, so the
# rebuilt controllers only need a moment for their entities to be registered.
RELOAD_STARTUP_DELAY = 1

__all__ = [
    "async_setup",
    "async_reload",
    "EntityController",
    "Model",
    "STARTUP_DELAY",
    "RELOAD_STARTUP_DELAY",
    "VERSION",
    "MODE_SCHEMA",
    "ENTITY_SCHEMA",
    "PLATFORM_SCHEMA",
]


async def async_setup(hass, config):
    """Load graph configurations."""

    if(str(((datetime.now()).astimezone()).tzinfo) != str(dt.as_local(dt.now()).tzname())):
        _LOGGER.error("Timezones do not Match. Mismatched timezones may cause unintended behaviours.")
        _LOGGER.error("System DateTime: %s", ((datetime.now()).astimezone()).tzinfo )
        _LOGGER.error("Home Assistant DateTime: %s", dt.as_local(dt.now()).tzname())

    component = EntityComponent(_LOGGER, DOMAIN, hass)

    _LOGGER.info(
        "If you have ANY issues with EntityController (v"
        + VERSION
        + "), please enable DEBUG logging under the logger component and kindly report the issue on Github. https://github.com/danobot/entity-controller/issues"
    )

    async_setup_entity_services(component)

    machine = build_machine()

    hass.data[DOMAIN] = {
        "component": component,
        "machine": machine,
        "devices": [],
    }

    await _async_create_controllers(hass, config[DOMAIN], STARTUP_DELAY)

    async def _async_handle_reload(call):
        await async_reload(hass)

    hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_handle_reload)

    _LOGGER.info("The %s component is ready!", DOMAIN)

    return True

async def _async_create_controllers(hass, domain_config, startup_delay):
    """Instantiate one EntityController per configured key and add them to HA.

    ``domain_config`` is the validated ``config[DOMAIN]`` list. The new
    controllers are appended to ``hass.data[DOMAIN]["devices"]`` so a later
    reload can tear them down again.
    """
    data = hass.data[DOMAIN]
    devices = []
    for myconfig in domain_config:
        _LOGGER.info("Domain Configuration: " + str(myconfig))
        for key, item_config in myconfig.items():
            if not item_config:
                item_config = {}

            item_config["name"] = key
            devices.append(
                EntityController(hass, item_config, data["machine"], startup_delay)
            )

    data["devices"].extend(devices)
    await data["component"].async_add_entities(devices)
    return devices

async def async_reload(hass):
    """Re-read the ``entity_controller:`` YAML and rebuild every controller.

    Backs the ``entity_controller.reload`` service. The YAML is validated
    first; if it is invalid the running controllers are left untouched and
    the error is logged, exactly like the reload services of the core YAML
    integrations. Otherwise each controller is torn down (listeners and
    timers cancelled, state persisted, entity removed) and the set is rebuilt
    from the new configuration with a short startup delay. The rebuilt
    controllers restore their persisted state the same way they do after a
    Home Assistant restart.

    Returns True when the controllers were rebuilt.
    """
    data = hass.data.get(DOMAIN)
    if data is None:
        _LOGGER.error("reload :: %s is not set up", DOMAIN)
        return False

    conf = await async_integration_yaml_config(hass, DOMAIN)
    if conf is None or DOMAIN not in conf:
        _LOGGER.error(
            "reload :: configuration for %s is invalid or missing, keeping the running controllers",
            DOMAIN,
        )
        return False

    old_devices = list(data["devices"])
    _LOGGER.info("reload :: tearing down %d controller(s)", len(old_devices))
    for device in old_devices:
        try:
            await device.async_teardown()
        except Exception:  # noqa: BLE001 - one broken controller must not abort the reload
            _LOGGER.exception("reload :: teardown of %s failed", device.name)
    data["devices"] = []

    new_devices = await _async_create_controllers(hass, conf[DOMAIN], RELOAD_STARTUP_DELAY)
    _LOGGER.info("reload :: %d controller(s) rebuilt", len(new_devices))
    return True
