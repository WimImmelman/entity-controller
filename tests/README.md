# Tests

Two files, both driving the real `transitions` state machine of the component with
mocked Home Assistant objects, no running HA instance needed:

- `test_legacy_behaviors.py` – sensor flows, blocking, overrides, duration sensors,
  stay-on, constraints (the scenarios of the original AppDaemon-era suites).
- `test_new_features.py` – everything added in the forks: block-timer fixes,
  forced/event/hold sensors, state persistence, grace period, lux constraint,
  entity-driven night mode, graceful off.

## Setup

The component imports `homeassistant`, so it has to be installed next to the test
dependencies. Any Home Assistant release your Python supports will do.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install homeassistant -r requirements_test.txt
```

(On Python 3.10 the last supported release is `homeassistant==2023.7.3`.)

## Run

From the repository root:

```bash
python -m pytest tests/test_legacy_behaviors.py tests/test_new_features.py -q
```
