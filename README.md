[![License](https://img.shields.io/github/license/WimImmelman/entity-controller.svg?style=flat-square)](https://github.com/WimImmelman/entity-controller/blob/main/COPYING)
[![Release](https://img.shields.io/github/v/tag/WimImmelman/entity-controller?style=flat-square&label=release)](https://github.com/WimImmelman/entity-controller/tags)

This is a maintained fork of [danobot/entity-controller](https://github.com/danobot/entity-controller) by way of [pluskal/entity-controller](https://github.com/pluskal/entity-controller). See [Lineage](#lineage).


# :wave: Introduction
Entity Controller (EC) is an implementation of "When This, Then That for x amount of time" using a finite state machine that ensures basic automations do not interfere with the rest of your home automation setup. This component encapsulates common automation scenarios into a neat package that can be configured easily and reused throughout your home. Traditional automations would need to be duplicated _for each instance_ in your config. The use cases for this component are endless because you can use any entity as input and outputs (there is no restriction to motion sensors and lights).

All options are documented in the [Configuration Reference](#configuration-reference) below.

## Installation
Add `https://github.com/WimImmelman/entity-controller` to HACS as a custom repository (type *Integration*) and install *Entity Controller* from it. Once installed, add the the following to your `configuration.yaml`, replacing the values for `sensor` and `entity` with one of your own. Reboot your Home Assistant server and you should have a motion controlled light that turns off after 5 seconds.
```
motion_light:
  sensor: binary_sensor.living_room_motion
  entity: light.tv_led
  delay: 5
```

## Lineage
- **Daniel Mason ([danobot](https://github.com/danobot))** wrote Entity Controller and maintained it to v9.7.6 (2024).
- **[pluskal](https://github.com/pluskal/entity-controller)** added, in 2026, state persistence with timer run-out across restarts, forced/event/hold sensors, the lux constraint, entity-driven night mode, `grace_period`, and a series of state-machine fixes (v9.8.0 to v9.11.1).
- **This fork** continues from pluskal's v9.11.1 with `graceful_off` (v9.12.0), the `entity_controller.reload` service (v9.13.0), the global `switch.entity_controller` (v9.14.0), the bundled dashboard card (v9.15.0) and repository housekeeping.

Licensed under the GPL-3.0, as the original. See [COPYING](COPYING).

# Contributions
Issues and pull requests are welcome at [github.com/WimImmelman/entity-controller](https://github.com/WimImmelman/entity-controller). Please include the controller's YAML and the relevant `entity_controller.*` state history when reporting a behaviour problem.

---

# Configuration Reference

## Basic options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `sensor` / `sensors` | entity id(s) | — | Motion/binary sensor(s) that trigger activation |
| `entity` / `entities` | entity id(s) | — | Entities to control (lights, switches, …) |
| `delay` | seconds | 180 | How long to stay active after the last trigger |
| `sensor_type` | `event` / `duration` | `event` | `duration` sensors (PIR/occupancy that stay `on`) hold the timer while on; the light only goes off once every sensor is off. |
| `sensor_resets_timer` | boolean | `false` | With `duration` sensors: restart the timer when a sensor turns off, so the light stays on for the full `delay` after the last sensor drops. Without it the timer runs from activation and the light goes off the moment the last sensor drops once it has expired. |

## Forced Sensors (`forced_sensors`)

Sensors listed under `forced_sensors` bypass the `blocked`, `constrained`, and `overridden` states and **immediately activate** the controller regardless of its current state. This is useful for panic buttons, manual overrides, or priority scenes where the normal blocking logic should be ignored.

```yaml
entity_controller:
  living_room:
    sensor: binary_sensor.pir
    entity: light.ceiling
    forced_sensors:
      - binary_sensor.panic_button   # always activates, even when overridden
```

The `forced_sensors` list accepts any Home Assistant entity id whose state changes to one of the sensor-on states (default: `on`, `playing`, `home`, `True`).

## HA Bus Event Sensors (`event_sensors`)

`event_sensors` accepts a list of **HA bus event type strings**. When any of those events fires on the event bus the controller treats it the same as a sensor turning on — transitioning from `idle`, `active_timer`, or `blocked` to `active`. Unlike `forced_sensors`, event sensors respect the `overridden` and `constrained` states.

```yaml
entity_controller:
  hallway:
    sensor: binary_sensor.door
    entity: light.hallway
    event_sensors:
      - my_custom_event          # fires when HA fires this bus event
      - zwave_js.value_updated   # or any other HA event type
```

Cancel callbacks are tracked automatically and cleaned up whenever the configuration is refreshed.

## Lux Constraint (`lux_entity` / `lux_threshold` / `lux_bright_states`)

Gate activation on measured room illuminance: motion turns the lights on **only while the room is dark enough**. Walking into an already-bright room no longer switches the lights on. Two sensor flavours are supported on the same `lux_entity`:

- **numeric sensors** (PIR-style lux): activation requires reading < `lux_threshold` (in whatever unit the sensor reports, typically lx);
- **string sensors** (radar/mmWave two-level `bright`/`dim`): activation is blocked while the state matches one of `lux_bright_states` — the light-level calibration lives in the sensor's own firmware.

```yaml
entity_controller:
  bedroom:                                  # numeric PIR lux
    sensor: binary_sensor.bedroom_occupancy
    entity: light.bedroom_led_strip
    lux_entity: sensor.bedroom_illuminance
    lux_threshold: 50                       # activate only below 50 lx

  living_room:                              # radar bright/dim
    sensor: binary_sensor.living_room_presence
    entity: light.living_room_wall
    lux_entity: sensor.living_room_presence_illumination
    lux_bright_states: ["bright"]
```

Both keys may be combined on one entity: numeric readings compare against the threshold, string states match the list.

The constraint deliberately gates **only** the `idle → active` transition that starts from a fully-off room. Everything else is unaffected:

- **timer resets** while active — the controlled light inflates the reading itself, so re-triggers must not be gated (otherwise the light would drop out mid-presence);
- the `blocked` bookkeeping paths (lights already on);
- `overrides`, `forced_sensors`, and the `activate` service (manual escape hatch).

A lux entity that is `unavailable`, missing, or otherwise unmatched (numeric on a bright-states-only config, or a string not in the list) **fails open**: activation is allowed and a warning is logged where appropriate. A dead sensor battery degrades to pre-lux behaviour instead of leaving the room dark. Setting `lux_entity` without any criterion — or a criterion without `lux_entity` — logs an error and disables the constraint.

When an activation is blocked, the EC entity records `lux_blocked_at` and `lux_at_last_block` attributes for diagnostics; `lux_entity` and `lux_threshold` are always shown as attributes when the constraint is active.

## Night-mode block timeout (`night_mode: block_timeout`)

**Problem:** `night_mode` gives a second `delay`, `service_data` and set of `entities` for part of the day, but the block timeout (how long EC leaves a hand-switched light alone before taking over again) was one value for the whole day. A bathroom light that should be left alone for 30 minutes in the morning rush but only 10 minutes for the rest of the day needed two controllers on the same light, with an awkward handover at the boundary.

**Solution:** `night_mode` accepts its own `block_timeout`. It is evaluated when the controller enters `blocked`, so it also applies to a block entered straight from `idle` (light switched on by hand, then motion). Omit it and night mode keeps using the controller-level `block_timeout`.

```yaml
entity_controller:
  ensuite:
    sensors:
      - binary_sensor.ensuite_motion_occupancy
    entities:
      - light.ensuite
    delay: 300            # rest of the day: 5 min timer, 10 min block
    block_timeout: 600
    night_mode:           # 05:00-08:00: 30 min timer, 30 min block
      start_time: '05:00:00'
      end_time: '08:00:00'
      delay: 1800
      block_timeout: 1800
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `night_mode.block_timeout` | seconds | controller `block_timeout` | Block timeout used while night mode is active. |

## Entity-Driven Night Mode (`night_mode: entity` / `entity_states` / `entities`)

`night_mode` historically switched to alternate service parameters (dimmer
brightness, shorter delay) inside a fixed time window. It can now also be
driven by the **state of an entity** — typically a house-mode
`input_select` — and can swap the **target entities** themselves:

```yaml
entity_controller:
  ec_bedroom:
    sensors:
      - binary_sensor.bedroom_motion
    entities:
      - light.bedroom_wardrobe       # day/evening target
    night_mode:
      entity: input_select.house_mode
      entity_states: [vecerka, noc]  # these states mean "night"
      entities:
        - light.bedroom_bed          # night target replaces the day set
      delay: 120
```

Semantics:

- `entity` + `entity_states` declare night whenever the entity's state matches
  one of the listed strings. `start_time`/`end_time` are now optional; if both
  a window and an entity are configured, **whichever says night wins**.
  At least one of `entity` / `start_time` must be present.
- `entities` (optional) replaces the controller's target set while night mode
  is active. The set is chosen **at activation time** and remembered: if the
  mode flips while the timer runs, the eventual turn-off still targets
  whatever was turned on — no orphaned lights.
- Night targets are watched like state entities (unless `state_entities` is
  set explicitly), so a manually-lit night light blocks activation as usual.
- A missing/unavailable mode entity **fails open to day behaviour** — a broken
  helper skips the night tweaks, it never dims the house.
- `mode` (day/night) and `active_entities` attributes expose the current
  choice for diagnostics.

## State Persistence

EC now persists the `overridden` and `blocked` states across Home Assistant restarts using the built-in HA storage layer. On startup the saved state is re-validated against the current live entity states before being applied, so stale persisted states are silently discarded. A restored `blocked` state leaves the (manually switched on) light on; a restored `active_timer` finishes its run-out and switches the light off when the timer would have expired.

No configuration is required — persistence is enabled automatically.

## Block Timer Fix

Prior to v9.8.0, when the block timer expired while all state entities were already off, the controller was left stuck in the `blocked` state (issue #310). This has been fixed: the state machine now correctly transitions `blocked → idle` when the block timer expires and all state entities are off.

## Grace Period (`grace_period`)

**Problem:** Cloud and gateway integrations — such as [Tahoma / Somfy](https://www.home-assistant.io/integrations/tahoma/) — update entity states asynchronously by polling the cloud. When EC calls `light.turn_on`, the integration sends the command upstream and only confirms the new state seconds later through its next poll cycle. That delayed state-change event is emitted with a fresh HA context that has no relationship to the original EC service call. Because EC's self-suppression mechanism (`is_ignored_context`) looks for its own context id prefix, it misses the late-arriving event, fires `control()`, finds the state entity on, and transitions `active_timer → blocked`.

**Solution:** Set `grace_period` to a value (in seconds) that covers the integration's worst-case round-trip latency. EC will then ignore all state-entity changes that arrive within that window after any service call, preventing false `blocked` transitions.

```yaml
entity_controller:
  room_108:
    sensor: binary_sensor.108_motion_hs_portal_occupancy
    entity:
      - light.108_f
      - light.108_i
      - light.led_1
      - light.led_3
    delay: 300
    grace_period: 10   # covers Tahoma's ~5–6 s cloud round-trip latency
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `grace_period` | integer (seconds) | `null` (disabled) | Duration after each service call during which state-entity changes are ignored. Set to a value slightly above your integration's worst-case latency. |

**When to use it:** Only needed for integrations where state-change events arrive with a context unrelated to the original EC service call (cloud integrations, gateway bridges, etc.). Standard local integrations — where HA propagates the service-call context through to the state-change event — are handled correctly by the existing context check and do not need this option.


## Dashboard card

The integration ships its own dashboard card and registers it as a dashboard resource on startup, so there is nothing extra to install. Add it from the card picker ("Entity Controller Card"), where a visual editor lets you pick the layout (one controller in detail, or a compact list), the controller(s), a name or title and the toggles. In list mode the controllers are edited in HA's standard entity list with drag-and-drop ordering, add and remove. Per-entity names in list mode are YAML only. The equivalent YAML:

```yaml
# one controller in detail
type: custom:entity-controller-card
entity: entity_controller.auto_kitchen_lights

# several controllers as a compact list, sorted by state
type: custom:entity-controller-card
title: Auto lights
entities:
  - entity_controller.auto_kitchen_lights
  - entity: entity_controller.auto_boundary_light
    name: Boundary
```

| Option | Default | Description |
|--------|---------|-------------|
| `entity` | — | Controller to show in detail. |
| `entities` | — | List of controllers (entity id, or `{entity, name}`) for the compact list. |
| `sort_by_state` | `true` | List mode: order rows active → blocked → overridden → idle → constrained. `false` keeps the configured order, which you can drag into shape in the visual editor. |
| `name` / `title` | friendly name | Card heading. Without one the card uses the controller's `friendly_name`, or a readable form of its YAML key (`auto_playroom_light` → "Playroom light"). |
| `show_entities` | `true` | Detail card: show the sensor, hold, forced, light and override entities with live on/off dots. |
| `show_buttons` | `true` | Detail card: Activate (idle, blocked) / Clear block (blocked) / Block (active_timer) buttons; they call the matching `entity_controller.*` services. The info icon in the header and every entity chip open the more-info dialog. |

What the card shows depends on the state: `active_timer` shows who triggered it and a live countdown to the switch-off; `blocked` shows what blocked it and when the block clears; `overridden` and `constrained` show the cause, when the window opens next and a pending `graceful_off` run-out; `idle` shows the last trigger and when the window closes. A banner appears on every card while `switch.entity_controller` is off.

The card is served from `/entity_controller_frontend/entity-controller-card.js` and added to Settings → Dashboards → Resources automatically when HA manages the resources (the default). If your dashboards are in YAML mode, add that URL as a JavaScript module resource yourself; the log says so at startup.

## Global switch (`switch.entity_controller`)

**Problem:** An "automatic lighting on/off" master control had to be built by hand: an `input_boolean`, a template sensor that inverts it (EC overrides are *on* when they override), and an `overrides:` line on every single controller. Forget the line on a new controller and it ignores the master switch.

**Solution:** The integration creates one switch entity itself, `switch.entity_controller`. It exists whatever the YAML says and needs no configuration.

| State | Effect |
|-------|--------|
| `on` (default) | Normal operation. |
| `off` | Every controller behaves as if an override entity were on: running controllers move to `overridden` (a `graceful_off` timer still switches its light off), constrained ones go to `overridden` instead of `idle` when their window opens, and controllers starting up land in `overridden`. `overridden_by` shows `switch.entity_controller`. |

Switching back on releases the controllers through the usual override rules: `idle` when the light is off, `active` when the light is on and a sensor still sees motion, and a YAML override entity that is still on keeps its controller overridden. The switch state survives restarts (it is restored from HA's last-state store) and is not touched by `entity_controller.reload`. The attribute `controllers` shows how many controllers exist.

```yaml
# Dashboard button: master control for all controllers
type: button
entity: switch.entity_controller
name: Auto lights
```

`overrides:` remains available for entity-driven overrides (a sleep-mode boolean, a presence sensor); the global switch replaces the emergency-stop use, not the option.

## Reload service (`entity_controller.reload`)

**Problem:** Entity Controller is configured in YAML, and every change to a controller (a new sensor, a different `delay`, a time window) needed a full Home Assistant restart before it took effect. Restarts disturb every other integration and make tuning a controller a slow loop.

**Solution:** The `entity_controller.reload` service re-reads the `entity_controller:` YAML and rebuilds the controllers in place. It works like the reload services of the core YAML integrations:

1. The YAML is validated first. If it is invalid, the error is logged and the running controllers are left untouched.
2. Every existing controller is torn down: all its listeners and timers are cancelled, its state is persisted, and its entity is removed.
3. The controllers are rebuilt from the new configuration. They start monitoring after about a second instead of the 70 s startup delay used at boot, and they restore their persisted state the same way they do after a Home Assistant restart.

Controllers that were removed from the YAML disappear, new ones appear, and renamed ones are treated as removed plus new. Because a reload goes through the same restore path as a restart, a controller that was in `active_timer` re-evaluates its light like it would after a restart (the light is switched off when the controller settles in `idle`); pick a quiet moment for reloads if that matters.

```yaml
# Developer tools -> Actions, or from an automation/script:
action: entity_controller.reload
```

Code changes to the component itself still need a Home Assistant restart; the reload only re-reads the configuration.

## Graceful Off (`graceful_off`)

**Problem:** A controller that is in `active_timer` can be pushed out of it by two things that are not the timer: an override entity turning on (`overridden`) or its `end_time` arriving (`constrained`). Leaving `active` cancels the off-timer, and the entry behaviours of `overridden` and `constrained` default to `ignore`, so the light EC switched on a few minutes earlier is never switched off. Typical case: indoor controllers overridden by an "auto lights enabled" boolean that turns off shortly after sunrise, and outdoor controllers whose window ends at sunrise, both cutting off a timer started by motion minutes before.

**Solution:** With `graceful_off: true` the running timer is kept when the controller moves into `overridden` or `constrained`. When it expires the control entities are switched off (only if they are still on) and the controller stays in its current state. Sensor triggers during that window are ignored, as they normally are in those states, so the light goes off exactly when it would have anyway. Moving into `idle`, `blocked` or `active` cancels the kept timer, so a light somebody re-toggled by hand is left alone. A pending run-out survives a Home Assistant restart through the state persistence layer.

```yaml
entity_controller:
  kitchen:
    sensors:
      - binary_sensor.kitchen_pir
    entities:
      - light.kitchen
    delay: 900
    overrides:
      - binary_sensor.auto_lights_blocked   # turns on after sunrise
    graceful_off: true                      # a timer cut off by the override still switches the light off
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `graceful_off` | boolean | `false` | Keep the off-timer running when the controller is pushed from `active_timer` into `overridden` or `constrained`, and switch the control entities off when it expires. |

Attributes while a run-out is pending: `graceful_off_expires_at`. After it fired: `graceful_off_at`.

**Compared with `behaviours`:** `on_enter_overridden: 'off'` / `on_enter_constrained: 'off'` switch the light off immediately and also fire when entering those states from `pending` (every HA restart during the override window) or from `blocked` (a light switched on by hand). `on_exit_active: 'off'` is the zero-maintenance alternative if you prefer an immediate off over letting the timer run out.
