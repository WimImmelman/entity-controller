[![License](https://img.shields.io/github/license/WimImmelman/entity-controller.svg?style=flat-square)](https://github.com/WimImmelman/entity-controller/blob/main/COPYING)

Maintained fork of [danobot/entity-controller](https://github.com/danobot/entity-controller) via [pluskal/entity-controller](https://github.com/pluskal/entity-controller).

Entity Controller (EC) is an implementation of "When This, Then That" using a finite state machine that ensures basic automations do not interfere with the rest of your home automation setup. This component encapsulates common automation scenarios into a neat package that can be configured easily and reused throughout your home. Traditional automations would need to be duplicated _for each instance_ in your config. The use cases for this component are endless because you can use any entity as input and outputs (there is no restriction to motion sensors and lights).

**Full Documentation:** [README](https://github.com/WimImmelman/entity-controller/blob/main/README.md)

## :clapper: Video Demo
Daniel Mason, the original author, created the following video to give a high-level overview of all EC features, how they work and how you can configure them for your use cases.
[Link](https://youtu.be/HJQrA6sFlPs)

[![Video](images/video_thumbnail.png)](https://youtu.be/HJQrA6sFlPs)

## Basic Configuration
The controller needs `sensors` to monitor (such as motion detectors, binary switches, doors, weather, etc) as well as an entity to control (such as a light).

```yaml
entity_controller:
  motion_light:                               # serves as a name
    sensor: binary_sensor.living_room_motion  # required, [sensors]
    entity: light.table_lamp                  # required, [entity,entities]
    delay: 300                                # optional, overwrites default delay of 180s
```

## What's new in this fork

- **`graceful_off`** (v9.12.0) – A timer cut short by an override or `end_time` keeps running and still switches the light off when it expires, instead of leaving it on indefinitely. Survives HA restarts.
- From pluskal's fork (v9.8 to v9.11): **state persistence** with timer run-out across restarts, **`forced_sensors`**, **`event_sensors`**, **`hold_sensors`**, **lux constraint** (`lux_entity`/`lux_threshold`), **entity-driven night mode**, **`grace_period`**, and fixes for controllers getting stuck in `blocked` or looping at `start_time`/`end_time`.

See the [CHANGELOG](https://github.com/WimImmelman/entity-controller/blob/main/CHANGELOG.md) for details.

## Lineage
Original author Daniel Mason ([danobot](https://github.com/danobot)); 2026 features by [pluskal](https://github.com/pluskal/entity-controller). GPL-3.0.



