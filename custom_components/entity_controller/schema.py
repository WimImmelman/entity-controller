# SPDX-License-Identifier: GPL-3.0-or-later
"""Voluptuous schemas for the entity_controller YAML."""
import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_BEHAVIOURS,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
    DEFAULT_DELAY,
    CONF_CONTROL_ENTITIES,
    CONF_CONTROL_ENTITY,
    CONF_TRIGGER_ON_ACTIVATE,
    CONF_TRIGGER_ON_DEACTIVATE,
    CONF_SENSOR,
    CONF_SENSORS,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA_OFF,
    CONF_STATE_ENTITIES,
    CONF_DELAY,
    CONF_BLOCK_TIMEOUT,
    CONF_DISABLE_BLOCK,
    CONF_SENSOR_TYPE_DURATION,
    CONF_SENSOR_TYPE,
    CONF_SENSOR_RESETS_TIMER,
    CONF_NIGHT_MODE,
    CONF_NIGHT_MODE_ENTITY,
    CONF_NIGHT_MODE_ENTITY_STATES,
    CONF_NIGHT_MODE_ENTITIES,
    CONF_STATE_ATTRIBUTES_IGNORE,
    CONF_IGNORED_EVENT_SOURCES,
    CONF_GRACEFUL_OFF,
    CONF_IGNORE_STATE_CHANGES_UNTIL,
    CONF_FORCED_SENSORS,
    CONF_HOLD_SENSORS,
    CONF_HOLD_MAX_SECONDS,
    CONF_EVENT_SENSORS,
    CONF_LUX_ENTITY,
    CONF_LUX_THRESHOLD,
    CONF_LUX_BRIGHT_STATES,
    CONF_LUX_RECHECK_DELAY,
)


MODE_SCHEMA = vol.Schema(
    vol.All(
        {
            # Default must be None because we differentiate between set and
            # unset. Guarded by vol.Any: current voluptuous validates inserted
            # defaults, and Coerce(dict) on None always fails.
            vol.Optional(CONF_SERVICE_DATA, default=None): vol.Any(
                None, vol.Coerce(dict)
            ),
            vol.Optional(CONF_SERVICE_DATA_OFF, default=None): vol.Any(
                None, vol.Coerce(dict)
            ),
            vol.Optional(CONF_START_TIME): cv.string,
            vol.Optional(CONF_END_TIME): cv.string,
            vol.Optional(CONF_NIGHT_MODE_ENTITY): cv.entity_id,
            vol.Optional(CONF_NIGHT_MODE_ENTITY_STATES, default=[]): vol.All(
                cv.ensure_list, [cv.string]
            ),
            vol.Optional(CONF_NIGHT_MODE_ENTITIES, default=[]): cv.entity_ids,
            vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): cv.positive_int,
            vol.Optional(CONF_BLOCK_TIMEOUT): cv.positive_int,
        },
        # night detection needs a time window, a state entity, or both
        cv.has_at_least_one_key(CONF_NIGHT_MODE_ENTITY, CONF_START_TIME),
    )
)

ENTITY_SCHEMA = vol.Schema(
    cv.has_at_least_one_key(
        CONF_CONTROL_ENTITIES, CONF_CONTROL_ENTITY, CONF_TRIGGER_ON_ACTIVATE
    ),
    {
        # vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): cv.positive_int,
        vol.Optional(CONF_START_TIME): cv.string,
        vol.Optional(CONF_END_TIME): cv.string,
        vol.Optional(CONF_SENSOR_TYPE_DURATION, default=False): cv.boolean,
        vol.Optional(CONF_SENSOR_TYPE, default=SENSOR_TYPE_EVENT): vol.All(
            vol.Lower, vol.Any(SENSOR_TYPE_EVENT, SENSOR_TYPE_DURATION)
        ),
        vol.Optional(CONF_SENSOR_RESETS_TIMER, default=False): cv.boolean,
        vol.Optional(CONF_SENSOR, default=[]): cv.entity_ids,
        vol.Optional(CONF_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_CONTROL_ENTITIES, default=[]): cv.entity_ids,
        vol.Optional(CONF_CONTROL_ENTITY, default=[]): cv.entity_ids,
        vol.Optional(CONF_TRIGGER_ON_ACTIVATE, default=None): cv.entity_ids,
        vol.Optional(CONF_TRIGGER_ON_DEACTIVATE, default=None): cv.entity_ids,
        vol.Optional(CONF_STATE_ENTITIES, default=[]): cv.entity_ids,
        vol.Optional(CONF_BLOCK_TIMEOUT, default=None): cv.positive_int,
        vol.Optional(CONF_DISABLE_BLOCK, default=False): cv.boolean,
        vol.Optional(CONF_GRACEFUL_OFF, default=False): cv.boolean,
        vol.Optional(CONF_IGNORE_STATE_CHANGES_UNTIL, default=None): vol.Any(None, cv.positive_int),
        vol.Optional(CONF_NIGHT_MODE, default=None): MODE_SCHEMA,
        vol.Optional(CONF_STATE_ATTRIBUTES_IGNORE, default=[]): cv.ensure_list,
        vol.Optional(CONF_IGNORED_EVENT_SOURCES, default=[]): cv.ensure_list,
        vol.Optional(CONF_FORCED_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_HOLD_SENSORS, default=[]): cv.entity_ids,
        vol.Optional(CONF_HOLD_MAX_SECONDS, default=7200): vol.Any(
            cv.positive_int, None
        ),
        vol.Optional(CONF_EVENT_SENSORS, default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_LUX_ENTITY, default=None): vol.Any(None, cv.entity_id),
        vol.Optional(CONF_LUX_THRESHOLD, default=None): vol.Any(None, vol.Coerce(float)),
        vol.Optional(CONF_LUX_BRIGHT_STATES, default=[]): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_LUX_RECHECK_DELAY, default=1.0): vol.Any(None, vol.Coerce(float)),
        vol.Optional(CONF_SERVICE_DATA, default=None): vol.Coerce(
            dict
        ),
        vol.Optional(CONF_BEHAVIOURS, default=None): vol.Coerce(
            dict
        ),
        # Default must be none because we differentiate between set and unset
        vol.Optional(CONF_SERVICE_DATA_OFF, default=None): vol.Coerce(dict),
    },
    # extra=vol.ALLOW_EXTRA,
)

PLATFORM_SCHEMA = cv.schema_with_slug_keys(ENTITY_SCHEMA)
