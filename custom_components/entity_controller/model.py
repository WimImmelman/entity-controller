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
"""Model: state, lifecycle and state-machine callbacks of one controller."""
import logging
import pprint
from datetime import datetime
from threading import Timer

from homeassistant.const import CONF_NAME
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import event
from homeassistant.helpers.storage import Store

from .model_events import ModelEventsMixin
from .model_timers import ModelTimersMixin
from .model_conditions import ModelConditionsMixin
from .model_config import ModelConfigMixin
from .model_persistence import ModelPersistenceMixin
from .model_time_windows import ModelTimeWindowsMixin
from .model_control import ModelControlMixin
from .const import (
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
    CONF_DELAY,
    STORAGE_VERSION,
)


# Configure delay before starting to monitor state change events
STARTUP_DELAY = 70


class Model(
    ModelEventsMixin,
    ModelTimersMixin,
    ModelConditionsMixin,
    ModelConfigMixin,
    ModelPersistenceMixin,
    ModelTimeWindowsMixin,
    ModelControlMixin,
):
    """ Represents the transitions state machine model """

    def __init__(self, hass, config, machine, entity, startup_delay=STARTUP_DELAY):
        self.ec_startup_time = datetime.now()

        self.hass = hass  # backwards reference to hass object
        self.entity = entity  # backwards reference to entity containing this model
        self._machine = machine  # kept so a reload can detach this model again
        # Cancel callables of every HA listener this model registered. A reload
        # calls them all in async_teardown(); without that the old controller
        # would keep reacting to sensors next to its replacement.
        self._unsubs = []
        self._torn_down = False
        self.start_time_event_hook = None
        self.end_time_event_hook = None

        self.config = (
            {}
        )  # new way of storing configuration (avoids having an attribue for each)
        self.config = config
        self.stateEntities = []
        self.controlEntities = []
        self.sensorEntities = []
        self.forcedSensorEntities = []
        self.eventSensorTypes = []
        self._event_sensor_cancel_callbacks = []
        self.triggerOnDeactivate = []
        self.triggerOnActivate = []
        self.timer_handle = None
        self._expiry_time = None   # kdy ma dobehnout timer (pro obnovu po restartu)
        self._pending_restore_expiry = None  # timer run-out carried over a restart
        self._restore_retries = 0            # kolikrat jsme cekali na nedostupnou entitu
        self._restoring = False              # True while _async_restore_state walks the machine to a saved state
        self._pending_restore_is_graceful = False  # the carried-over run-out is a graceful-off timer
        self.block_timer_handle = None
        # graceful_off support (see CONF_GRACEFUL_OFF)
        self.graceful_off = False
        self.graceful_candidate = False  # timer was kept alive on exit from active, awaiting destination state
        self.graceful_pending = False    # timer is running while in overridden/constrained
        self.sensor_type = None
        self.night_mode = None
        self.state_attributes_ignore = []
        self.backoff = False
        self.backoff_count = 0
        self.light_params_day = {}
        self.light_params_night = {}
        self.lightParams = {}
        self.name = None
        self.stay = False
        self.start = None
        self.end = None
        self.reset_count = None
        self.transition_behaviours = {}
        # logging.setFormatter(logging.Formatter(FORMAT))
        # logger name stays custom_components.entity_controller.<controller> as before the module split
        self.log = logging.getLogger(__package__ + "." + config.get(CONF_NAME))
        self.ignored_event_sources = []
        self.context = None
        self._store = None  # HA storage for state persistence
        self.luxEntity = None
        self.lux_threshold = None
        self.lux_bright_states = []
        self.lux_recheck_delay = 1.0
        self._lux_recheck_handle = None
        self._lux_recheck_entity = None
        self._lux_blocked = False
        self.night_mode_entity = None
        self.night_mode_entity_states = []
        self.nightControlEntities = []
        # the target set chosen at the most recent activation; turn-off must
        # use the same set even if day/night flipped while the timer ran
        self.activeControlEntities = []
        self._state_entities_explicit = False

        self.log.debug(
            "Initialising EntityController entity with this configuration: "
        )
        self.log.debug(
            pprint.pformat(config)
        )
        self.name = config.get(CONF_NAME, "Unnamed Entity Controller")
        self.ignored_event_sources = []

        machine.add_model(
            self
        )  # add here because machine generated methods are being used in methods below.

        self._track(event.async_call_later(self.hass, startup_delay, self.startup_delay_callback))

    def _track(self, unsub):
        """Remember a listener cancel callable so async_teardown() can call it."""
        if getattr(self, "_unsubs", None) is None:
            self._unsubs = []
        if callable(unsub):
            self._unsubs.append(unsub)
        return unsub

    async def async_teardown(self):
        """Stop this model for good: cancel listeners and timers, persist state.

        Called by the reload service before the controller is rebuilt from the
        new YAML. The state is saved first so the replacement restores it the
        same way it would after a Home Assistant restart. Timers are cancelled
        afterwards; the callbacks also check ``_torn_down`` because a
        ``threading.Timer`` that already fired cannot be cancelled any more.
        """
        self.log.debug("async_teardown :: Tearing down")
        self._torn_down = True
        if self._store is not None:
            try:
                await self._async_save_state()
            except Exception:  # noqa: BLE001 - never let a save failure block the teardown
                self.log.exception("async_teardown :: Failed to persist state")
        for unsub in getattr(self, "_unsubs", []):
            try:
                unsub()
            except Exception:  # noqa: BLE001
                self.log.exception("async_teardown :: Failed to cancel a listener")
        self._unsubs = []
        for cancel in self._event_sensor_cancel_callbacks:
            cancel()
        self._event_sensor_cancel_callbacks = []
        for hook_name in ("start_time_event_hook", "end_time_event_hook", "_lux_recheck_handle"):
            hook = getattr(self, hook_name, None)
            if callable(hook):
                hook()
            setattr(self, hook_name, None)
        self._cancel_timer()
        if self.block_timer_handle is not None and self.block_timer_handle.is_alive():
            self.block_timer_handle.cancel()
        machine = getattr(self, "_machine", None)
        if machine is not None:
            try:
                machine.remove_model(self)
            except ValueError:
                pass  # already detached

    async def startup_delay_callback(self, evt):
        if self._torn_down:
            return
        config = self.config
        self.config_static_strings(config)
        self.config_control_entities(config)
        self.config_state_entities(
            config
        )  # must come after config_control_entities (uses control entities if not set)
        self.config_sensor_entities(config)
        self.config_hold_sensor_entities(config)
        self.config_forced_sensor_entities(config)
        self.config_event_sensors(config)
        self.config_override_entities(config)
        self.config_lux_constraint(config)
        self.config_transition_behaviours(config)
        self.config_off_entities(config)
        self.config_on_entities(config)
        self.config_normal_mode(config)
        self.config_night_mode(
            config
        )  # must come after normal_mode (uses normal mode parameters if not set)
        self.config_state_attributes_ignore(config)
        self.config_times(config)
        self.config_other(config)
        self.prepare_service_data()

        # Phase 2: Set up state persistence store and register shutdown handler
        self._store = Store(self.hass, STORAGE_VERSION, self._storage_key())
        # Tracked so a torn-down controller does not overwrite its
        # replacement's persisted state when HA stops later.
        self._track(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_save_state))

        # Phase 2: Attempt to restore persisted state before the first transition
        restored = await self._async_restore_state()

        if not restored:
            if len(self.overrideEntities) > 0 and self.is_override_state_on():
                self.override()
                self.update(overridden_at=str(datetime.now()))
            else:
                self.start_monitoring()

    def update(self, wait=False, **kwargs):
        """ Called from different methods to report a state attribute change """
        # self.log.debug("Update called with {}".format(str(kwargs)))
        for k, v in kwargs.items():
            if v is not None:
                self.entity.set_attr(k, v)

        if wait == False:
            self.entity.do_update()

    def finalize(self):
        self.entity.do_update()

    def on_enter_idle(self):
        self.log.debug("Entering idle")
        self._cancel_graceful_timer()
        # Entering idle due to no events, set a new context with no parent
        self.set_context(None)
        if getattr(self, "_restoring", False):
            # Passing through idle on the way to a restored state: the light is
            # on for a reason, do not switch it off (see _async_restore_state).
            self.log.debug("on_enter_idle :: restoring, skipping the entry behaviour")
        else:
            self.do_transition_behaviour(CONF_ON_ENTER_IDLE)
        self.entity.reset_state()

    def on_exit_idle(self):
        self.log.debug("Exiting idle")
        self.do_transition_behaviour(CONF_ON_EXIT_IDLE)

    def on_enter_overridden(self):
        self.log.debug("Entering overridden")
        self._arm_graceful_timer()
        self.do_transition_behaviour(CONF_ON_ENTER_OVERRIDDEN)
        self._schedule_save_state()

    def on_exit_overridden(self):
        self.log.debug("Exiting overridden")
        self.do_transition_behaviour(CONF_ON_EXIT_OVERRIDDEN)
        self._schedule_save_state()

    def on_enter_active(self):
        self.log.debug("Entering active")
        self._cancel_graceful_timer()  # a graceful timer may still be running (e.g. overridden -> active)
        self.update(last_triggered_at=str(datetime.now()))
        self.backoff_count = 0
        self.prepare_service_data()

        self._start_timer()

        self.log.debug("on_enter_active :: light params before turning on: " + str(self.lightParams))
        self.do_transition_behaviour(CONF_ON_ENTER_ACTIVE)
        self.enter()

    def on_exit_active(self):
        self.log.debug("Exiting active")
        if self.graceful_off and self.timer_handle is not None and self.timer_handle.is_alive():
            # Keep the timer running for now. The destination state decides:
            # overridden/constrained arm it (graceful off), idle/blocked/active cancel it.
            self.log.debug("on_exit_active :: graceful_off - keeping timer alive")
            self.graceful_candidate = True
        else:
            self.log.debug("on_exit_active :: Turning off entities, cancelling timer")
            self._cancel_timer()  # cancel previous timer
        self.update(
            delay=self.lightParams.get(CONF_DELAY)
        )  # no need to update immediately
        self.do_transition_behaviour(CONF_ON_EXIT_ACTIVE)

    def on_enter_blocked(self):
        self.log.debug("Entering blocked")
        self._cancel_graceful_timer()
        self.update(blocked_at=datetime.now())
        self.update(blocked_by=self._state_entity_state())

        self.do_transition_behaviour(CONF_ON_ENTER_BLOCKED)
        if self.block_timeout:
            self.block_timer_handle = Timer(self.block_timeout, self.block_timer_expire)
            self.block_timer_handle.start()
            self.update(block_timeout=self.block_timeout)
        self._schedule_save_state()

    def on_exit_blocked(self):
        self.log.debug("Exiting blocked")
        self.do_transition_behaviour(CONF_ON_EXIT_BLOCKED)
        if self.block_timer_handle and self.block_timer_handle.is_alive():
            self.block_timer_handle.cancel()
        self._schedule_save_state()

    def on_enter_constrained(self):
        self.log.debug("Entering constrained")
        self._arm_graceful_timer()
        self.do_transition_behaviour(CONF_ON_ENTER_CONSTRAINED)

    def on_exit_constrained(self):
        self.log.debug("Exiting constrained")
        self.do_transition_behaviour(CONF_ON_EXIT_CONSTRAINED)
