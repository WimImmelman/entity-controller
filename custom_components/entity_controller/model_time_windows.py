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
"""start_time/end_time windows: parsing, sun events and the constrain/enable callbacks. Part of Model."""
import re
from datetime import datetime, time, timedelta

from transitions.core import MachineError

from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
from homeassistant.core import callback
from homeassistant.helpers import event
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt

from .const import (
    CONF_ON_ENTER_CONSTRAINED,
    CONF_ON_EXIT_CONSTRAINED,
)


class ModelTimeWindowsMixin:
    """start_time/end_time windows: parsing, sun events and the constrain/enable callbacks.

    Mixed into :class:`Model`; every method works on the shared model state.
    """

    @callback
    def constrain_entity(self, evt):
        """
            Event callback used on component setup if current time requires entity to start in constrained state.
        """
        self.constrain()

    @callback
    def end_time_callback(self, evt):
        """
            Called when `end_time` is reached, will change state to `constrained` and schedule `start_time` callback.
        """
        self.log.debug("end_time_callback :: Triggered")
        # must be reparsed to get up to date sunset/sunrise times
        x = self.parse_time(self.end_time)

        parsed_end = self.futurize(x)
        self.log.debug("end_time_callback :: New callback set to %s (future)", parsed_end)
        self.end_time_event_hook = event.async_track_point_in_time(
            self.hass, self.end_time_callback, parsed_end
        )
        self.update(end_time=parsed_end)

        # must be down here to make sure new callback is set regardless of exceptions
        self.do_transition_behaviour(CONF_ON_ENTER_CONSTRAINED)
        self.constrain()

    @callback
    def start_time_callback(self, evt):
        """
            Called when `start_time` is reached, will change state to `idle` and schedule `end_time` callback.
        """
        self.log.debug("start_time_callback :: Triggered")
        # must be reparsed to get up to date sunset/sunrise times
        #     self.log.debug("using debug day lengh %s", x)
        # else:
        x = self.parse_time(self.start_time)

        parsed_start = self.futurize(x)
        self.log.debug(
            "start_time_callback :: New callback set to %s (future)" % parsed_start
        )
        self.start_time_event_hook = event.async_track_point_in_time(
            self.hass, self.start_time_callback, parsed_start
        )

        self.update(start_time=parsed_start)

        self._apply_start_time_transition()
        self.do_transition_behaviour(CONF_ON_EXIT_CONSTRAINED)

    def _apply_start_time_transition(self):
        """Transition the machine when start_time is reached.

        Must never raise: an exception escaping a point-in-time callback makes
        HA re-fire it endlessly (error storm, 2026-07-08). States with no
        defined transition (e.g. overridden or active after a mid-window
        restart) are logged and left unchanged — the next sensor/override
        event resolves the controller normally.
        """
        try:
            # Override-at-start_time fix (2026-07-30): an override that switched
            # on while we were still constrained never reached the machine.
            # override_state_change()
            # only calls override() from active/active_timer/idle/blocked --
            # matching the `override` trigger, which has no `constrained`
            # source -- so the event is dropped on the floor.  Without this
            # branch the blocked() path below then strands the controller:
            # blocked ignores the override entirely, and when the block clears
            # (block_timer_expires, or enable() once the state entities go off)
            # the machine lands in idle = armed, with the override forgotten.
            # Observed 2026-07-29 on ec_202: the night block was armed 6s after
            # start_time (= sunset) while the controlled light happened to be
            # on, and the room then lit up on presence 7 times during the night.
            # enable() has a dedicated constrained -> overridden transition, so
            # routing through it honours the override without a new transition.
            # Scoped to `constrained` on purpose: start_time_callback also runs
            # while already idle/blocked/etc. (see the Phase 4 comment above),
            # and those states are reached only after override_state_change()
            # has had its chance, so they must keep the original behaviour.
            if (
                self.is_constrained()
                and len(self.overrideEntities) > 0
                and self.is_override_state_on()
            ):
                self.update(overridden_by=self._override_entity_state())
                self.enable()
                self.update(overridden_at=str(datetime.now()))
            elif self.is_state_entities_on() and self.is_block_enabled():
                self.blocked()
            else:
                # If the entity is on and block is disabled, we just transition from constrained
                # to idle and leave the entity on. (Don't start a timer to turn it off.)
                self.enable()
        except MachineError as err:
            self.log.warning(
                "start_time_callback :: no transition from state '%s' (%s); leaving state unchanged",
                self.state,
                err,
            )

    def now_is_between(self, start_time_str, end_time_str, name=None):
        start_time = (self._parse_time(start_time_str, name))["datetime"]
        end_time = (self._parse_time(end_time_str, name))["datetime"]
        now = dt.as_local(dt.now())
        start_date = now.replace(
            hour=start_time.hour, minute=start_time.minute, second=start_time.second
        )
        end_date = now.replace(
            hour=end_time.hour, minute=end_time.minute, second=end_time.second
        )
        if end_date < start_date:
            # Spans midnight
            if now < start_date and now < end_date:
                now = now + timedelta(days=1)
            end_date = end_date + timedelta(days=1)

        self.log.debug("now_is_between start time %s", start_date)
        self.log.debug("now_is_between end time %s", end_date)
        return start_date <= now <= end_date

    def parse_time(self, time_str, name=None, aware=False):
        if aware is True:
            return dt.as_local(self._parse_time(time_str, name)["datetime"]).time()
        else:
            return self.make_naive(
                (self._parse_time(time_str, name))["datetime"]
            ).time()

    def parse_datetime(self, time_str, name=None, aware=False):
        if aware is True:
            return dt.as_local(self._parse_time(time_str, name)["datetime"])
        else:
            return self.make_naive(
                dt.as_local(self._parse_time(time_str, name)["datetime"])
            )

    def _parse_time(self, time_str, name=None):
        parsed_time = None
        sun = None
        offset = 0
        parts = re.search(r"^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+):(\d+)$", str(time_str))
        if parts:
            this_time = datetime(
                int(parts.group(1)),
                int(parts.group(2)),
                int(parts.group(3)),
                int(parts.group(4)),
                int(parts.group(5)),
                int(parts.group(6)),
                0,
            )
            parsed_time = dt.as_local(this_time)
        else:
            parts = re.search(r"^(\d+):(\d+):(\d+)$", str(time_str))
            if parts:
                today = dt.as_local(dt.now())
                time_temp = time(
                    int(parts.group(1)), int(parts.group(2)), int(parts.group(3)), 0
                )
                parsed_time = today.replace(
                    hour=time_temp.hour,
                    minute=time_temp.minute,
                    second=time_temp.second,
                    microsecond=0,
                )

            else:
                if time_str == "sunrise":
                    parsed_time = self.sunrise(True)
                    sun = "sunrise"
                    offset = 0
                elif time_str == "sunset":
                    parsed_time = self.sunset(True)
                    sun = "sunset"
                    offset = 0
                else:
                    parts = re.search(
                        r"^sunrise\s*([+-])\s*(\d+):(\d+):(\d+)$", str(time_str)
                    )
                    if parts:

                        sun = "sunrise"
                        if parts.group(1) == "+":
                            td = timedelta(
                                hours=int(parts.group(2)),
                                minutes=int(parts.group(3)),
                                seconds=int(parts.group(4)),
                            )
                            offset = td.total_seconds()
                            parsed_time = self.sunrise(True) + td
                        else:
                            td = timedelta(
                                hours=int(parts.group(2)),
                                minutes=int(parts.group(3)),
                                seconds=int(parts.group(4)),
                            )
                            offset = td.total_seconds() * -1
                            parsed_time = self.sunrise(True) - td
                    else:
                        parts = re.search(
                            r"^sunset\s*([+-])\s*(\d+):(\d+):(\d+)$", str(time_str)
                        )
                        if parts:
                            sun = "sunset"
                            if parts.group(1) == "+":
                                td = timedelta(
                                    hours=int(parts.group(2)),
                                    minutes=int(parts.group(3)),
                                    seconds=int(parts.group(4)),
                                )
                                offset = td.total_seconds()
                                parsed_time = self.sunset(True) + td
                            else:
                                td = timedelta(
                                    hours=int(parts.group(2)),
                                    minutes=int(parts.group(3)),
                                    seconds=int(parts.group(4)),
                                )
                                offset = td.total_seconds() * -1
                                parsed_time = self.sunset(True) - td
        if parsed_time is None:
            if name is not None:
                raise ValueError("%s: invalid time string: %s", name, time_str)
            else:
                raise ValueError("invalid time string: %s", time_str)
        # self.log.debug("Result of parsing: %s",
        #                {"datetime": parsed_time, "sun": sun, "offset": offset})
        return {"datetime": parsed_time, "sun": sun, "offset": offset}

    def make_naive(self, dts):
        local = dt.as_local(dts)
        return datetime(
            local.year,
            local.month,
            local.day,
            local.hour,
            local.minute,
            local.second,
            local.microsecond,
        )

    def sunset(self, aware):
        t = get_astral_event_date(
            self.hass, SUN_EVENT_SUNSET, datetime.now().replace(hour=0)
        )
        if aware is True:
            return dt.as_local(t)
        else:
            return t

    def sunrise(self, aware):
        t = get_astral_event_date(
            self.hass, SUN_EVENT_SUNRISE, datetime.now().replace(hour=0)
        )
        if aware is True:
            return dt.as_local(t)
        else:
            return t

    def next_sunrise(self, offset=0):
        mod = offset
        while True:

            next_rising_dt = self.sunrise(True) + timedelta(mod)
            if next_rising_dt > dt.now():
                break

            mod += 1

        return next_rising_dt

    def next_sunset(self, offset=0):
        mod = offset
        while True:

            next_setting_dt = self.sunset(True) + timedelta(mod)
            if next_setting_dt > dt.now():
                break

            mod += 1

        return next_setting_dt

    def futurize(self, timet):
        """ Returns tomorrows time if time is in the past.
            Input time should be offset aware
         """

        # self.log.debug("-------------------- futurize ------------------------")
        # self.log.debug("Input (naive) %s ", timet)
        # Compare in HA-local wall time, NOT the process timezone: parse_time()
        # returns naive times in the HA-configured timezone, while
        # datetime.now()/date.today() follow the OS timezone. When the two
        # differ (e.g. host on UTC, HA on Europe/Prague), a just-fired callback
        # rescheduled itself to a time that is "future" in OS terms but already
        # past in HA-local terms — async_track_point_in_time then fires it
        # again immediately, in an endless loop (2026-07-09 incident: sunrise
        # end_time callbacks re-fired for exactly the UTC-offset window,
        # flooding MQTT with turn_off commands).
        now_local = dt.as_local(dt.now()).replace(tzinfo=None)
        today = now_local.date()
        try:
            t = datetime.combine(today, timet)
        except TypeError as e:
            t = timet
        if t.tzinfo is not None:
            t = dt.as_local(t).replace(tzinfo=None)
        x = now_local
        # self.log.debug("input time: " + str(t))

        # self.log.debug("current time: " + str(x))
        while t <= x:
            if t <= x:
                t = t + timedelta(1)  # tomorrow!
                # self.log.debug( "Time already happened. Returning tomorrow instead. " + str(t))
            else:
                self.log.debug("Time still happening today. " + str(t))
        # self.log.debug("output time: %s", t)
        # self.log.debug("-------------------- futurize (END) -------------------")
        return t

    def debug_time_wrapper(self, timet):
        """

            Injects some debugging capability. Number is parenthesis is the
            first delay used on initial component setup. (This creates a time
            difference between start and end time callbacks.)

            The other number after the + sign is the standard period.
            In real life, this would be 24 hours, for debugging you can make
            it a few seconds to see the app change from idle to constrained.

            start_time: now + 5 (3)
            end_time: now + 5 (6)

            This function is used to wrap CONF_START_TIME and CONF_END_TIME
            and should only be called by the corresponding class properties!

            See config_times.
        """
        s = timet
        parts = re.search(r"^now\s*([+-])\s*(\d+)\s*\(?(\d+)?\)?$", timet)
        if parts:
            sign = parts.group(1)
            first_delay = parts.group(3)
            delay = parts.group(2)
            now = dt.now()
            self.log.debug("now %s", now)
            delta = timedelta(seconds=int(delay))
            if first_delay is not None:
                delta = timedelta(seconds=int(first_delay))
            if sign == "-":
                now = now - delta
            else:
                now = now + delta

            # self.log.debug("now + delta %s", now)

            s = str(self.make_naive(now).time().replace(microsecond=0))

        # self.log.debug("config time s %s", s)
        return s

    def five_seconds_from_now(self, sun):
        """ Returns a timedelta that will result in a sunrise trigger in 5 seconds time"""

        return (
            dt.now()
            + timedelta(seconds=5)
            - get_astral_event_date(self.hass, sun, datetime.now())
        )

    def five_minutes_ago(self, sun):
        """ Returns a timedelta that will result in a sunrise trigger in 5 seconds time"""
        return (
            dt.now()
            - timedelta(minutes=5)
            - get_astral_event_date(self.hass, sun, datetime.now())
        )
