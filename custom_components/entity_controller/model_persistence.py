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
"""Saving and restoring state across restarts and reloads (HA storage). Part of Model."""
import asyncio
import re
from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers import event

from .const import (
    STORAGE_KEY_PREFIX,
)


class ModelPersistenceMixin:
    """Saving and restoring state across restarts and reloads (HA storage).

    Mixed into :class:`Model`; every method works on the shared model state.
    """

    def _storage_key(self):
        """Return a unique storage key for this EC instance."""
        safe_name = re.sub(r'[^a-z0-9_]+', '_', self.name.lower()).strip('_')
        return f"{STORAGE_KEY_PREFIX}{safe_name}"

    def _schedule_save_state(self):
        """Schedule an async state save without blocking the caller.

        Must be thread-safe: ``on_enter_blocked`` arms a ``threading.Timer``
        whose ``block_timer_expire`` callback drives state transitions from a
        worker thread, so the ``on_exit_blocked`` -> ``_schedule_save_state``
        path is reached off the event loop. HA 2026.x raises ``RuntimeError``
        when ``hass.async_create_task`` is called from a non-event-loop thread,
        which aborts the transition and traps the controller in ``blocked``
        until HA restarts.
        """
        if self._store is not None:
            asyncio.run_coroutine_threadsafe(self._async_save_state(), self.hass.loop)

    async def _async_save_state(self, *_args):
        """Persist the current EC state to HA storage."""
        if self._store is None:
            return
        data = {
            "state": self.state,
            "saved_at": str(datetime.now()),
            # The timer expiry time is needed so the run-out can be finished
            # after a restart — otherwise EC ends up in 'idle' and nothing ever
            # turns the controlled light off (measured 2026-08-19: out of 24
            # restarts the light stayed on 21 times, with a 20-40 min tail
            # after the last motion).
            "expires_at": str(self._expiry_time) if self._expiry_time else None,
            # A graceful-off timer (see CONF_GRACEFUL_OFF) keeps running while the
            # controller sits in overridden/constrained. It has to be finished after
            # a restart as well, otherwise the light it was about to switch off stays on.
            "graceful_expires_at": str(self._expiry_time) if (self.graceful_pending and self._expiry_time) else None,
        }
        self.log.debug("_async_save_state :: Saving state: %s", data)
        await self._store.async_save(data)

    async def _async_restore_state(self):
        """Load persisted state from HA storage and restore if applicable.

        Returns True when the state was successfully restored so the caller
        can skip the normal startup evaluation.
        """
        if self._store is None:
            return False
        try:
            data = await self._store.async_load()
        except (OSError, ValueError) as exc:
            self.log.warning("_async_restore_state :: Failed to load persisted state: %s", exc)
            return False

        if not data:
            self.log.debug("_async_restore_state :: No persisted state found")
            return False

        saved_state = data.get("state")
        self.log.debug("_async_restore_state :: Restoring state '%s' (saved at %s)",
                       saved_state, data.get("saved_at"))

        graceful_expiry = self._parse_saved_expiry(data.get("graceful_expires_at"))
        if graceful_expiry is not None and saved_state in ("overridden", "constrained"):
            # A graceful-off timer was running when HA stopped. Finish it outside
            # the state machine, exactly like an active_timer run-out, whatever
            # state the normal startup evaluation below settles on.
            self._pending_restore_expiry = graceful_expiry
            self._pending_restore_is_graceful = True
            remaining = max((graceful_expiry - datetime.now()).total_seconds(), 0)
            self.log.info(
                "_async_restore_state :: Graceful-off timer from before restart has %.0f s left, scheduling turn-off",
                remaining)
            self.update(notes="Graceful-off timer from before restart: %.0f s left" % remaining)
            self._track(event.async_call_later(self.hass, max(remaining, 1), self._restore_timer_finish))

        if saved_state == "overridden":
            # Only restore overridden if an override entity is actually on, so
            # we do not get stuck in overridden when the override cleared while HA
            # was stopped.
            if len(self.overrideEntities) > 0 and self.is_override_state_on():
                self.override()
                self.update(overridden_at=str(datetime.now()), notes="Restored from storage")
                return True
            # Override is gone — fall through to normal startup evaluation
            return False

        if saved_state == "blocked":
            # Only restore blocked if the state entity is still on (otherwise the
            # entity was turned off while HA was down — go to idle instead).
            if self.is_state_entities_on() and self.is_block_enabled():
                # The route to blocked passes through idle, whose default entry
                # behaviour switches the control entities off. That is exactly
                # wrong here: the light is on because somebody switched it on by
                # hand, and 'blocked' means "leave it alone". Until 9.13.1 the
                # off command went out anyway, EC ignored the resulting off event
                # (its own context) and sat in blocked with the light off for the
                # rest of the night (boundary light, 2026-09-17 21:39).
                self._restoring = True
                try:
                    self.start_monitoring()
                    self.sensor_on()  # idle -> blocked via the normal transition
                finally:
                    self._restoring = False
                return True
            return False

        if saved_state == "active_timer":
            # The timer was running when HA shut down. Without restoring it EC
            # ends up in 'idle' and nothing turns the controlled light off —
            # only new motion completes the cycle. Measured 2026-08-19 in
            # production: out of 24 restarts the light stayed on 21 times, with
            # a 20-40 min tail after the last motion instead of the expected
            # ~5.5 min (90 s hold + 240 s delay).
            expiry = self._parse_saved_expiry(data.get("expires_at"))
            if expiry is None:
                return False
            if self._state_entities_unavailable():
                # The controlled entity has not come up yet — bulbs behind a
                # relay report later than EC starts (STARTUP_DELAY = 70 s).
                # This is EXACTLY the case where even the on_enter_idle command
                # is lost and the light then hangs on, so we must not give up:
                # defer the decision to _restore_timer_finish, which waits for
                # the entity.
                self._pending_restore_expiry = expiry
                self.log.info(
                    "_async_restore_state :: Controlled entity is not available yet, "
                    "deferring the run-out decision (expiry %s)", expiry)
                self._track(event.async_call_later(self.hass, 30, self._restore_timer_finish))
                return False
            if not self.is_state_entities_on():
                # The light was turned off meanwhile (manually or by another
                # automation) — there is nothing to finish.
                return False
            remaining = (expiry - datetime.now()).total_seconds()
            if remaining <= 1:
                # NOTE: start_monitoring() may only be called here, where we
                # return True. The other branch returns False and the caller
                # invokes it itself — otherwise it would register twice.
                self.start_monitoring()
                # The timer would have expired while HA was down -> finish the
                # turn-off.
                self.log.info(
                    "_async_restore_state :: Timer expired while HA was down (%s), turning control entities off",
                    expiry)
                self.turn_off_control_entities()
                self.update(notes="Timer expired while HA was down — entities turned off")
                return True
            # The timer has not run out yet. We do not try to re-arm it via
            # sensor_on() — on an already-on entity that deliberately leads to
            # 'blocked' (the same path the blocked-restore above uses). Instead
            # EC keeps running normally and we only finish what the timer did
            # not: turn off after the remaining time, unless EC has taken over
            # control meanwhile.
            self._pending_restore_expiry = expiry
            self.log.info(
                "_async_restore_state :: Timer from before restart has %.0f s left, scheduling turn-off",
                remaining)
            self.update(notes="Timer from before restart: %.0f s left" % remaining)
            self._track(event.async_call_later(self.hass, remaining, self._restore_timer_finish))
            return False

        # For all other states (idle, constrained, etc.) let the normal startup
        # evaluation run.
        return False

    @callback
    def _restore_timer_finish(self, _now=None):
        """Finish the turn-off that the timer running before the restart owed.

        Deliberately outside the state machine: when the controlled light is on
        at startup, EC ends up in 'blocked' (external control) or 'idle' and
        never turns it off by itself. If motion arrived meanwhile and EC took
        over control (active_timer / overridden), we do not interfere.
        """
        expiry = self._pending_restore_expiry
        if expiry is None or self._torn_down:
            return
        if self.is_active_timer() or (self.is_overridden() and not self._pending_restore_is_graceful):
            # A graceful-off run-out is expected to finish *inside* overridden, so in
            # that case only a fresh active_timer counts as EC having taken over.
            self._pending_restore_expiry = None
            self._pending_restore_is_graceful = False
            self.log.debug("_restore_timer_finish :: EC has already taken over control, not interfering")
            return
        # The key case: during EC initialisation (STARTUP_DELAY) bulbs behind a
        # relay are often still 'unavailable', because localtuya/Tasmota come up
        # later. EC does enter idle and send turn_off at that point, but the
        # command goes nowhere; when the light then shows up on, EC treats it as
        # external control and ends in 'blocked' -> it never turns off again.
        # That is why we wait for an unavailable entity here instead of giving up.
        if self._state_entities_unavailable():
            if self._restore_retries < 10:
                self._restore_retries += 1
                self.log.debug(
                    "_restore_timer_finish :: Controlled entity is unavailable, retrying in 30 s (%d/10)",
                    self._restore_retries)
                self._track(event.async_call_later(self.hass, 30, self._restore_timer_finish))
            else:
                self._pending_restore_expiry = None
                self._pending_restore_is_graceful = False
                self.log.warning(
                    "_restore_timer_finish :: Controlled entity stayed unavailable, giving up on the run-out")
            return
        if not self.is_state_entities_on():
            self._pending_restore_expiry = None
            self._pending_restore_is_graceful = False
            self.log.debug("_restore_timer_finish :: The light is no longer on, doing nothing")
            return
        # The entity is available and on. If the timer has not run out yet
        # (typically when we got here from the deferred decision after 30 s),
        # wait exactly the remaining time — otherwise we would turn off earlier
        # than the timer was due to expire.
        remaining = (expiry - datetime.now()).total_seconds()
        if remaining > 1:
            self.log.debug(
                "_restore_timer_finish :: Entity is back, timer has %.0f s left", remaining)
            self._track(event.async_call_later(self.hass, remaining, self._restore_timer_finish))
            return
        self._pending_restore_expiry = None
        self._pending_restore_is_graceful = False
        self.log.info("_restore_timer_finish :: Turning control entities off (timer from before restart)")
        self.turn_off_control_entities()
        self.update(notes="Turned off by timer carried over the restart")

    def _state_entities_unavailable(self):
        """True when at least one controlled/state entity is not available yet."""
        for e in self.stateEntities:
            st = self.hass.states.get(e)
            if st is None or st.state in ("unavailable", "unknown"):
                return True
        return False

    def _parse_saved_expiry(self, raw):
        """Prevede ulozeny cas vyprseni na datetime (naivni lokalni cas)."""
        if not raw or raw == "None":
            return None
        try:
            return datetime.fromisoformat(str(raw))
        except ValueError:
            self.log.warning("_parse_saved_expiry :: Nelze precist ulozeny expires_at: %s", raw)
            return None
