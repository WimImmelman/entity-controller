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
"""The transitions state machine shared by every controller."""
from transitions.extensions import HierarchicalMachine as Machine

from .const import (
    STATES,
)


def build_machine():
    """Build the state machine shared by every controller instance."""
    machine = Machine(
        states=STATES,
        initial="pending",
        # title=self.name+" State Diagram",
        # show_conditions=True
        # show_auto_transitions = True,
        finalize_event="finalize",
    )
    machine.add_transition(
        trigger="start_monitoring",
        source="pending",
        dest="idle",
    )

    machine.add_transition(trigger="constrain", source="*", dest="constrained")
    machine.add_transition(
        trigger="override",
        source=["pending", "idle", "active_timer", "blocked"],
        dest="overridden",
    )

    machine.add_transition(
        trigger="activate",
        source=["idle", "blocked"],
        dest="active",
    )
    machine.add_transition(
        trigger="activate", source="active_timer", dest=None, after="_reset_timer"
    )

    # Idle
    # machine.add_transition(trigger='sensor_off',           source='idle',              dest=None)
    # Lux constraint: gate ONLY this transition — the one that turns lights on
    # from a fully off room. The other sensor_on paths (active_timer resets,
    # idle → blocked, blocked re-entry) deal with lights that are already on,
    # where the reading is inflated by the controlled lights themselves.
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="active",
        conditions=["is_state_entities_off", "is_lux_constraint_satisfied"],
    )
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="active",
        conditions=["is_state_entities_on"],
        unless="is_block_enabled"
    )
    machine.add_transition(
        trigger="sensor_on",
        source="idle",
        dest="blocked",
        conditions=["is_state_entities_on", "is_block_enabled"],
    )
    machine.add_transition(trigger="enable", source="idle", dest=None, conditions=["is_state_entities_off"])

    # Blocked
    machine.add_transition(trigger="enable", source="blocked", dest="idle", conditions=["is_state_entities_off"])
    machine.add_transition(
        trigger="sensor_on", source="blocked", dest="blocked", conditions=["is_block_enabled"]
    )  # re-entering self-transition (on_enter callback executed.)

    # Overridden
    # machine.add_transition(trigger='enable', source='overridden', dest='idle')
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="idle",
        conditions=["is_state_entities_off"],
    )
    # If a device leaving overridden is on, we do not necessarily want to shut it off immediately. We simply want EC to stop controlling it. To do that, we'll move it to active, to simulate an EC trigger, and we'll see if it exits on its own. This works for event sensors, of course, and it will also work for duration sensors if the current state is on. A duration sensor that is off now will never expire on its own, though, so in that case, we'll assume the target is 'idle'.
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="active",
        conditions=["is_state_entities_on", "is_event_sensor"],
    )
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="active",
        conditions=["is_state_entities_on", "is_sensor_on"],
    )  # This could be duration && on, but it will also work for any event sensor, so it's simpler to just write 'on'
    machine.add_transition(
        trigger="enable",
        source="overridden",
        dest="idle",
        conditions=["is_state_entities_on", "is_duration_sensor", "is_sensor_off"],
    )

    machine.add_transition(
        trigger="enter", source="active", dest="active_timer", unless="will_stay_on"
    )
    machine.add_transition(
        trigger="enter",
        source="active",
        dest="active_stay_on",
        conditions="will_stay_on",
    )

    # Active Timer
    machine.add_transition(
        trigger="sensor_on", source="active_timer", dest=None, after="_reset_timer"
    )
    # machine.add_transition(trigger='sensor_off',           source='active_timer',      dest=None,              conditions=['is_event_sensor'])
    machine.add_transition(
        trigger="sensor_off_duration",
        source="active_timer",
        dest="idle",
        conditions=["is_timer_expired"],
    )
    # The following two transitions must be kept seperate because they have
    # special conditional logic that cannot be combined.
    machine.add_transition(
        trigger="timer_expires",
        source="active_timer",
        dest="idle",
        conditions=["is_event_sensor"],
    )
    machine.add_transition(
        trigger="timer_expires",
        source="active_timer",
        dest="idle",
        conditions=["is_duration_sensor", "is_sensor_off"],
    )
    # machine.add_transition(trigger='block_timer_expires', source='blocked', dest='idle')
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="active",
        conditions=["is_state_entities_on", "is_event_sensor"],
    )
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="active",
        conditions=["is_state_entities_on", "is_sensor_on"],
    )  # This could be duration && on, but it will also work for any event sensor, so it's simpler to just write 'on'
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="idle",
        conditions=["is_state_entities_on", "is_duration_sensor", "is_sensor_off"],
    )

    # Active Timer
    machine.add_transition(
        trigger="control",
        source="active_timer",
        dest="idle",
        conditions=["is_state_entities_off"]
    )
    machine.add_transition(trigger="control", source="active_timer",
                           dest="blocked", conditions=["is_state_entities_on", "is_block_enabled"])
    # When block is disabled, "control" will reset the active timer
    machine.add_transition(trigger="control", source="active_timer",
                           dest=None, after="_reset_timer", conditions=["is_state_entities_on"], unless="is_block_enabled")
    # Manually enable blocked state
    machine.add_transition(trigger="block_enable", source="active_timer",
                           dest="blocked", conditions=["is_state_entities_on", "is_block_enabled"])

    # machine.add_transition(trigger='sensor_off',           source='active_stay_on',    dest=None)
    # machine.add_transition(trigger="timer_expires", source="active_stay_on", dest=None)
    machine.add_transition(
        trigger="enable",
        source="active_stay_on",
        dest="idle",
        conditions=["is_state_entities_off"]
    )
    # Constrained
    machine.add_transition(
        trigger="enable",
        source="constrained",
        dest="idle",
        conditions=["is_override_state_off"],
    )
    machine.add_transition(
        trigger="enable",
        source="constrained",
        dest="overridden",
        conditions=["is_override_state_on"],
    )
    # Enter blocked state when component is enabled and entity is on
    machine.add_transition(trigger="blocked", source="constrained", dest="blocked", conditions=["is_block_enabled"])

    # Phase 4 fix: blocked must also be reachable from idle.
    # start_time_callback fires while the machine is already idle (e.g. after a
    # HA restart inside the active window, or an override toggled off before
    # start_time) and calls blocked() when state entities are on.  Without this
    # transition that raises MachineError, and HA keeps re-firing the failed
    # point-in-time callback, producing an error storm (observed 2026-07-08).
    # Mirrors the existing sensor_on: idle → blocked rule.
    machine.add_transition(trigger="blocked", source="idle", dest="blocked", conditions=["is_block_enabled"])

    # Phase 1 fix: block_timer_expires → idle when state entities are already off.
    # Without this transition the SM could be stuck in blocked when entities turned
    # off before the block timeout fired.
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="idle",
        conditions=["is_state_entities_off"],
    )

    # Phase 2 fix: catch-all for block_timer_expires → idle.
    # Covers the case where state entities are still reported as on (e.g. due to
    # slow cloud/gateway feedback from integrations like Overkiz/Tahoma) but the
    # trigger sensor has already turned off.  Without this transition the controller
    # would remain stuck in blocked indefinitely because none of the earlier
    # block_timer_expires conditions (which require is_sensor_on or
    # is_state_entities_off) would match.  This transition is unconditional so it
    # acts as a guaranteed fallback for every case not handled above.
    machine.add_transition(
        trigger="block_timer_expires",
        source="blocked",
        dest="idle",
    )

    # Phase 3: force_activate — triggered by forced sensors.
    # Bypasses blocked, constrained and overridden states entirely.
    machine.add_transition(
        trigger="force_activate",
        source=["idle", "blocked", "constrained", "overridden", "active_timer"],
        dest="active",
    )

    return machine
