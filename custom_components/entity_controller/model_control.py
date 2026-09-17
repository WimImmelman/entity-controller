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
"""Turning the controlled entities on and off, service calls, contexts and transition behaviours. Part of Model."""
import asyncio
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional

import homeassistant.util.uuid as uuid_util
from homeassistant.core import Context

from .const import (
    DOMAIN_SHORT,
    CONF_TRANSITION_BEHAVIOUR_ON,
    CONF_TRANSITION_BEHAVIOUR_OFF,
    CONF_SERVICE_DATA,
    CONF_SERVICE_DATA_OFF,
    CONTEXT_ID_CHARACTER_LIMIT,
)


class ModelControlMixin:
    """Turning the controlled entities on and off, service calls, contexts and transition behaviours.

    Mixed into :class:`Model`; every method works on the shared model state.
    """

    def handleTriggerOnDeactivateEntities(self):
        """ Entities that are defined outside of control entities via the `triggerOnDetivate` key. """
        if len(self.triggerOnDeactivate) > 0:
            self.log.info("handleTriggerOnDeactivateEntities :: Triggering Deactivation entities (Yes! params passed along)")
            for e in self.triggerOnDeactivate:
                self.log.debug("Triggering with turn_on call: %s", e)
                if self.lightParams.get(CONF_SERVICE_DATA_OFF) is not None:
                    self.log.debug(
                        "Triggering with turn_on call %s with service parameters %s",
                        e,
                        self.lightParams.get(CONF_SERVICE_DATA_OFF),
                    )
                    self.call_service(e, "turn_on", **self.lightParams.get(CONF_SERVICE_DATA_OFF))
                else:
                    self.log.debug("Triggering with turn_on call %s (no parameters provided to pass to service call)", e)
                    self.call_service(e, "turn_on")

    def handleTriggerOnActivateEntities(self):
        """ Entities that are defined outside of control entities via the `triggerOnActivate` key. """
        if len(self.triggerOnActivate) > 0:
            self.log.info("handleTriggerOnActivateEntities :: Triggering Activation entities (Yes! params passed along)")
            for e in self.triggerOnActivate:
                # if light params are defined
                if self.lightParams.get(CONF_SERVICE_DATA) is not None:
                    self.log.debug(
                        "Triggering with turn_on call %s with service parameters %s",
                        e,
                        self.lightParams.get(CONF_SERVICE_DATA),
                    )
                    self.call_service(
                        e, "turn_on", **self.lightParams.get(CONF_SERVICE_DATA)
                    )
                else:
                    self.log.debug("Turning on %s (no parameters provided to pass to service call)", e)
                    self.call_service(e, "turn_on")

    def turn_on_control_entities(self):
        self.handleTriggerOnActivateEntities()

        for e in self.activeControlEntities or self.controlEntities:
            # if light params are defined
            if self.lightParams.get(CONF_SERVICE_DATA) is not None:
                self.log.debug(
                    "turn_on_control_entities :: Turning on %s with service parameters %s",
                    e,
                    self.lightParams.get(CONF_SERVICE_DATA),
                )
                self.call_service(
                    e, "turn_on", **self.lightParams.get(CONF_SERVICE_DATA)
                )
            else:
                self.log.debug(
                    "turn_on_control_entities :: Turning on %s (no parameters passed to service call)", e
                )
                self.call_service(e, "turn_on")

    def turn_off_control_entities(self):
        self.handleTriggerOnDeactivateEntities()
        for e in self.activeControlEntities or self.controlEntities:
            self.log.debug("turn_off_control_entities :: Turning off %s", e)

            if self.lightParams.get(CONF_SERVICE_DATA_OFF) is not None:
                self.call_service(
                    e, "turn_off", **self.lightParams.get(CONF_SERVICE_DATA_OFF)
                )
            else:
                self.call_service(e, "turn_off")

    def call_service(self, entity, service, **service_data):
        """ Helper for calling HA services with the correct parameters """
        self.log.debug("call_service :: Calling service " + service + " on " + entity)
        if self.grace_period:
            self.ignore_state_changes_until = datetime.now() + timedelta(seconds=self.grace_period)
            self.log.debug("call_service :: grace_period active, ignoring state changes until %s", self.ignore_state_changes_until)

        domain, e = entity.split(".")
        if service in ['turn_on','turn_off'] and domain in self.homeassistant_turn_on_domains:
            domain = "homeassistant"
            self.log.debug("call_service :: Actually calling service %s on %s via the %s domain because the entity domain requires it." % (service, entity, domain))
        params = {}
        if service_data is not None:
            params = service_data

        params["entity_id"] = entity
        asyncio.run_coroutine_threadsafe(
            self.hass.services.async_call(domain, service, service_data, context=self.context),
            self.hass.loop
        )
        self.update(service_data=service_data)

    def set_context(self, parent: Optional[Context] = None) -> None:
        """Set the context used when calling other services.

        The new ID is linked to the context (`parent`) of the triggering event
        and will be unique per trigger.
        """
        # Unique name per EC instance, but short enough to fit within id length
        name_hash = hashlib.sha1(self.name.encode("UTF-8")).hexdigest()[:6]
        self.log.debug("set_context :: name_hash: %s", name_hash)
        unique_id = uuid_util.random_uuid_hex()

        # Restrict id length to database field size
        context_id = f"{DOMAIN_SHORT}_{name_hash}_{unique_id}"[:CONTEXT_ID_CHARACTER_LIMIT]
        self.log.debug("set_context :: context_id: %s", context_id)
        self.context_id = context_id
        # parent_id only exists for a non-None parent
        parent_id = parent.id if parent else None
        self.context = Context(parent_id=parent_id, id=context_id)
        # Set the EC entity's context so the logbook can identify the source of
        # events that will be generated by this object.
        self.entity.async_set_context(self.context)

    def is_ignored_context(self, context: Context) -> bool:
        """Should the event with the given `context` be ignored?"""
        if any(re.match(pattern + r"\b", context.id) is not None
               for pattern in self.ignored_event_sources):
            # Matched an ignore_event_source regex pattern
            return True
        if context.id.startswith(f"{DOMAIN_SHORT}_"):
            # This is an EC-generated event
            return True
        return False

    def matches(self, value, list):
        """
            Checks whether a string is contained in a list (used for matching state strings)
        """
        try:
            index = list.index(value)
            return True
        except ValueError:
            return False

    def do_transition_behaviour(self, behaviour):
        """ Wrapper method for acting on transition behaviours such as at time of end constraint of state transitions from override state. """
        self.log.debug("%10s | Performing Transition Behaviour" % (behaviour))
        action = self.get_transition_behaviour(behaviour)
        if action:
            self.log.debug("%10s | Action - %s" % (behaviour, action))
            if action == CONF_TRANSITION_BEHAVIOUR_ON:
                self.log.debug("%10s | Performing Action - Turning on" % (behaviour))
                self.turn_on_control_entities()
            if action == CONF_TRANSITION_BEHAVIOUR_OFF:
                self.log.debug("%10s | Performing Action - Turning off" % (behaviour))
                self.turn_off_control_entities()
