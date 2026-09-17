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
"""Off-timer, block timer and graceful-off timer handling. Part of Model."""
from datetime import datetime, timedelta
from threading import Timer

from .const import (
    DEFAULT_DELAY,
    CONF_DELAY,
)


class ModelTimersMixin:
    """Off-timer, block timer and graceful-off timer handling.

    Mixed into :class:`Model`; every method works on the shared model state.
    """

    def _start_timer(self):
        self.log.info("_start_timer :: Light params: " + str(self.lightParams))
        if self.backoff_count == 0:
            self.previous_delay = self.lightParams.get(CONF_DELAY, DEFAULT_DELAY)
        else:
            self.log.debug(
                "_start_timer :: Backoff: %s,  count: %s, delay%s, factor: %s",
                self.backoff,
                self.backoff_count,
                self.lightParams.get(CONF_DELAY, DEFAULT_DELAY),
                self.backoff_factor,
            )
            self.previous_delay = round(self.previous_delay * self.backoff_factor, 2)
            if self.previous_delay > self.backoff_max:
                self.log.debug("Max backoff reached. Will not increase further.")
                self.previous_delay = self.backoff_max
            self.update(delay=self.previous_delay)

        expiry_time = datetime.now() + timedelta(seconds=self.previous_delay)

        # not able to use async_call_later because no known way to check whether timer is active.
        # self.timer_handle = event.async_call_later(self.hass, self.previous_delay, self.timer_expire)
        self.timer_handle = Timer(self.previous_delay, self.timer_expire)
        self.timer_handle.start()
        self._expiry_time = expiry_time
        self.update(expires_at=expiry_time)

    def _cancel_timer(self):
        if self.timer_handle is not None and self.timer_handle.is_alive():
            self.timer_handle.cancel()

    def _arm_graceful_timer(self):
        """ Called on entering overridden/constrained. If the active timer was kept alive
            when leaving active_timer, let it run to completion so the control entities
            are still switched off after the configured delay. """
        if self.graceful_candidate:
            self.graceful_candidate = False
            if self.timer_handle is not None and self.timer_handle.is_alive():
                self.graceful_pending = True
                self.log.info("_arm_graceful_timer :: Keeping timer alive in %s; control entities will be turned off at %s",
                              self.state, self.entity.attributes.get("expires_at"))
                self.update(graceful_off_expires_at=self.entity.attributes.get("expires_at"))
                self._schedule_save_state()  # so the run-out survives an HA restart

    def _cancel_graceful_timer(self):
        """ Called on entering idle/blocked/active. Any timer kept alive for a graceful off
            is no longer wanted in these states. """
        if self.graceful_candidate or self.graceful_pending:
            self.log.debug("_cancel_graceful_timer :: Cancelling graceful off timer")
            self.graceful_candidate = False
            self.graceful_pending = False
            self._cancel_timer()
            self.entity.attributes.pop("graceful_off_expires_at", None)
            self._schedule_save_state()

    def _reset_timer(self):
        self.log.debug("_reset_timer :: Resetting timer: " + str(self.backoff))
        self._cancel_timer()
        self.update(reset_at=datetime.now())
        if self.backoff:
            self.backoff_count += 1
            self.update(backoff_count=self.backoff_count)
        self._start_timer()

        return True

    def timer_expire(self):
        if self._torn_down:
            return  # a reload replaced this controller while the timer thread was already running
        self.log.debug("timer_expire :: Timer expired")
        if self.graceful_pending:
            # Graceful off: we left active_timer for overridden/constrained but kept the timer.
            # Turn the control entities off now (no state transition, sensors are ignored).
            self.graceful_pending = False
            self.entity.attributes.pop("graceful_off_expires_at", None)
            if not (self.is_overridden() or self.is_constrained()):
                self.log.debug("timer_expire :: graceful timer expired but state is %s - ignoring", self.state)
                return
            if self.is_state_entities_on():
                self.log.info("timer_expire :: Graceful off - turning off control entities while %s", self.state)
                self.turn_off_control_entities()
            else:
                self.log.debug("timer_expire :: Graceful off - control entities already off")
            self.update(graceful_off_at=str(datetime.now()))
            return
        if self.is_duration_sensor() and self.is_sensor_on():  # Ignore timer expiry because duration sensor overwrites timer
            self.update(expires_at="pending sensor")
        else:
            self.log.debug("timer_expire :: Trigger timer_expires event")
            self.timer_expires()

    def block_timer_expire(self):
        if self._torn_down:
            return
        self.log.debug("block_timer_expire :: Blocked Timer expired")
        self.block_timer_expires()
