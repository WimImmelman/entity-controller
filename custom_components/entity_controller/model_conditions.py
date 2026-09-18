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
"""Predicates used as transition conditions by the state machine. Part of Model."""
from datetime import datetime

from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    DATA_ENABLED,
    GLOBAL_SWITCH_ENTITY_ID,
    CONF_START_TIME,
    CONF_END_TIME,
    SENSOR_TYPE_DURATION,
    SENSOR_TYPE_EVENT,
    CONF_SENSOR_RESETS_TIMER,
)


class ModelConditionsMixin:
    """Predicates used as transition conditions by the state machine.

    Mixed into :class:`Model`; every method works on the shared model state.
    """

    def is_globally_enabled(self):
        """State of switch.entity_controller (True when the switch does not exist yet)."""
        data = getattr(self.hass, "data", None)
        try:
            enabled = data.get(DOMAIN, {}).get(DATA_ENABLED, True)
        except AttributeError:
            return True
        return enabled is not False

    def _override_entity_state(self):
        if not self.is_globally_enabled():
            self.log.debug("Override: %s is off", GLOBAL_SWITCH_ENTITY_ID)
            return GLOBAL_SWITCH_ENTITY_ID
        for e in self.overrideEntities:
            s = self.hass.states.get(e)
            try:
                state = s.state
            except AttributeError as ex:
                self.log.error(
                    "Potential configuration error: Override Entity ({}) does not exist (yet). Please check for spelling and typos. {}".format(
                        e, ex
                    )
                )
                
                continue

            if self.matches(state, self.OVERRIDE_ON_STATE):
                self.log.debug("Override entities are ON. [%s]", e)
                return e
        self.log.debug("Override entities are OFF.")
        return None

    def is_override_state_off(self):
        return self._override_entity_state() is None

    def is_within_grace_period(self):
        """Determines whether the last service call EC made was within the configured grace_period.

        This is a fallback for integrations (e.g. cloud/gateway integrations like Tahoma) that
        do not propagate the original HA context to their state-change events.  For those
        integrations the Context-API check in is_ignored_context() is insufficient because the
        delayed state update arrives with a fresh, unrelated context.  Setting grace_period to a
        value that covers the integration's worst-case latency prevents EC from entering the
        blocked state due to its own delayed state feedback.
        """
        if not self.grace_period:
            return False
        return datetime.now() < self.ignore_state_changes_until

    def is_override_state_on(self):
        return self._override_entity_state() is not None

    def _hold_sensor_is_stuck(self, entity, state_obj):
        """True when a hold sensor has been reporting ON for too long.

        A wedged presence sensor would otherwise keep the timer alive forever
        (expires_at: "pending sensor") and the light would never turn off. See
        CONF_HOLD_MAX_SECONDS for the incident this guards against.
        """
        cap = getattr(self, "hold_max_seconds", None)
        if not cap:
            return False
        try:
            held_for = (
                dt_util.utcnow() - state_obj.last_changed
            ).total_seconds()
        except (AttributeError, TypeError):
            return False
        if held_for < cap:
            return False
        self.log.warning(
            "_sensor_entity_state :: hold sensor %s has been ON for %.0f s "
            "(cap %s s) — treating it as stuck and ignoring it, otherwise the "
            "timer would never start",
            entity, held_for, cap,
        )
        return True

    def _sensor_entity_state(self):
        # Regular sensors first: they both trigger and hold, so they are always
        # honoured. Hold sensors only hold, which makes it safe to ignore one
        # that is obviously wedged (a stuck sensor in `sensors:` would just
        # re-trigger, so the same treatment there would only cause flicker).
        regular = list(self.sensorEntities)
        holds = list(getattr(self, "holdSensorEntities", []))
        for e in regular + holds:
            s = self.hass.states.get(e)
            try:
                state = s.state
            except AttributeError as ex:
                self.log.error(
                    "Potential configuration error: Sensor Entity ({}) does not exist (yet). Please check for spelling and typos. {}".format(
                        e, ex
                    )
                )
                
                continue

            if self.matches(state, self.SENSOR_ON_STATE):
                if e in holds and e not in regular and self._hold_sensor_is_stuck(e, s):
                    continue
                self.log.debug("Sensor entities are ON. [%s]", e)
                return e
        self.log.debug("Sensor entities are OFF.")
        return None

    def is_sensor_off(self):
        return self._sensor_entity_state() is None

    def is_sensor_on(self):
        return self._sensor_entity_state() is not None

    def _state_entity_state(self):
        for e in self.stateEntities:
            s = self.hass.states.get(e)
            self.log.info(s)
            try:
                state = s.state
            except AttributeError as ex:
                self.log.error(
                    "Potential configuration error: State Entity ({}) does not exist (yet). Please check for spelling and typos. {}".format(
                        e, ex
                    )
                )
                
                continue

            if self.matches(state, self.STATE_ON_STATE):
                self.log.debug("State entities are ON. [%s]", e)
                return e
        self.log.debug("State entities are OFF.")
        return None

    def is_state_entities_off(self):
        return self._state_entity_state() is None

    def is_state_entities_on(self):
        return self._state_entity_state() is not None

    def is_block_enabled(self):
        return self.disable_block is False

    def is_lux_constraint_satisfied(self):
        """Whether the illuminance constraint allows turning the lights on.

        Two sensor flavours are supported on the same ``lux_entity``:

        - numeric readings (PIR-style lux sensors) are compared against
          ``lux_threshold``: activation requires reading < threshold;
        - string states (radar-style two-level sensors reporting e.g.
          ``bright``/``dim``) block activation when the state matches one of
          ``lux_bright_states`` — the calibration lives in the sensor's own
          firmware.

        Anything else — no constraint configured, unavailable/unknown state,
        a numeric reading without a configured threshold, or a string not in
        ``lux_bright_states`` — allows activation. Failing open on a broken
        sensor is deliberate: a dead battery must degrade to pre-lux
        behaviour (lights turn on), never to a permanently dark room.
        """
        self._lux_blocked = False
        if self.luxEntity is None:
            return True
        s = self.hass.states.get(self.luxEntity)
        try:
            state = s.state
        except AttributeError:
            self.log.warning(
                "is_lux_constraint_satisfied :: Lux entity %s does not exist; failing open (activation allowed).",
                self.luxEntity,
            )
            return True

        try:
            value = float(state)
        except (TypeError, ValueError):
            value = None

        if value is not None:
            if self.lux_threshold is None:
                self.log.warning(
                    "is_lux_constraint_satisfied :: %s reports numeric %s but no lux_threshold is configured; failing open.",
                    self.luxEntity,
                    value,
                )
                return True
            if value >= self.lux_threshold:
                self.log.debug(
                    "is_lux_constraint_satisfied :: Activation blocked: %s reports %s lx >= threshold %s lx.",
                    self.luxEntity,
                    value,
                    self.lux_threshold,
                )
                self._lux_blocked = True
                self.update(lux_blocked_at=str(datetime.now()), lux_at_last_block=value)
                return False
            self.log.debug(
                "is_lux_constraint_satisfied :: %s reports %s lx < threshold %s lx; activation allowed.",
                self.luxEntity,
                value,
                self.lux_threshold,
            )
            return True

        if state in self.lux_bright_states:
            self.log.debug(
                "is_lux_constraint_satisfied :: Activation blocked: %s reports '%s' (in lux_bright_states).",
                self.luxEntity,
                state,
            )
            self._lux_blocked = True
            self.update(lux_blocked_at=str(datetime.now()), lux_at_last_block=state)
            return False
        self.log.debug(
            "is_lux_constraint_satisfied :: %s reports non-bright state '%s'; activation allowed.",
            self.luxEntity,
            state,
        )
        return True

    def will_stay_on(self):
        return self.stay

    def is_night(self):
        if self.night_mode is None:
            return False  # if night mode is undefined, it's never night :)

        self.log.debug("NIGHT MODE ENABLED: " + str(self.night_mode))

        # state-entity-driven night detection (e.g. input_select.house_mode);
        # an unavailable/missing entity fails open to DAY behaviour — a broken
        # helper must never dim the house, only skip the night tweaks
        if self.night_mode_entity is not None:
            s = self.hass.states.get(self.night_mode_entity)
            state = getattr(s, "state", None)
            if state is None:
                self.log.warning(
                    "is_night :: night_mode entity %s does not exist; treating as day.",
                    self.night_mode_entity,
                )
            elif state in self.night_mode_entity_states:
                self.log.debug(
                    "is_night :: %s is '%s' (in entity_states) -> night.",
                    self.night_mode_entity,
                    state,
                )
                return True

        # time-window detection (original behaviour); may coexist with the
        # entity above — whichever says "night" wins
        if self.night_mode.get(CONF_START_TIME) and self.night_mode.get(
            CONF_END_TIME
        ):
            return self.now_is_between(
                self.night_mode[CONF_START_TIME], self.night_mode[CONF_END_TIME]
            )
        return False

    def is_event_sensor(self):
        return self.sensor_type == SENSOR_TYPE_EVENT

    def is_duration_sensor(self):
        return self.sensor_type == SENSOR_TYPE_DURATION

    def is_timer_expired(self):
        expired = self.timer_handle.is_alive() == False
        return expired

    def does_sensor_reset_timer(self):
        return self.config[CONF_SENSOR_RESETS_TIMER]
