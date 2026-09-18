# SPDX-License-Identifier: GPL-3.0-or-later
"""State-change callbacks: what a sensor, hold/forced sensor, override, state entity or bus event does to the state machine. Part of Model."""
import pprint
from datetime import datetime

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import callback
from homeassistant.helpers import event

from .const import (
    GLOBAL_SWITCH_ENTITY_ID,
    CONF_SENSOR_RESETS_TIMER,
)


class ModelEventsMixin:
    """State-change callbacks: what a sensor, hold/forced sensor, override, state entity or bus event does to the state machine.

    Mixed into :class:`Model`; every method works on the shared model state.
    """

    @callback
    def sensor_state_change(self, event):
        """ State change callback for sensor entities """
        entity = event.data["entity_id"]
        old = event.data["old_state"]
        new = event.data["new_state"]
        if new is None:
            # The entity is gone (platform reload / removed from the system),
            # so there is nothing to evaluate. Without this guard the log call
            # below already raises "'NoneType' object has no attribute ..."
            # (HA 2026.7 sends state_changed with new_state=None on removal).
            self.log.debug(
                "%s :: new_state is None (entity %s removed) — ignoring",
                "sensor_state_change", str(entity))
            return
        self.log.debug("sensor_state_change :: %10s Sensor state change to: %s" % ( pprint.pformat(entity), new.state))
        self.log.debug("sensor_state_change :: state: " +  pprint.pformat(self.state))

        try:
            if new.state == old.state:
                self.log.debug("sensor_state_change :: Ignore attribute only change")
                return
        except AttributeError:
            self.log.debug("sensor_state_change :: old NoneType")
            pass

        if self.matches(new.state, self.SENSOR_ON_STATE) and (
            self.is_idle() or self.is_active_timer() or self.is_blocked()
        ):
            self.set_context(new.context)
            self.update(last_triggered_by=entity)
            self.sensor_on()
            if self.is_idle() and getattr(self, "_lux_blocked", False):
                self._schedule_lux_recheck(entity)

        if (
            self.matches(new.state, self.SENSOR_OFF_STATE)
            and self.is_duration_sensor()
            and self.is_active_timer()
        ):
            self.set_context(new.context)
            self.update(last_triggered_by=entity, sensor_turned_off_at=datetime.now())

            # If configured, reset timer when duration sensor goes off
            if self.config[CONF_SENSOR_RESETS_TIMER]:
                self.log.debug("sensor_state_change :: CONF_SENSOR_RESETS_TIMER")
                self.update(
                    notes="The sensor turned off and reset the timeout. Timer started."
                )
                self._reset_timer()
            else:
                # We only care about sensor off state changes when the sensor is a duration sensor and we are in active_timer state.
                self.sensor_off_duration()
                self.log.debug("sensor_state_change :: CONF_SENSOR_RESETS_TIMER - normal")

    def _schedule_lux_recheck(self, entity):
        """Give a lux-blocked activation one second look at the reading.

        Integrations that publish occupancy and illuminance from a single
        device message (Zigbee2MQTT + Aqara PIR) deliver them as two HA state
        changes whose order is not stable across HA restarts. When the
        occupancy change lands first, the constraint compares against the
        *previous* illuminance report - typically taken while the lights were
        still on - and blocks a legitimate activation in a dark room
        (2026-09-04: ec_204 read 62 lx while the fresh report, 2 ms later,
        said 6 lx; ec_206 the same with 37 lx). One re-check after
        ``lux_recheck_delay`` seconds, with the sensor still on, picks up the
        late reading. A room that really is bright stays blocked;
        ``lux_recheck_delay: null`` disables the retry.
        """
        delay = getattr(self, "lux_recheck_delay", None)
        if not delay:
            return
        if getattr(self, "_lux_recheck_handle", None) is not None:
            return
        self.log.debug(
            "_schedule_lux_recheck :: activation by %s blocked on a possibly "
            "stale lux reading; re-checking in %.1f s",
            entity, delay,
        )
        self._lux_recheck_entity = entity
        self._lux_recheck_handle = event.async_call_later(
            self.hass, delay, self._lux_recheck
        )

    @callback
    def _lux_recheck(self, _now=None):
        """Retry the idle -> active transition once the lux entity caught up."""
        self._lux_recheck_handle = None
        if not self.is_idle():
            return
        triggered_by = getattr(self, "_lux_recheck_entity", None)
        for e in self.sensorEntities:
            s = self.hass.states.get(e)
            if s is not None and self.matches(s.state, self.SENSOR_ON_STATE):
                break
        else:
            self.log.debug(
                "_lux_recheck :: no sensor is on any more; nothing to retry")
            return
        self.log.debug(
            "_lux_recheck :: retrying activation, sensor %s is still on", e)
        self.update(
            last_triggered_by=triggered_by or e,
            notes="Lux re-check after a possibly stale reading",
        )
        self.sensor_on()

    @callback
    def hold_sensor_state_change(self, event):
        """Hold sensor: keeps the light on, but never switches it on."""
        entity = event.data["entity_id"]
        old = event.data["old_state"]
        new = event.data["new_state"]
        if new is None:
            return
        try:
            if old is not None and new.state == old.state:
                return  # jen zmena atributu
        except AttributeError:
            pass

        if self.matches(new.state, self.SENSOR_ON_STATE):
            # DELIBERATELY not calling sensor_on() — a hold sensor must never
            # switch the light on.
            # Kdyz uz bezi timer, chovame se jako keep-alive.
            if self.is_active_timer():
                self.set_context(new.context)
                self.update(last_triggered_by=f"hold:{entity}",
                            notes="Hold sensor is on, keeping the light on")
                self._cancel_timer()
                self.update(expires_at="pending sensor")
            else:
                self.log.debug(
                    "hold_sensor_state_change :: %s je ON, ale nezapinam (stav %s)",
                    entity, self.state)
            return

        if (
            self.matches(new.state, self.SENSOR_OFF_STATE)
            and self.is_duration_sensor()
            and self.is_active_timer()
        ):
            # Hold sensor went off — the timer only starts once nothing holds
            # it any more.
            if self.is_sensor_on():
                self.log.debug(
                    "hold_sensor_state_change :: %s is OFF, but another sensor still holds", entity)
                return
            self.set_context(new.context)
            self.update(last_triggered_by=f"hold:{entity}", sensor_turned_off_at=datetime.now(),
                        notes="Hold sensor turned off, timer started")
            self._reset_timer()

    @callback
    def override_state_change(self, event):
        """ State change callback for override entities """
        entity = event.data["entity_id"]
        old = event.data["old_state"]
        new = event.data["new_state"]
        if new is None:
            # The entity is gone (platform reload / removed from the system),
            # so there is nothing to evaluate. Without this guard the log call
            # below already raises "'NoneType' object has no attribute ..."
            # (HA 2026.7 sends state_changed with new_state=None on removal).
            self.log.debug(
                "%s :: new_state is None (entity %s removed) — ignoring",
                "override_state_change", str(entity))
            return
        self.log.debug("override_state_change :: Override state change entity=%s, old=%s, new=%s" % ( entity, old, new))
        if self.matches(new.state, self.OVERRIDE_ON_STATE) and (
            self.is_active()
            or self.is_active_timer()
            or self.is_idle()
            or self.is_blocked()
        ):
            self.set_context(new.context)
            self.update(overridden_by=entity)
            self.override()
            self.update(overridden_at=str(datetime.now()))
        if (
            self.matches(new.state, self.OVERRIDE_OFF_STATE)
            and self.is_override_state_off()
            and self.is_overridden()
        ):
            self.set_context(new.context)
            self.enable()

    def global_enabled_changed(self, enabled):
        """switch.entity_controller flipped; mirror override_state_change().

        OFF overrides a running controller (idle/active/blocked), exactly like an
        override entity turning on; constrained and pending controllers are left
        alone because their own start-time / startup evaluation consults
        is_override_state_on(). ON releases an overridden controller unless a
        YAML override entity still holds it.
        """
        if getattr(self, "_torn_down", False):
            return
        self.log.debug("global_enabled_changed :: enabled=%s, state=%s", enabled, self.state)
        if not enabled:
            if self.is_active() or self.is_active_timer() or self.is_idle() or self.is_blocked():
                self.set_context(None)
                self.update(overridden_by=GLOBAL_SWITCH_ENTITY_ID)
                self.override()
                self.update(overridden_at=str(datetime.now()))
            return
        if self.is_overridden() and self.is_override_state_off():
            self.set_context(None)
            self.enable()

    @callback
    def state_entity_state_change(self, event):
        entity = event.data["entity_id"]
        old = event.data["old_state"]
        new = event.data["new_state"]
        if new is None:
            # The entity is gone (platform reload / removed from the system),
            # so there is nothing to evaluate. Without this guard the log call
            # below already raises "'NoneType' object has no attribute ..."
            # (HA 2026.7 sends state_changed with new_state=None on removal).
            self.log.debug(
                "%s :: new_state is None (entity %s removed) — ignoring",
                "state_entity_state_change", str(entity))
            return
        """ State change callback for state entities. This can be called with either a state change or an attribute change. """
        self.log.debug(
            "state_entity_state_change :: [ Entity: %s, Context: %s ]\n\tOld state: %s\n\tNew State: %s",
            str(entity),
            str(new.context),
            str(old),
            str(new)
        )
        if self.is_ignored_context(new.context):
            self.log.debug("state_entity_state_change :: Ignoring this state change because it came from %s" % (new.context.id))
            return
        if self.is_within_grace_period():
            self.log.debug("state_entity_state_change :: Ignoring this state change because we are within the grace period (until %s)", self.ignore_state_changes_until)
            return

        # --- Resync after unavailability (2026-08-23) ---------------------
        # A controlled entity (relay/light) dropped off WiFi and came back.
        # That is NOT manual control, so it must not be evaluated as external
        # control (it used to push EC into 'blocked', after which the timer
        # never completed again).
        # It is also the only moment when the state can be genuinely stuck:
        # if EC wanted to turn the light off during the outage, that command
        # was dropped.
        #
        # Replaces the naive Turnoff_light_from_unavailable automation, which
        # turned lights off UNCONDITIONALLY. Measured over 7 days: 11 firings,
        # 10 of them wrong (91 %) — in 9 cases a sensor in the room was active,
        # and once EC turned the light back on after just 2 s (visible flash).
        # Hence: only turn off when EC is 'idle' AND no sensor reports motion.
        try:
            came_back = (
                old is not None
                and getattr(old, "state", None) == STATE_UNAVAILABLE
                and getattr(new, "state", None) != STATE_UNAVAILABLE
            )
        except AttributeError:
            came_back = False
        if came_back:
            is_on = self.matches(new.state, self.CONTROL_ON_STATE)
            self.log.info(
                "state_entity_state_change :: %s came back from unavailable as '%s' (EC state: %s) — resync",
                str(entity), str(new.state), self.state,
            )
            if self.is_active_timer() or self.is_active_stay_on():
                # EC wants the light on: if it came back off, turn it on.
                if not is_on:
                    self.log.info("resync :: timer is running but entity came back off — turning on")
                    self.turn_on_control_entities()
                return
            if is_on and self.is_idle():
                if self.is_sensor_on():
                    # Someone is in the room and the light is on. Leaving EC in
                    # 'idle' is NOT enough: the next sensor edge would call
                    # sensor_on() on an already-on entity, which deliberately
                    # lands in 'blocked' (block_timeout refreshed by every
                    # further edge), so EC would never manage the light again
                    # and a human has to turn it off.
                    # Measured 2026-08-23: ec_105_e went blocked at 20:44 after
                    # the relay came back on, was re-blocked by every kitchen PIR
                    # edge, and Jan had to switch 1NP off by hand at 21:34.
                    # force_activate() adopts the light instead: EC enters
                    # 'active', starts its timer and turns the light off after
                    # the delay once the room empties.
                    self.log.info("resync :: on and a sensor is active — adopting it (force_activate)")
                    self.force_activate()
                    return
                self.log.info("resync :: on, EC is idle and sensors are quiet — clearing stuck state")
                self.turn_off_control_entities()
            return
        # -----------------------------------------------------------------

        #  If the state changed, we definitely want to handle the transition. If only attributes changed, we'll check if the new attributes are significant (i.e., not being ignored).
        try:
            if not old or not new or old == 'off' or new == 'off':
                pass
            else:
                if old.state == new.state:  # Only attributes changed
                    # Build two dictionaries of attributes, excluding the ones we don't want to monitor
                    old_temp = {
                        key: old.attributes[key]
                        for key in old.attributes
                        if key not in self.state_attributes_ignore
                    }
                    new_temp = {
                        key: new.attributes[key]
                        for key in new.attributes
                        if key not in self.state_attributes_ignore
                    }
                    if old_temp == new_temp:
                        self.log.debug("state_entity_state_change :: insignificant attribute change - Ignore the state change altogether")
                        return
                    self.log.debug("state_entity_state_change :: A significant attribute changed and will be handled")
        except AttributeError as a:
            # Most likely one of the states, either new or old, is 'off', so there's no attributes dict attached to the state object.
            self.log.debug(
                "state_entity_state_change :: Most likely one of the states, either new or old, is 'off', so there's no attributes dict attached to the state object: "
                + str(a)
            )
        self.set_context(new.context)
        if self.is_active_timer():
            self.log.debug("state_entity_state_change :: We are in active timer and the state of observed state entities changed.")
            self.control()

        if self.is_blocked() or self.is_active_stay_on(): # if statement required to avoid MachineErrors, cleaner than adding transitions to all possible states.
            self.enable()

    @callback
    def forced_sensor_state_change(self, ev):
        """State change callback for forced sensor entities (Phase 3).

        Forced sensors bypass blocked, constrained, and overridden states and
        immediately activate the controller.
        """
        entity_id = ev.data["entity_id"]
        old = ev.data["old_state"]
        new = ev.data["new_state"]
        self.log.debug(
            "forced_sensor_state_change :: %s → %s (state=%s)",
            entity_id,
            new.state if new else None,
            self.state,
        )

        try:
            if new.state == old.state:
                self.log.debug("forced_sensor_state_change :: Ignore attribute-only change")
                return
        except AttributeError:
            pass

        if new and self.matches(new.state, self.SENSOR_ON_STATE):
            self.set_context(new.context)
            self.update(last_triggered_by=entity_id)
            self.log.debug(
                "forced_sensor_state_change :: Force-activating from state '%s'", self.state
            )
            self.force_activate()

    @callback
    def ha_event_sensor_callback(self, event_type, ev):
        """HA bus event callback for event-bus sensors (Phase 6).

        Subscribes to arbitrary HA bus events and triggers sensor_on when
        the configured event fires, regardless of any attached event data.
        """
        self.log.debug(
            "ha_event_sensor_callback :: Received HA bus event '%s' (state=%s)",
            event_type,
            self.state,
        )
        self.set_context(None)
        self.update(last_triggered_by=f"ha_event:{event_type}")
        if self.is_idle() or self.is_active_timer() or self.is_blocked():
            self.sensor_on()
