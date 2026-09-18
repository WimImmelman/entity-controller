# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading the per-controller YAML into the model (config_* methods). Part of Model."""
import functools
import pprint
import re
from datetime import datetime
from typing import List

from homeassistant.helpers import event
from homeassistant.util import dt

from .const import (
    CONF_START_TIME,
    CONF_END_TIME,
    CONF_TRANSITION_BEHAVIOUR_ON,
    CONF_TRANSITION_BEHAVIOUR_OFF,
    CONF_TRANSITION_BEHAVIOUR_IGNORE,
    CONF_BEHAVIOURS,
    CONF_ON_ENTER_IDLE,
    CONF_ON_EXIT_IDLE,
    CONF_ON_ENTER_ACTIVE,
    CONF_ON_EXIT_ACTIVE,
    CONF_ON_ENTER_OVERRIDDEN,
    CONF_ON_EXIT_OVERRIDDEN,
    CONF_ON_ENTER_CONSTRAINED,
    CONF_ON_EXIT_CONSTRAINED,
    CONF_ON_ENTER_BLOCKED,
    CONF_ON_EXIT_BLOCKED,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
    MODE_DAY,
    MODE_NIGHT,
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


class ModelConfigMixin:
    """Reading the per-controller YAML into the model (config_* methods).

    Mixed into :class:`Model`; every method works on the shared model state.
    """

    def config_transition_behaviours(self, config):
        self.transition_behaviours = {
            CONF_ON_ENTER_IDLE: CONF_TRANSITION_BEHAVIOUR_OFF,          # By default turn off
            CONF_ON_EXIT_IDLE: CONF_TRANSITION_BEHAVIOUR_IGNORE,
            CONF_ON_ENTER_ACTIVE: CONF_TRANSITION_BEHAVIOUR_ON,         # By default turn on
            CONF_ON_EXIT_ACTIVE: CONF_TRANSITION_BEHAVIOUR_IGNORE,
            CONF_ON_ENTER_OVERRIDDEN: CONF_TRANSITION_BEHAVIOUR_IGNORE,
            CONF_ON_EXIT_OVERRIDDEN: CONF_TRANSITION_BEHAVIOUR_IGNORE,
            CONF_ON_ENTER_CONSTRAINED: CONF_TRANSITION_BEHAVIOUR_IGNORE,
            CONF_ON_EXIT_CONSTRAINED: CONF_TRANSITION_BEHAVIOUR_IGNORE,
            CONF_ON_ENTER_BLOCKED: CONF_TRANSITION_BEHAVIOUR_IGNORE,
            CONF_ON_EXIT_BLOCKED: CONF_TRANSITION_BEHAVIOUR_IGNORE,
        }

        if CONF_BEHAVIOURS in config:
            self.transition_behaviours = {**self.transition_behaviours, **config[CONF_BEHAVIOURS]}

        self.log.debug("config_transition_behaviours :: Transition Behaviours: " +  pprint.pformat(self.transition_behaviours))

    def config_control_entities(self, config):
        self.controlEntities = []

        self.add(self.controlEntities, config, CONF_CONTROL_ENTITY)
        self.add(self.controlEntities, config, CONF_CONTROL_ENTITIES)

        self.log.debug("Control Entities: " +  pprint.pformat(self.controlEntities))

    def config_state_entities(self, config):
        self.stateEntities = []
        self.add(
            self.stateEntities, config, CONF_STATE_ENTITIES
        )  # adding optimistically
        self._state_entities_explicit = len(self.stateEntities) > 0
        if len(self.stateEntities) > 0:  # now checking whether they actually exist
            self.log.info(
                "State Entities (explicitly defined - I hope you know what you are doing): " + str(self.stateEntities)
            )
            self._track(event.async_track_state_change_event(
                self.hass, self.stateEntities, self.state_entity_state_change
            ))

        if len(self.stateEntities) == 0:
            # If no state entities are defined, use control entites as state
            self.stateEntities = self.controlEntities.copy()
            self.log.debug(
                "Added Control Entities as state entities (default): " + str(self.stateEntities)
            )
            self._track(event.async_track_state_change_event(
                self.hass, self.stateEntities, self.state_entity_state_change
            ))

    def config_off_entities(self, config):

        self.triggerOnDeactivate = []
        self.add(self.triggerOnDeactivate, config, CONF_TRIGGER_ON_DEACTIVATE)
        if len(self.triggerOnDeactivate) > 0:
            self.log.info("Off Entities: " +  pprint.pformat(self.triggerOnDeactivate))

    def config_on_entities(self, config):
        self.triggerOnActivate = []
        self.add(self.triggerOnActivate, config, CONF_TRIGGER_ON_ACTIVATE)
        if len(self.triggerOnActivate) > 0:
            self.log.info("On Entities: " +  pprint.pformat(self.triggerOnActivate))

    def config_sensor_entities(self, config):
        self.sensorEntities = []
        self.add(self.sensorEntities, config, CONF_SENSOR)
        self.add(self.sensorEntities, config, CONF_SENSORS)

        if len(self.sensorEntities) == 0 and len(config.get(CONF_FORCED_SENSORS, [])) == 0 \
                and len(config.get(CONF_EVENT_SENSORS, [])) == 0:
            self.log.error(
                "No sensor entities defined. You must define at least one sensor entity."
            )

        self.log.debug("Sensor Entities: " +  pprint.pformat(self.sensorEntities))

        if self.sensorEntities:
            self._track(event.async_track_state_change_event(
                self.hass, self.sensorEntities, self.sensor_state_change
            ))

    def config_hold_sensor_entities(self, config):
        """Sensors that never switch the light on, but keep it on.

        Rationale: "trigger from PIR, hold from PIR + radar". A radar listed
        in `sensors:` would switch the light on by itself (and flicker it
        needlessly while flapping), so it gets its own category: it counts
        towards `_sensor_entity_state()` (thus holding the timer via
        is_sensor_on()), but its on-edge never triggers activation.
        """
        self.holdSensorEntities = []
        self.hold_max_seconds = config.get(CONF_HOLD_MAX_SECONDS, 7200)
        self.add(self.holdSensorEntities, config, CONF_HOLD_SENSORS)
        if self.holdSensorEntities:
            self.log.debug("Hold Sensor Entities: %s", pprint.pformat(self.holdSensorEntities))
            self._track(event.async_track_state_change_event(
                self.hass, self.holdSensorEntities, self.hold_sensor_state_change
            ))

    def config_forced_sensor_entities(self, config):
        """Phase 3: Configure forced sensors that bypass blocked/constrained/overridden.

        Forced sensors trigger ``force_activate`` instead of ``sensor_on``, so
        the controller transitions directly to the ``active`` state from any
        state (including ``blocked``, ``constrained``, and ``overridden``).
        """
        self.forcedSensorEntities = []
        self.add(self.forcedSensorEntities, config, CONF_FORCED_SENSORS)
        if self.forcedSensorEntities:
            self.log.debug("Forced Sensor Entities: %s", pprint.pformat(self.forcedSensorEntities))
            self._track(event.async_track_state_change_event(
                self.hass, self.forcedSensorEntities, self.forced_sensor_state_change
            ))

    def config_event_sensors(self, config):
        """Phase 6: Configure HA bus event sensors.

        Each entry in ``event_sensors`` is a HA bus event type string.  When
        that event fires the controller treats it the same way as a sensor
        turning on (transitions to active from idle/active_timer/blocked).
        """
        self.eventSensorTypes = []
        for cancel in self._event_sensor_cancel_callbacks:
            cancel()
        self._event_sensor_cancel_callbacks = []

        raw = config.get(CONF_EVENT_SENSORS, [])
        if not raw:
            return

        for event_type in raw:
            self.eventSensorTypes.append(event_type)
            self.log.debug("config_event_sensors :: Subscribing to HA bus event '%s'", event_type)
            cancel = self.hass.bus.async_listen(
                event_type,
                functools.partial(self.ha_event_sensor_callback, event_type),
            )
            self._event_sensor_cancel_callbacks.append(cancel)

    def config_static_strings(self, config):
        DEFAULT_ON = ["on", "playing", "home", "True"]
        DEFAULT_OFF = ["off", "idle", "paused", "away", "False"]
        self.CONTROL_ON_STATE = config.get("control_states_on", DEFAULT_ON)
        self.CONTROL_OFF_STATE = config.get("control_states_off", DEFAULT_OFF)
        self.SENSOR_ON_STATE = config.get("sensor_states_on", DEFAULT_ON)
        self.SENSOR_OFF_STATE = config.get("sensor_states_off", DEFAULT_OFF)
        self.OVERRIDE_ON_STATE = config.get("override_states_on", DEFAULT_ON)
        self.OVERRIDE_OFF_STATE = config.get("override_states_off", DEFAULT_OFF)
        self.STATE_ON_STATE = config.get("state_states_on", DEFAULT_ON)
        self.STATE_OFF_STATE = config.get("state_states_off", DEFAULT_OFF)

        on = config.get("state_strings_on", False)
        if on:
            self.CONTROL_ON_STATE.extend(on)
            self.CONTROL_ON_STATE.extend(on)
            self.SENSOR_ON_STATE.extend(on)
            self.OVERRIDE_ON_STATE.extend(on)
            self.STATE_ON_STATE.extend(on)

        off = config.get("state_strings_off", False)
        if off:
            self.CONTROL_OFF_STATE.extend(off)
            self.SENSOR_OFF_STATE.extend(off)
            self.OVERRIDE_OFF_STATE.extend(off)
            self.STATE_OFF_STATE.extend(off)

    def config_night_mode(self, config):
        """
            Configured night mode parameters. If no night_mode service
            parameters are given, the day mode parameters are used instead.
            If those do not exist, the
        """
        if "night_mode" in config:
            self.night_mode = config[CONF_NIGHT_MODE]
            night_mode = config[CONF_NIGHT_MODE]
            self.light_params_night[CONF_DELAY] = night_mode.get(
                CONF_DELAY, config.get(CONF_DELAY, DEFAULT_DELAY)
            )
            self.light_params_night[CONF_SERVICE_DATA] = night_mode.get(
                CONF_SERVICE_DATA, self.light_params_day.get(CONF_SERVICE_DATA)
            )
            self.light_params_night[CONF_SERVICE_DATA_OFF] = night_mode.get(
                CONF_SERVICE_DATA_OFF, self.light_params_day.get(CONF_SERVICE_DATA_OFF)
            )

            # Optional night-time block timeout; None means "same as the
            # controller-level block_timeout" (see effective_block_timeout()).
            self.night_block_timeout = night_mode.get(CONF_BLOCK_TIMEOUT)
            self.night_mode_entity = night_mode.get(CONF_NIGHT_MODE_ENTITY)
            self.night_mode_entity_states = night_mode.get(
                CONF_NIGHT_MODE_ENTITY_STATES, []
            )
            self.nightControlEntities = night_mode.get(CONF_NIGHT_MODE_ENTITIES, [])

            has_window = "start_time" in night_mode and "end_time" in night_mode
            if self.night_mode_entity is not None and not self.night_mode_entity_states:
                self.log.error(
                    "Night mode 'entity' requires 'entity_states' (list of states that mean night). Disabling night mode."
                )
                self.night_mode = None
                self.night_mode_entity = None
                self.nightControlEntities = []
                return
            if self.night_mode_entity is None and not has_window:
                self.log.error(
                    "Night mode requires either start_time+end_time or entity+entity_states! Disabling night mode."
                )
                self.night_mode = None
                self.nightControlEntities = []
                return

            if self.nightControlEntities:
                self.log.info(
                    "Night Control Entities: %s", str(self.nightControlEntities)
                )
                # observe night targets like any other state entity so a
                # manually-lit night light blocks activation and external
                # changes are noticed — but only when state entities were
                # defaulted from control entities, never when set explicitly
                if not self._state_entities_explicit:
                    new_watch = [
                        e for e in self.nightControlEntities
                        if e not in self.stateEntities
                    ]
                    if new_watch:
                        self.stateEntities.extend(new_watch)
                        self._track(event.async_track_state_change_event(
                            self.hass, new_watch, self.state_entity_state_change
                        ))
                        self.log.debug(
                            "Added night control entities as state entities: %s",
                            str(new_watch),
                        )

    def config_state_attributes_ignore(self, config):
        self.add(self.ignored_event_sources, config, CONF_IGNORED_EVENT_SOURCES)
        self.add(self.state_attributes_ignore, config, CONF_STATE_ATTRIBUTES_IGNORE)
        self.log.debug(
            "Ignoring events (state changes) caused by the following entities): %s",
            self.ignored_event_sources,
        )
        self.log.debug(
            "Ignoring state changes on the following attributes: %s",
            self.state_attributes_ignore,
        )

    def config_normal_mode(self, config):
        self.log.info("Service data set up")
        params = {}
        params[CONF_DELAY] = config.get(CONF_DELAY, DEFAULT_DELAY)
        params[CONF_SERVICE_DATA] = config.get(CONF_SERVICE_DATA, None)
        params[CONF_SERVICE_DATA_OFF] = config.get(CONF_SERVICE_DATA_OFF, None)
        self.light_params_day = params

    @property
    def start_time(self):
        """ Wrapper for _start_time_private """
        return self.debug_time_wrapper(self._start_time_private)

    @property
    def end_time(self):
        """ Wrapper for _end_time_private """
        return self.debug_time_wrapper(self._end_time_private)

    def config_times(self, config):
        self._start_time_private = None
        self._end_time_private = None
        if CONF_START_TIME in config and CONF_END_TIME in config:
            # FOR OPTIONAL DEBUGGING: for initial setup use the raw input value
            self._start_time_private = config.get(CONF_START_TIME)
            self._end_time_private = config.get(CONF_END_TIME)
            start_time_parsed = self.parse_time(self.start_time)
            self.log.debug("start_time_parsed: %s", start_time_parsed)

            self.log.debug("futurize outputs %s", self.futurize(start_time_parsed))

            parsed_start = self.parse_time(self.start_time, aware=False)
            parsed_end = self.parse_time(self.end_time, aware=False)
            # parsed_start = datetime.now() + timedelta(seconds=5)
            # parsed_end = datetime.now() + timedelta(seconds=10)
            # FOR OPTIONAL DEBUGGING: subsequently use normal delay
            sparts = re.search(r"^(now\s*[+-]\s*\d+)", config.get(CONF_START_TIME))
            if sparts is not None:
                self._start_time_private = sparts.group(1)
            eparts = re.search(r"^(now\s*[+-]\s*\d+)", config.get(CONF_END_TIME))
            if eparts is not None:
                self._end_time_private = eparts.group(1)

            self.update(start=self.start_time)
            self.update(end=self.end_time)

            parsed_start = self.futurize(parsed_start)
            parsed_end = self.futurize(parsed_end)
            self.log.debug("Setting FIRST START callback for %s", parsed_start)
            self.log.debug("Setting FIRST END callback for %s", parsed_end)
            # Publish the next window edges right away; until 9.15.0 the
            # start_time/end_time attributes only appeared after the first
            # callback had fired, so a controller that started outside its
            # window showed no opening time on the dashboard card.
            self.update(start_time=parsed_start, end_time=parsed_end)

            self.start_time_event_hook = event.async_track_point_in_time(
                self.hass, self.start_time_callback, parsed_start
            )
            self.end_time_event_hook = event.async_track_point_in_time(
                self.hass, self.end_time_callback, parsed_end
            )

            if not self.now_is_between(self.start_time, self.end_time):
                self.log.debug(
                    "Constrain period active. Scheduling transition to 'constrained'"
                )
                self._track(event.async_call_later(self.hass, 1, self.constrain_entity))

        self.log_config()

    def config_override_entities(self, config):
        self.overrideEntities = []
        self.add(self.overrideEntities, config, "override")
        self.add(self.overrideEntities, config, "overrides")

        if len(self.overrideEntities) > 0:
            self.log.debug("Override Entities: " +  pprint.pformat(self.overrideEntities))
            self._track(event.async_track_state_change_event(
                self.hass, self.overrideEntities, self.override_state_change
            ))

    def config_lux_constraint(self, config):
        """Configure the optional illuminance (lux) activation constraint.

        When ``lux_entity`` is set together with ``lux_threshold`` (numeric
        sensors) and/or ``lux_bright_states`` (string bright/dim sensors),
        sensor_on activation from ``idle`` (with the state entities off)
        requires the room to be dark enough. Everything else — timer resets,
        blocked handling, overrides, forced sensors, and the ``activate``
        service — is unaffected, so a running controller keeps managing
        lights whose own output pushes the reading past the threshold, and a
        manual activation always works.
        """
        self.luxEntity = config.get(CONF_LUX_ENTITY, None)
        self.lux_threshold = config.get(CONF_LUX_THRESHOLD, None)
        self.lux_bright_states = config.get(CONF_LUX_BRIGHT_STATES, []) or []
        # seconds before a lux-blocked activation is re-evaluated once (None/0
        # disables); see _schedule_lux_recheck for the ordering race it covers
        delay = config.get(CONF_LUX_RECHECK_DELAY, 1.0)
        try:
            self.lux_recheck_delay = float(delay) if delay else None
        except (TypeError, ValueError):
            self.log.error("lux_recheck_delay must be a number of seconds, got %r; using 1.0", delay)
            self.lux_recheck_delay = 1.0

        if self.luxEntity is not None and self.lux_threshold is None \
                and not self.lux_bright_states:
            self.log.error(
                "lux_entity is set but neither lux_threshold nor lux_bright_states is. "
                "The lux constraint is disabled."
            )
            self.luxEntity = None
        if self.luxEntity is None and (
            self.lux_threshold is not None or self.lux_bright_states
        ):
            self.log.error(
                "lux_threshold/lux_bright_states are set but lux_entity is not. "
                "The lux constraint is disabled."
            )
            self.lux_threshold = None
            self.lux_bright_states = []

        if self.luxEntity is not None:
            if self.lux_threshold is not None:
                self.lux_threshold = float(self.lux_threshold)
            self.log.debug(
                "Lux constraint: %s, threshold %s, bright states %s",
                self.luxEntity,
                self.lux_threshold,
                self.lux_bright_states,
            )
            self.update(
                lux_entity=self.luxEntity,
                lux_threshold=self.lux_threshold,
                lux_bright_states=self.lux_bright_states or None,
            )

    def config_other(self, config):
        self.ignore_state_changes_until = datetime.now()
        self.homeassistant_turn_on_domains = ['group'] # domains that do not have their own turn_on service and rely on homeassistant.turn_on

        self.config[CONF_SENSOR_RESETS_TIMER] = config.get(CONF_SENSOR_RESETS_TIMER)

        self.block_timeout = config.get(CONF_BLOCK_TIMEOUT, None)
        self.grace_period = config.get(CONF_IGNORE_STATE_CHANGES_UNTIL, None)
        self.disable_block = config.get(CONF_DISABLE_BLOCK, False)
        self.backoff = config.get("backoff", False)
        self.stay = config.get("stay_mode", False)
        self.graceful_off = config.get(CONF_GRACEFUL_OFF, False)
        if self.graceful_off:
            self.log.debug("config_other :: graceful_off enabled - timers survive override/constraint")
            self.update(graceful_off=True)

        if self.backoff:
            self.log.debug("config_other :: setting up backoff. Using delay as initial backoff value.")
            self.backoff_factor = config.get("backoff_factor", 1.1)
            self.backoff_max = config.get("backoff_max", 300)

        if config.get(CONF_SENSOR_TYPE_DURATION):
            self.sensor_type = SENSOR_TYPE_DURATION
        else:
            self.sensor_type = SENSOR_TYPE_EVENT

        if CONF_SENSOR_TYPE in config:
            self.sensor_type = config.get(CONF_SENSOR_TYPE)

        self.update(sensor_type=self.sensor_type)

    def effective_block_timeout(self):
        """block_timeout for a block entered right now.

        Evaluated when the controller enters ``blocked`` rather than at
        activation, because a block can also be entered straight from ``idle``
        (sensor on while the light is already on by hand), where no activation
        parameters were prepared. Night mode with its own ``block_timeout``
        wins while night is active; otherwise the controller-level value.
        """
        night_value = getattr(self, "night_block_timeout", None)
        if night_value is not None and self.night_mode is not None and self.is_night():
            return night_value
        return self.block_timeout

    def prepare_service_data(self):
        """
            Called when entering active state and on initial set up to set
            correct service parameters.
        """
        if self.is_night():
            self.log.debug(
                "Using NIGHT MODE parameters: " + str(self.light_params_night)
            )
            self.lightParams = self.light_params_night
            self.activeControlEntities = (
                self.nightControlEntities or self.controlEntities
            )
            self.update(mode=MODE_NIGHT)
        else:
            self.log.debug("Using DAY MODE parameters: " + str(self.light_params_day))
            self.lightParams = self.light_params_day
            self.activeControlEntities = self.controlEntities
            if self.night_mode is not None:
                self.update(mode=MODE_DAY)  # only show when night mode set up
        if self.nightControlEntities:
            self.update(active_entities=list(self.activeControlEntities))
        self.update(delay=self.lightParams.get(CONF_DELAY))

    def add(self, list, config, key=None):
        """ Adds e (which can be a string or list or config or Template) to the list
            if e is defined.
            If its a template, we have to create the Template object and register state listeners
            self.add(self.controlEntities, config, CONF_CONTROL_ENTITIES)

        """
        self.log.debug("add :: Adding config key `%s` to the config list", key)
        if config is None:
            self.log.debug("Tried to configure %s but supplied config was None" % (key))
            return False

        v = None
        if key is not None:
            if key in config:  # must be in separate if statement
                v = config[key]
        else:
            v = config

        if isinstance(v,str):
            self.log.debug("Found string value %s for key %s, now adding to existing list %s. (Type: %s)", v, key, list, type(v))
            list.append(v)
            return len(v) > 0
        elif isinstance(v, List):
            self.log.debug("Found list value %s for key %s, now adding to existing list %s. (Type: %s)", v, key, list, type(v))
            list.extend(v)
            return len(v) > 0
        elif v == None:
            self.log.debug(f'Config key {key} not provided by user. Skipping.')
            return False
        else:
            self.log.error(f'Cannot determine type of provided config value. Key: {key}, Type: {type(v)}, Value: {str(v)}')
            return False

    def log_config(self):
        self.log.debug("--------------------------------------------------")
        self.log.debug("       C O N F I G U R A T I O N   D U M P        ")
        self.log.debug("--------------------------------------------------")
        self.log.debug("Entity Controller       %s", self.name)
        self.log.debug("Sensor Entities         %s", str(self.sensorEntities))
        self.log.debug("Forced Sensor Entities: %s", str(self.forcedSensorEntities))
        self.log.debug("Event Bus Sensors:      %s", str(self.eventSensorTypes))
        self.log.debug("Control Entities:       %s", str(self.controlEntities))
        self.log.debug("State Entities:         %s", str(self.stateEntities))
        self.log.debug("Activate Trigger E.:    %s", str(self.triggerOnActivate))
        self.log.debug("Deactivate Trigger E.:  %s", str(self.triggerOnDeactivate))
        self.log.debug("Ignored state attrs:    %s", str(self.state_attributes_ignore))
        self.log.debug("Lux Entity:             %s", str(self.luxEntity))
        self.log.debug("Lux Threshold:          %s", str(self.lux_threshold))
        self.log.debug("Lux Bright States:      %s", str(self.lux_bright_states))
        self.log.debug("Night Mode Entity:      %s", str(self.night_mode_entity))
        self.log.debug("Night Mode States:      %s", str(self.night_mode_entity_states))
        self.log.debug("Night Control Entities: %s", str(self.nightControlEntities))
        self.log.debug("Light params:           %s", str(self.lightParams))
        self.log.debug("        -------        Time        -------        ")
        self.log.debug("Start time:             %s", self._start_time_private)
        self.log.debug("End time:               %s", self._end_time_private)
        self.log.debug("DT Now:                 %s", dt.now())
        self.log.debug("datetime Now:           %s", datetime.now())
        self.log.debug("Next Sunrise:           %s", self.next_sunrise(True))
        self.log.debug("Next Sunset:            %s", self.next_sunset(True))
        self.log.debug("        -------        Sun         -------        ")
        self.log.debug("Sunrise:                %s", self.sunrise(True))
        self.log.debug("Sunset:                 %s", self.sunset(True))
        self.log.debug("Sunset Diff (to now): %s", self.next_sunset() - dt.now())
        self.log.debug("Sunrise Diff(to now): %s", self.next_sunset() - dt.now())
        self.log.debug("Transition Behaviours: %s",  str(self.transition_behaviours))
        self.log.debug("--------------------------------------------------")

    def store_transition_behaviour(self, key, behaviour):
        """ manages transition_behaviour map """
        self.transition_behaviours[key] = behaviour

    def get_transition_behaviour(self, key):
        """ manages transition_behaviour map """
        if key in self.transition_behaviours:
            return self.transition_behaviours[key]
        else:
            return None
