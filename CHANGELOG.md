# Change Log

All notable changes to this project will be documented in this file. See [standard-version](https://github.com/conventional-changelog/standard-version) for commit guidelines.

<a name="9.17.0"></a>
## [9.17.0](https://github.com/WimImmelman/entity-controller/compare/v9.16.0...v9.17.0) (2026-09-18)


### Features

* **`night_mode.block_timeout`** – Night mode can carry its own block timeout. `Model.effective_block_timeout()` picks the night value while night mode is active and the controller-level `block_timeout` otherwise; `on_enter_blocked` uses it, so it also covers a block entered straight from `idle`. Lets one controller replace the two-instance "morning / rest of day" workaround where only the block timeout differed.
* **Card list ordering** – The visual editor's list mode now uses HA's own `hui-entities-card-row-editor` (the element behind the entities card): drag rows to reorder, add and remove controllers, with the plain multi-select kept as a fallback if a future HA drops that element. New option `sort_by_state` (default `true`, the previous behaviour); `false` shows the rows in the configured order so the drag order is what you see. Per-entity names survive reordering.

### Tests

* `TestNightModeBlockTimeout` (8 tests): `effective_block_timeout()` prefers the night value at night, the day value by day, falls back when night mode has none or is not configured; entering `blocked` at night and by day arms the matching timer and attribute; `config_night_mode` reads the key; the schema accepts it and rejects negative values.

<a name="9.16.0"></a>
## [9.16.0](https://github.com/WimImmelman/entity-controller/compare/v9.15.0...v9.16.0) (2026-09-18)


### Features

* **Card visual editor** – `entity-controller-card` now provides `getConfigElement()`, so the dashboard's "Add card" dialog shows a form instead of the YAML editor: a layout dropdown (one controller in detail / compact list), an entity picker limited to `entity_controller.*` (multi-select in list mode), name or title, and the two show toggles. The editor renders HA's own `ha-form` and loads the editor bundle on demand through `loadCardHelpers()`. Per-entity names in list mode remain YAML only and survive edits in the form.
* **Readable fallback names** – A controller without a configured `friendly_name` reports its YAML key as the friendly name; the card now shows a humanised form instead (`auto_playroom_light` → "Playroom light").

### Bug Fixes

* **`start_time` / `end_time` attributes at startup** – `config_times()` now publishes the next window edges as soon as they are computed. They used to appear only after the first start- or end-time callback, so a controller that started outside its window showed "Outside the active window" on the card with no opening time until the next day.

### Tests

* `TestFrontend.test_config_times_publishes_window_edges`: the attributes are set at configuration time to the futurised start and end.

<a name="9.15.0"></a>
## [9.15.0](https://github.com/WimImmelman/entity-controller/compare/v9.14.0...v9.15.0) (2026-09-18)


### Features

* **Dashboard card** – `custom:entity-controller-card`, a plain web component (`www/entity-controller-card.js`, no build step) bundled with the integration. `frontend.py` serves `www/` at `/entity_controller_frontend/` (`async_register_static_paths`, falling back to `register_static_path` on older HA) and, once HA has started, adds or re-versions the card in the storage-mode dashboard resources (`?v=<version>` cache busting); in YAML resource mode it logs the URL to add by hand. Detail mode (`entity:`) shows the state chip, delay and window, per-state lines with live one-second countdowns (switch-off, block timeout, graceful run-out, next window opening), the sensor / hold / forced / light / override entities with on/off dots, and Activate (idle, blocked) / Clear block (blocked) / Block (active_timer) buttons, plus an info icon in the header that opens the more-info dialog. List mode (`entities:`) shows one compact row per controller sorted by state. A banner shows on every card while `switch.entity_controller` is off.
* **Entity list attributes** – Controllers now publish `sensor_entities`, `hold_sensor_entities`, `forced_sensor_entities`, `control_entities`, `state_entities` and `override_entities` as attributes after startup (the first four were listed in `PERSISTED_STATE_ATTRIBUTES` since the original project but never set).

### Tests

* `TestFrontend` (8 tests): resource URL carries the version; static path registered through the new or the old API; resource created when missing, re-versioned when the version differs, left alone when current; skipped with a warning in YAML resource mode or when lovelace is not loaded; resource registration deferred to `EVENT_HOMEASSISTANT_STARTED` when HA is still starting; `startup_delay_callback` publishes the entity list attributes.

<a name="9.14.0"></a>
## [9.14.0](https://github.com/WimImmelman/entity-controller/compare/v9.13.2...v9.14.0) (2026-09-18)


### Features

* **`switch.entity_controller`** – The integration now creates one global switch entity of its own (a `switch` platform loaded through `async_load_platform`, no YAML). OFF overrides every controller: `_override_entity_state()` reports `switch.entity_controller` as the active override, so startup, restore, the start-time evaluation and the `overrides:` machinery all treat it exactly like an override entity that is on. Running controllers are moved to `overridden` immediately through the new `Model.global_enabled_changed()`, which mirrors `override_state_change()`; constrained and pending controllers are left to their own evaluation. ON releases them through the existing `enable()` transitions, and a YAML override entity that is still on keeps its controller overridden. The switch extends `RestoreEntity`, so its state survives restarts, and `entity_controller.reload` does not touch it. The three `len(self.overrideEntities) > 0 and is_override_state_on()` guards lose the length check, which was redundant even before. Replaces the hand-built `input_boolean` + inverting template sensor + sixteen `overrides:` lines in the maintainer's config.

### Tests

* `TestGlobalSwitch` (17 tests): `is_globally_enabled()` reads `hass.data` and defaults to enabled when the flag or `hass.data` is missing; `_override_entity_state()` returns the switch id when disabled and still evaluates YAML entities when enabled; `global_enabled_changed(False)` overrides from `idle`, `active_timer` and `blocked` and leaves `constrained` and `pending` alone; `global_enabled_changed(True)` releases to `idle`, keeps a controller overridden while a YAML override is on, and is a no-op after teardown; startup with the switch off lands in `overridden` without any YAML override entity; restoring `overridden` with the switch off succeeds; `set_global_enabled()` stores the flag and notifies every model; the switch entity restores OFF/ON/missing last state, and `async_setup` loads the switch platform.

<a name="9.13.2"></a>
## [9.13.2](https://github.com/WimImmelman/entity-controller/compare/v9.13.1...v9.13.2) (2026-09-18)


### Bug Fixes

* **restoring `blocked` switched the light off** – When HA restarted while a controller was `blocked` (light switched on by hand), the persistence layer restored the state by walking `pending → idle → blocked`. Entering `idle` runs the default `on_enter_idle: off` behaviour, so EC switched the manually lit light off, then ignored the resulting off event because it carried EC's own context, and sat in `blocked` with the light off until the next constraint or override. Seen on the boundary light on 2026-09-17: restart at 21:38, light off at 21:39:14, doorbell motion at 23:11 ignored, dark until sunrise. `Model` now sets `_restoring` while `_async_restore_state` walks the machine and `on_enter_idle` skips the entry behaviour in that case. Restoring `active_timer` is unchanged: EC still settles in `idle` and finishes the run-out through `_restore_timer_finish`.

### Tests

* `TestStatePersistence`: restoring `blocked` keeps a manually lit light on and lands in `blocked`; falls through to normal startup when the light is off; `_restoring` is reset even when the transition raises; a regular timer expiry into `idle` still switches the light off.

<a name="9.13.1"></a>
## [9.13.1](https://github.com/WimImmelman/entity-controller/compare/v9.13.0...v9.13.1) (2026-09-17)


### Bug Fixes

* **module layout** – No behaviour change. `__init__.py` (2,994 lines) is split into per-concern modules: `schema.py`, `state_machine.py` (`build_machine()`), `entity.py` (`EntityController`), `model.py` (`Model`, assembled from mixins) and `model_events.py`, `model_timers.py`, `model_conditions.py`, `model_config.py`, `model_persistence.py`, `model_time_windows.py`, `model_control.py`. Every function body is unchanged (verified by syntax-tree comparison); per-controller logger names stay `custom_components.entity_controller.<name>`, so existing `logger:` settings keep working. The dead commented-out `adjust_times` helper is dropped.

### Tests

* The tests build the real state machine through `build_machine()` instead of a hand-copied transition table, so they can no longer drift from the component.

<a name="9.13.0"></a>
## [9.13.0](https://github.com/WimImmelman/entity-controller/compare/v9.12.2...v9.13.0) (2026-09-17)


### Features

* **`entity_controller.reload` service** – Re-read the `entity_controller:` YAML and rebuild every controller without restarting Home Assistant. The YAML is validated first (`async_integration_yaml_config`); invalid configuration is logged and the running controllers are kept, as the core YAML integrations do. Otherwise each controller is torn down and the set is rebuilt from the new configuration with a 1 s startup delay instead of the 70 s boot delay. To make teardown possible, `Model` now records the cancel callable of every listener it registers (`_track()`: sensor, hold, forced, override and state-entity trackers, night-mode state entities, the startup/constrain/restore `async_call_later` handles, the bus event-sensor subscriptions and the `EVENT_HOMEASSISTANT_STOP` save hook) and `Model.async_teardown()` persists the state, cancels the listeners, the start/end point-in-time hooks, the lux re-check, the off-timer and the block timer, and detaches the model from the shared state machine. `EntityController.async_teardown()` then removes the entity so the rebuilt controller can take over its entity id. Callbacks that can still fire after teardown (`timer_expire`, `block_timer_expire`, `_restore_timer_finish`, `startup_delay_callback`) return early for a torn-down model. The rebuilt controllers restore their persisted state through the existing persistence layer, so a reload behaves like a restart from the controllers' point of view. `async_setup` is split into `_build_machine()`, `_async_create_controllers()` and `async_reload()`; the module-level `devices` list moved into `hass.data[DOMAIN]`.

### Tests

* `TestReloadService` (17 tests): `_track` collects cancel callables; teardown cancels tracked listeners, event-sensor subscriptions, start/end hooks, lux re-check, off- and block timers and detaches the model; teardown persists state first and copes without a store and with a repeated call; timer, block-timer, restore and startup callbacks are no-ops after teardown; the listener-registering `config_*` methods and the HA-stop save hook are tracked; `EntityController.async_teardown` stops the model and removes the entity (also before an entity id exists); `async_reload` keeps the controllers when the YAML is invalid or the domain is missing, reports not-set-up, tears down and rebuilds with `RELOAD_STARTUP_DELAY` and the configured names, survives a failing teardown; `async_setup` registers `entity_controller.reload` and populates `hass.data`.

<a name="9.12.2"></a>
## [9.12.2](https://github.com/WimImmelman/entity-controller/compare/v9.12.1...v9.12.2) (2026-09-17)


### Bug Fixes

* **graceful_off attribute** – The `graceful_off` config echo disappeared from the entity's attributes as soon as the controller entered `idle` (i.e. right after startup), because `reset_state()` only keeps attributes listed in `PERSISTED_STATE_ATTRIBUTES`. It is now persisted like the other config keys, so the flag is visible in the states tool in every state. First observed after the 9.12.0 deployment: `graceful_off: True` showed only on controllers that were in `active_timer`.

### Tests

* `TestGracefulOff.test_graceful_off_attribute_survives_idle_reset`: `reset_state()` keeps `graceful_off` and `delay`, drops `graceful_off_at`, `graceful_off_expires_at` and `expires_at`.

<a name="9.12.1"></a>
## [9.12.1](https://github.com/WimImmelman/entity-controller/compare/v9.12.0...v9.12.1) (2026-09-17)


### Bug Fixes

* **fork identity** – `manifest.json` `documentation` and `codeowners` pointed at the original danobot repository and `issue_tracker` was missing, so HACS and the HA integration page sent users to the wrong place. Now `documentation`/`issue_tracker` point at this fork and `codeowners` is `@WimImmelman`; the non-standard `homeassistant` key is dropped from the manifest (HA ignores it; the minimum HA version lives in `hacs.json`, where HACS reads it). The module header, `VERSION` constant (stuck at 9.8.0 since the pluskal fork) and `package.json` are synced to the manifest version; README and `info.md` replace the original author's donation badges and blog links with a lineage section crediting Daniel Mason (original author) and pluskal (2026 fork features); the agent instructions use this repository's compare URL and default branch.
* **stale documentation** – Remove `diagram.puml` (hand-drawn 2020 PlantUML of the state machine, out of date since 9.8.0), the `images/` GIFs and diagrams that only the original author's external docs site referenced, and the demo-video section in README/`info.md`. Remove the `draw`, `image_prefix` and `image_path` config keys from `config_other()` (read into attributes nothing ever used) and the undocumented `day_length` debug key that let `futurize()` treat a day as N seconds. Drop the remaining links to the original author's documentation site and blog.

<a name="9.12.0"></a>
## [9.12.0](https://github.com/WimImmelman/entity-controller/compare/v9.11.1...v9.12.0) (2026-09-17)


### Features

* **graceful_off** – New per-controller option `graceful_off` (default `false`, stock behaviour). When a controller in `active_timer` is pushed into `overridden` (an override entity turns on) or `constrained` (`end_time` reached), EC cancels the off-timer in `on_exit_active` and the entry behaviours of both states default to `ignore`, so a light EC switched on stays on until somebody notices. With `graceful_off: true` the running timer is kept alive instead: when it expires the control entities are switched off (only if still on, without a state transition, attribute `graceful_off_at` stamped) and the light goes off exactly when it would have anyway. New sensor triggers during that window are ignored, as they already are in those states. Entering `idle`, `blocked` or `active` cancels the kept timer, so a light someone re-toggled by hand (`blocked`) is left alone and an override released back into `active` starts a fresh timer as before. Attribute `graceful_off_expires_at` shows the pending run-out. Motivating install: 18 `active_timer → constrained` cut-offs in 7 days, all outdoor controllers ending at sunrise plus a night lamp in no light group that then burned until 14:14; the household had been papering over it with "all lights off after sunrise" automations. Chosen over `behaviours: on_enter_overridden: 'off'`, which also fires from `pending` (every daytime HA restart would switch the room off) and from `blocked` (kills a manually switched-on light).
* **graceful_off survives restarts** – `_async_save_state` now also stores `graceful_expires_at` while a graceful run-out is pending, and the state is saved when the timer is armed or cancelled (this covers `constrained`, a state the persistence layer never saved on). On restore, a pending run-out saved in `overridden`/`constrained` is finished through `_restore_timer_finish`, which for this case no longer treats `overridden` as "EC has taken over"; a plain `active_timer` run-out keeps the old rule.

### Tests

* `TestGracefulOff` (17 tests): override and constraint mid-timer keep the timer and switch off on expiry (duration sensor still on is ignored), new triggers during the grace window are ignored, expiry is a no-op when the light was switched off by hand, `blocked` and manual-off cancel the kept timer, release back into `active` cancels it and restarts the timer, override from `idle` does not arm, flag off keeps stock behaviour, normal `active_timer` expiry unaffected, `config_other` reads the flag; persistence: `graceful_expires_at` saved only while pending, arming persists state, restore schedules the run-out for `overridden`/`constrained` only, `_restore_timer_finish` turns off inside `overridden` for a graceful run-out but still defers for a plain one.
* `TestStatePersistence.test_on_enter_overridden_schedules_save` updated to the thread-safe `run_coroutine_threadsafe` path introduced in 9.8.3 (it still asserted the pre-9.8.3 `hass.async_create_task`).

<a name="9.11.1"></a>
## [9.11.1](https://github.com/pluskal/entity-controller/compare/v9.11.0...v9.11.1) (2026-09-04)


### Bug Fixes

* **lux-constraint** – A lux-blocked activation from `idle` is re-evaluated once after `lux_recheck_delay` seconds (default 1.0; `null` disables) while the sensor is still on. Integrations that publish occupancy and illuminance from one device message (Zigbee2MQTT + Aqara PIR) deliver them as two HA state changes whose order is not stable across restarts; when occupancy lands first the gate compared against the *previous* illuminance report – taken while the lights were still on – and refused to light a dark room (ec_204: 62 lx stale vs 6 lx fresh; ec_206: 37 vs 0). A genuinely bright room stays blocked.

### Tests

* `TestLuxConstraint` +8: re-check scheduled once per block (no stacking), not scheduled on a normal activation, re-check activates on a fresh dark reading, stays idle when still bright, no-ops when the sensor already dropped or the controller left `idle`, disabled by config, and the `lux_bright_states` flavour schedules it too.

<a name="9.8.9"></a>
## [9.8.9](https://github.com/pluskal/entity-controller/compare/v9.8.8...v9.8.9) (2026-08-15)


### Features

* **night-mode** – `night_mode` can now be driven by the state of an entity (`entity` + `entity_states`, e.g. a house-mode `input_select`) instead of — or in addition to — the fixed `start_time`/`end_time` window; whichever source says "night" wins, and a missing mode entity fails open to day behaviour. A new `entities` sub-key swaps the controller's target set while night mode is active (e.g. bed LED instead of downlights); the set is chosen at activation and remembered, so a mode flip mid-timer never orphans a light. Night targets are observed as state entities unless `state_entities` is explicit.

### Bug Fixes

* **schema** – `MODE_SCHEMA`'s `service_data`/`service_data_off` defaults (`None`) crashed under current voluptuous, which validates inserted defaults (`Coerce(dict)` on `None` always fails); guarded with `vol.Any(None, ...)`. Latent only: HA never applies the component's `PLATFORM_SCHEMA`, but the schema is now usable in tests and any future validation.

### Tests

* Add `TestNightModeEntity` (22 tests): entity-driven night detection (match/non-match/missing entity/coexisting time window), activation-time target selection incl. mid-timer mode flips and empty-set fallbacks, `config_night_mode` validation permutations, state-entity extension rules, and MODE_SCHEMA validation.

<a name="9.8.8"></a>
## [9.8.8](https://github.com/pluskal/entity-controller/compare/v9.8.7...v9.8.8) (2026-08-15)


### Features

* **lux-constraint** – New `lux_bright_states` option extends the lux constraint to string-state light sensors (radar/mmWave presence sensors reporting `bright`/`dim`): activation from `idle` is blocked while the lux entity's state matches one of the listed strings, with the light-level calibration living in the sensor's own firmware. May be combined with `lux_threshold` on the same entity — numeric readings compare against the threshold, string states match the list. Numeric readings on a bright-states-only config fail open with a warning, as do `unavailable`/missing sensors. `lux_entity` now requires at least one of `lux_threshold`/`lux_bright_states` (config errors disable the constraint, as before).

### Tests

* Add `TestLuxBrightStates` (10 tests): bright blocks / dim allows / unavailable fails open, numeric-without-threshold fails open, combined-config numeric and string paths, diagnostic attributes, and config validation of all partial-config permutations.

<a name="9.8.7"></a>
## [9.8.7](https://github.com/pluskal/entity-controller/compare/v9.8.6...v9.8.7) (2026-08-15)


### Features

* **lux-constraint** – New `lux_entity` + `lux_threshold` options gate activation on measured room illuminance: `sensor_on` turns the lights on from `idle` only while the reading is below the threshold, so walking into an already-bright room no longer switches the lights on. Scoped deliberately to the single `idle → active` transition that starts from a fully-off room — timer resets while active, the `blocked` paths, overrides, `forced_sensors`, and the `activate` service are untouched, so the controlled light inflating the reading can never drop a running controller mid-presence, and manual activation always works. A missing, `unavailable`, or non-numeric lux entity fails open (activation allowed, warning logged): a dead sensor battery degrades to pre-lux behaviour instead of a permanently dark room. Setting only one of the two keys logs an error and disables the constraint. Blocked activations record `lux_blocked_at`/`lux_at_last_block` attributes; `lux_entity`/`lux_threshold` are surfaced as entity attributes while the constraint is active.

### Tests

* Add `TestLuxConstraint` (15 tests): activation allowed below / blocked at-and-above the threshold, inclusive boundary, no-config passthrough, fail-open on unavailable and missing lux entities, timer-reset and blocked paths not gated, `activate`/`force_activate` bypass, diagnostic attributes, partial-config validation, and machine-level condition placement.

<a name="9.8.6"></a>
## [9.8.6](https://github.com/pluskal/entity-controller/compare/v9.8.5...v9.8.6) (2026-07-30)


### Bug Fixes

* **state-machine** – Honour an override that was already on when `start_time` opened the window. `override_state_change()` only calls `override()` from `active`/`active_timer`/`idle`/`blocked`, mirroring the `override` trigger which has no `constrained` source — so an override switching on while the controller is still `constrained` is dropped on the floor. `_apply_start_time_transition()` then took the `blocked()` branch whenever the controlled entity happened to be on at `start_time`, and `blocked` never consults the override: once the block cleared (`block_timer_expires`, or `enable()` when the state entities went off) the machine landed in `idle` = armed, with the override forgotten. Observed on a bedroom controller whose night block is armed 6 s after `start_time` (= sunset): the room lit up on presence 7 times between 21:43 and 23:31 before it was switched off by hand. The new branch is scoped to `constrained` on purpose — `start_time_callback` also runs while already `idle` (see 9.8.4), and those states are reached only after `override_state_change()` has had its chance, so they keep the original behaviour. `overridden_by`/`overridden_at` are set to match the normal override path.

### Tests

* Add `TestStartTimeOverride` regression tests: override on with state entities on (the fix) and off, no override entities configured, overrides configured but off, the `idle` path staying on `blocked`, and the `overridden_by`/`overridden_at` bookkeeping.

<a name="9.8.5"></a>
## [9.8.5](https://github.com/pluskal/entity-controller/compare/v9.8.4...v9.8.5) (2026-07-09)


### Bug Fixes

* **`futurize()`** – Compare in HA-local wall time instead of the OS timezone. `parse_time()` returns naive times in the HA-configured timezone, but `futurize()` compared them against `datetime.now()`/`date.today()` in the process (OS) timezone. On a host running UTC with HA on Europe/Prague, every sunrise/sunset-relative `start_time`/`end_time` callback rescheduled itself to a wall time that was future in UTC terms but already past locally — `async_track_point_in_time` fired it again immediately, producing an endless enter/exit-constrained loop that flooded MQTT with turn_off commands (~230 msg/s) for exactly the UTC-offset window after each sun event. This, not the `MachineError` fixed in 9.8.4, was the actual driver of the 2026-07-08/09 incidents.

### Tests

* Add `TestFuturizeTimezone` regression tests: past/future local wall times, naive datetime input, and aware datetime normalization, with `dt.now()` pinned to a fixed HA-local instant.

<a name="9.8.4"></a>
## [9.8.4](https://github.com/pluskal/entity-controller/compare/v9.8.3...v9.8.4) (2026-07-08)


### Bug Fixes

* **state-machine** – Add `blocked` transition from `idle`. `start_time_callback` fires while the machine is already `idle` (HA restarted inside the active window, or an override toggled off while `constrained`) and calls `blocked()` when state entities are on; without the transition this raised `MachineError` and Home Assistant re-fired the failed point-in-time callback endlessly, flooding the log with tens of thousands of errors per hour (observed 2026-07-08). Mirrors the existing `sensor_on: idle → blocked` rule.
* **`start_time_callback`** – Extract the transition into `_apply_start_time_transition()` and guard it with `try/except MachineError`. States with no defined transition at start_time (e.g. `overridden`, `active`) now log a warning and keep their state instead of raising out of the callback.

### Tests

* Add `TestStartTimeTransition` regression tests: `idle → blocked`, `constrained → blocked`, `constrained → idle` (entities off) and `overridden` staying unchanged without raising.

<a name="9.8.3"></a>
## [9.8.3](https://github.com/pluskal/entity-controller/compare/v9.8.2...v9.8.3) (2026-05-15)


### Bug Fixes

* **thread-safe `_schedule_save_state`** – Replaced `hass.async_create_task(...)` with `asyncio.run_coroutine_threadsafe(coro, hass.loop)` so the helper is safe to call from worker threads. `on_enter_blocked` arms a `threading.Timer` whose `block_timer_expire` callback drives state transitions from a worker thread, so the `on_exit_blocked` → `_schedule_save_state` path is reached off the event loop. HA 2026.x raises `RuntimeError` when `hass.async_create_task` is called from a non-event-loop thread, which aborts the transition and traps the controller in `blocked` until HA restarts. The catch-all transition added in 9.8.2 cannot rescue this case because the failure is in the exit callback itself.


### Tests

* `test_schedule_save_is_thread_safe` — regression test that invokes `_schedule_save_state` from a `threading.Thread` and asserts no exception is raised and `hass.async_create_task` is not called.
* Updated `test_schedule_save_creates_task_when_store_set` and `test_on_enter_blocked_schedules_save` to assert against `asyncio.run_coroutine_threadsafe` instead of `hass.async_create_task`.


<a name="9.8.2"></a>
## [9.8.2](https://github.com/pluskal/entity-controller/compare/v9.8.1...v9.8.2) (2026-04-07)


### Bug Fixes

* **`block_timer_expires` catch-all** – Added an unconditional `blocked → idle` fallback transition for `block_timer_expires`. Previously, when the block timer fired while the trigger sensor was already off but state entities were still reporting "on" (e.g. delayed feedback from cloud/gateway integrations such as Overkiz/Tahoma), none of the existing `block_timer_expires` transitions matched and the controller remained stuck in `blocked` indefinitely past its `block_timeout`. The new catch-all fires for every case not handled by the earlier "go to `active`" transitions, guaranteeing the controller always exits `blocked` when the timer fires.


### Tests

* `test_block_timer_expires_to_idle_when_entities_on_but_sensor_off` — regression test for the missing catch-all scenario (Phase 2 fix).
* `test_block_timer_expires_catchall_transition_present_in_machine` — structural test asserting the unconditional transition exists in the state machine.



## [9.8.1](https://github.com/pluskal/entity-controller/compare/v9.8.0...v9.8.1) (2026-04-06)


### Bug Fixes

* **`grace_period`** – Re-introduced the `grace_period` configuration option to fix spurious `blocked` state transitions caused by cloud/gateway integrations (e.g. Tahoma/Somfy) that do not propagate Home Assistant's service-call context to their state-change events. When EC calls a service on such an integration the delayed state feedback arrives with a fresh, unrelated context; `is_ignored_context()` therefore does not suppress it, `control()` fires, and the controller enters `blocked`. Setting `grace_period` to a value that covers the integration's worst-case round-trip latency suppresses these false positives. The option is disabled by default (`null`) so no existing behaviour is changed.


<a name="9.8.0"></a>
# [9.8.0](https://github.com/pluskal/entity-controller/compare/v9.7.6...v9.8.0) (2026-04-06)

### Features

* **forced_sensors** – New `forced_sensors` config key. Sensors listed here bypass `blocked`, `constrained`, and `overridden` states and immediately activate the controller via a new `force_activate` state-machine trigger. Useful for panic buttons, manual overrides, or priority scenes.
* **event_sensors** – New `event_sensors` config key. Accepts a list of HA bus event type strings. When any of those events fires on the HA event bus the controller treats it like a sensor turning on (transitions from `idle` / `active_timer` / `blocked` to `active`). Cancel callbacks are tracked and cleaned up on reconfiguration.
* **block_timer_expires → idle fix** – When the block timer expired while all state entities were already off the controller was left stuck in `blocked`. The state machine now includes the missing transition: `blocked → idle` (condition `is_state_entities_off`).
* **State persistence** – Controller state (`overridden`, `blocked`) is now persisted across HA restarts using `homeassistant.helpers.storage.Store`. The saved state is restored on startup and re-validated against live entity states before being applied.

### Bug Fixes

* `block_timer_expires` with entities already off no longer leaves the controller stuck in `blocked` state (closes #310).

### Tests

* 47 new behavioral tests in `tests/test_legacy_behaviors.py` cover sensor flows, state-entity blocking, override entities, duration sensors, stay-on mode, multiple sensors, config registration, custom state strings, and constrained-state behavior.
* 28 tests in `tests/test_new_features.py` cover all four new feature areas end-to-end.
* All 7 permanently-skipped legacy test files are retained as historical artifacts; their scenarios are now covered by the two new files above.

<a name="9.7.6"></a>
## [9.7.6](https://github.com/danobot/entity-controller/compare/v9.7.5...v9.7.6) (2024-05-04)



<a name="9.7.5"></a>
## [9.7.5](https://github.com/danobot/entity-controller/compare/v9.7.4...v9.7.5) (2024-05-04)



<a name="9.7.4"></a>
## [9.7.4](https://github.com/danobot/entity-controller/compare/v9.7.3...v9.7.4) (2024-05-04)


### Bug Fixes

* async track events ([4421ed2](https://github.com/danobot/entity-controller/commit/4421ed2))



<a name="9.7.3"></a>
## [9.7.3](https://github.com/danobot/entity-controller/compare/v9.7.2...v9.7.3) (2024-03-19)



<a name="9.7.2"></a>
## [9.7.2](https://github.com/danobot/entity-controller/compare/v9.7.1...v9.7.2) (2024-02-14)


### Bug Fixes

* parsing config files broke with HA 2024.2.0 release. Closes [#320](https://github.com/danobot/entity-controller/issues/320) ([06cfe55](https://github.com/danobot/entity-controller/commit/06cfe55))



<a name="9.7.1"></a>
## [9.7.1](https://github.com/danobot/entity-controller/compare/v9.7.0...v9.7.1) (2024-01-13)


### Bug Fixes

* resolve defect [#316](https://github.com/danobot/entity-controller/issues/316) ([#317](https://github.com/danobot/entity-controller/issues/317)) ([b532262](https://github.com/danobot/entity-controller/commit/b532262))



<a name="9.7.0"></a>
# [9.7.0](https://github.com/danobot/entity-controller/compare/v9.6.1...v9.7.0) (2023-08-24)


### Features

* start up delay and tuning transitions ([cce7ba1](https://github.com/danobot/entity-controller/commit/cce7ba1))



<a name="9.6.1"></a>
## [9.6.1](https://github.com/danobot/entity-controller/compare/v9.6.0...v9.6.1) (2023-06-20)


### Bug Fixes

* context id length. Resolves [#297](https://github.com/danobot/entity-controller/issues/297) ([a9f3257](https://github.com/danobot/entity-controller/commit/a9f3257))



<a name="9.6.0"></a>
# [9.6.0](https://github.com/danobot/entity-controller/compare/v9.5.2...v9.6.0) (2022-11-08)


### Features

* Add possibility to manually enable blocked state ([6c6d827](https://github.com/danobot/entity-controller/commit/6c6d827))



<a name="9.5.2"></a>
## [9.5.2](https://github.com/danobot/entity-controller/compare/v9.5.1...v9.5.2) (2022-07-16)



<a name="9.2.9"></a>
## [9.2.9](https://github.com/danobot/entity-controller/compare/v9.2.8...v9.2.9) (2021-06-11)


### Bug Fixes

* upgrade transitions version to 0.8.8 ([88399ad](https://github.com/danobot/entity-controller/commit/88399ad))



<a name="9.2.8"></a>
## [9.2.8](https://github.com/danobot/entity-controller/compare/v9.2.7...v9.2.8) (2021-06-11)



<a name="9.2.7"></a>
## [9.2.7](https://github.com/danobot/entity-controller/compare/v9.2.6...v9.2.7) (2021-06-11)



<a name="9.2.6"></a>
## [9.2.6](https://github.com/danobot/entity-controller/compare/v9.2.5...v9.2.6) (2021-06-11)



<a name="9.2.5"></a>
## [9.2.5](https://github.com/danobot/entity-controller/compare/v9.2.4...v9.2.5) (2021-06-11)


### Bug Fixes

* upgrade transitions version to 0.8.8 ([#251](https://github.com/danobot/entity-controller/issues/251)) ([de9c954](https://github.com/danobot/entity-controller/commit/de9c954))



<a name="9.2.4"></a>
## [9.2.4](https://github.com/danobot/entity-controller/compare/v9.2.3...v9.2.4) (2021-05-25)


### Bug Fixes

* Version key ([#243](https://github.com/danobot/entity-controller/issues/243)) ([dc1f1ec](https://github.com/danobot/entity-controller/commit/dc1f1ec))



<a name="9.2.3"></a>
## [9.2.3](https://github.com/danobot/entity-controller/compare/v9.2.2...v9.2.3) (2021-05-04)


### Bug Fixes

* Version key ([#243](https://github.com/danobot/entity-controller/issues/243)) ([#245](https://github.com/danobot/entity-controller/issues/245)) ([6feef36](https://github.com/danobot/entity-controller/commit/6feef36))



<a name="9.2.2"></a>
## [9.2.2](https://github.com/danobot/entity-controller/compare/v9.2.1...v9.2.2) (2021-04-28)


### Bug Fixes

* Version key ([#243](https://github.com/danobot/entity-controller/issues/243)) ([#244](https://github.com/danobot/entity-controller/issues/244)) ([e2d7670](https://github.com/danobot/entity-controller/commit/e2d7670))



<a name="9.2.1"></a>
## [9.2.1](https://github.com/danobot/entity-controller/compare/v9.2.0...v9.2.1) (2021-02-04)


### Bug Fixes

* error messages used wrong variable ([9f20fb5](https://github.com/danobot/entity-controller/commit/9f20fb5))
* warn about potential configuration errors (could also mean entity is still initialising after reboot) ([7545d2e](https://github.com/danobot/entity-controller/commit/7545d2e))



<a name="9.2.0"></a>
# [9.2.0](https://github.com/danobot/entity-controller/compare/v9.1.0...v9.2.0) (2020-12-04)


### Bug Fixes

* HA does not need to poll EC for state ([#220](https://github.com/danobot/entity-controller/issues/220)) ([e8b833d](https://github.com/danobot/entity-controller/commit/e8b833d))
* missing service exceptions during startup ([#221](https://github.com/danobot/entity-controller/issues/221)) ([48d5602](https://github.com/danobot/entity-controller/commit/48d5602))


### Features

* Use unique Contexts to track cause and effect ([#222](https://github.com/danobot/entity-controller/issues/222)) ([56302ff](https://github.com/danobot/entity-controller/commit/56302ff))



<a name="9.1.0"></a>
# [9.1.0](https://github.com/danobot/entity-controller/compare/v9.0.2...v9.1.0) (2020-10-16)


### Features

* Allow 'ignored_event_sources' to contain Regex patterns to support integrations with dynamic context ids ([34df56e](https://github.com/danobot/entity-controller/commit/34df56e)), closes [/github.com/home-assistant/core/pull/40626#issuecomment-709373896](https://github.com//github.com/home-assistant/core/pull/40626/issues/issuecomment-709373896)



<a name="9.0.2"></a>
## [9.0.2](https://github.com/danobot/entity-controller/compare/v9.0.1...v9.0.2) (2020-10-12)


### Bug Fixes

* Context ID too long for recorder component [#200](https://github.com/danobot/entity-controller/issues/200) ([#203](https://github.com/danobot/entity-controller/issues/203)) ([a83ef05](https://github.com/danobot/entity-controller/commit/a83ef05))



<a name="9.0.1"></a>
## [9.0.1](https://github.com/danobot/entity-controller/compare/v9.0.0...v9.0.1) (2020-10-08)


### Bug Fixes

* include DOMAIN in Context id and log entire Context object for more detail ([bbc7b2e](https://github.com/danobot/entity-controller/commit/bbc7b2e))



<a name="9.0.0"></a>
# [9.0.0](https://github.com/danobot/entity-controller/compare/v8.0.0...v9.0.0) (2020-10-01)


### Features

* Implement Home Assistant Context API to avoid EC blocking itself (replaces grace_period) and ability to ignore event sources ([#193](https://github.com/danobot/entity-controller/issues/193)) ([738968d](https://github.com/danobot/entity-controller/commit/738968d)), closes [#192](https://github.com/danobot/entity-controller/issues/192) [#192](https://github.com/danobot/entity-controller/issues/192)


* fix!: Spelling of overridden ([0359947](https://github.com/danobot/entity-controller/commit/0359947))


### BREAKING CHANGES

* Fix the spelling of `on_enter_overidden` and `on_exit_overidden` to become `on_enter_overridden` and `on_exit_overridden` respectively.



<a name="8.0.0"></a>
# [8.0.0](https://github.com/danobot/entity-controller/compare/v7.0.0...v8.0.0) (2020-09-07)


### Features

* add customisable grace_period paramater to cater for long latencies in control entities ([b59d70c](https://github.com/danobot/entity-controller/commit/b59d70c))


* feat!: rename stay mode to make the feature easier to understand (#176) ([be46cb8](https://github.com/danobot/entity-controller/commit/be46cb8)), closes [#176](https://github.com/danobot/entity-controller/issues/176)


### BREAKING CHANGES

* Check the docs for new `stay_mode` configuration field and the name changes to the related services.



<a name="7.0.0"></a>
# [7.0.0](https://github.com/danobot/entity-controller/compare/v6.1.1...v7.0.0) (2020-09-04)


* feat!: rename stay mode to make the feature easier to understand (#176) (#177) ([9f7ec54](https://github.com/danobot/entity-controller/commit/9f7ec54)), closes [#176](https://github.com/danobot/entity-controller/issues/176) [#177](https://github.com/danobot/entity-controller/issues/177)


### BREAKING CHANGES

* Check the docs for new `stay_mode` configuration field and the name changes to the related services.



<a name="6.1.1"></a>
## [6.1.1](https://github.com/danobot/entity-controller/compare/v6.1.0...v6.1.1) (2020-09-03)


### Bug Fixes

* [#164](https://github.com/danobot/entity-controller/issues/164) active stay on never returning to idle state. ([75b1660](https://github.com/danobot/entity-controller/commit/75b1660))
* [#173](https://github.com/danobot/entity-controller/issues/173) call homeassistant.turn_on for groups ([afab88f](https://github.com/danobot/entity-controller/commit/afab88f))
* [#173](https://github.com/danobot/entity-controller/issues/173) include turn_off service and use the correct variable ([c54f2f0](https://github.com/danobot/entity-controller/commit/c54f2f0))
* [#174](https://github.com/danobot/entity-controller/issues/174) and [#98](https://github.com/danobot/entity-controller/issues/98) implements crude way to avoid getting blocked by ECs own service calls (and subsequent state changes) ([13f751b](https://github.com/danobot/entity-controller/commit/13f751b))
* add load-beta.sh script for loading files from develop branch ([67ec478](https://github.com/danobot/entity-controller/commit/67ec478))
* Fixes [#174](https://github.com/danobot/entity-controller/issues/174) and [#98](https://github.com/danobot/entity-controller/issues/98) where changing a control entity does not transition EC to blocked state (R3.2) ([f4c3275](https://github.com/danobot/entity-controller/commit/f4c3275))



<a name="6.1.0"></a>
# [6.1.0](https://github.com/danobot/entity-controller/compare/v6.0.1...v6.1.0) (2020-08-30)


### Bug Fixes

* Change mdi:timer* to mdi:timer*-outline in prep for HA 0.115 ([#172](https://github.com/danobot/entity-controller/issues/172)) ([9f019b8](https://github.com/danobot/entity-controller/commit/9f019b8))


### Features

* Transition Behaviours Extended ([#159](https://github.com/danobot/entity-controller/issues/159)) ([aa8dab9](https://github.com/danobot/entity-controller/commit/aa8dab9))



<a name="6.0.1"></a>
## [6.0.1](https://github.com/danobot/entity-controller/compare/v6.0.0...v6.0.1) (2020-08-30)



<a name="6.0.0"></a>
# [6.0.0](https://github.com/danobot/entity-controller/compare/v5.2.0...v6.0.0) (2020-06-20)


### Features

* transition behaviours and friendly name fix ([02a1ab4](https://github.com/danobot/entity-controller/commit/02a1ab4)), closes [#156](https://github.com/danobot/entity-controller/issues/156)


### BREAKING CHANGES

* The friendly name fix in #153 may break your configuration. Entities will be created based on the YAML section name but will respect friendly name in frontend.



<a name="5.2.0"></a>
# [5.2.0](https://github.com/danobot/entity-controller/compare/v5.1.2...v5.2.0) (2020-06-20)


### Bug Fixes

* BREAKING CHANGE ([2034e49](https://github.com/danobot/entity-controller/commit/2034e49))


### Features

* transition behaviours ([ffbbb47](https://github.com/danobot/entity-controller/commit/ffbbb47))
* transition behaviours  ([f85edc5](https://github.com/danobot/entity-controller/commit/f85edc5))



<a name="5.1.2"></a>
## [5.1.2](https://github.com/danobot/entity-controller/compare/v5.1.1...v5.1.2) (2020-04-05)



<a name="5.1.1"></a>
## [5.1.1](https://github.com/danobot/entity-controller/compare/v5.1.0...v5.1.1) (2020-04-05)



<a name="5.1.0"></a>
# [5.1.0](https://github.com/danobot/entity-controller/compare/v5.0.2...v5.1.0) (2020-03-02)


### Features

* basic services and control ([d1912b4](https://github.com/danobot/entity-controller/commit/d1912b4))
* Initial services buildout ([#142](https://github.com/danobot/entity-controller/issues/142)) ([e5e18f5](https://github.com/danobot/entity-controller/commit/e5e18f5))



<a name="5.0.2"></a>
## [5.0.2](https://github.com/danobot/entity-controller/compare/v5.0.1...v5.0.2) (2020-02-02)



<a name="5.0.1"></a>
## [5.0.1](https://github.com/danobot/entity-controller/compare/v5.0.0...v5.0.1) (2020-01-11)


### Bug Fixes

* remove trace logging ([b50f08b](https://github.com/danobot/entity-controller/commit/b50f08b))



<a name="5.0.0"></a>
# [5.0.0](https://github.com/danobot/entity-controller/compare/v4.2.0...v5.0.0) (2020-01-10)


* feat!: handle overrides better ([63f7aa8](https://github.com/danobot/entity-controller/commit/63f7aa8))


### BREAKING CHANGES

* Entering the override state will no longer turn off the control entities. This was implemented with the ratiionale that overriding an EC should not cause further interaction with the control entities. If the entities are on, they remain on when transitioning from active to override state. If the entities are off, they remain off going from other states in to override state.
If your configuration relied on this previous behaviour it will be a breaking change for you. Its unlikely your config took advantage of this weird behaviour.



<a name="4.2.0"></a>
# [4.2.0](https://github.com/danobot/entity-controller/compare/v4.1.6...v4.2.0) (2019-12-21)


### Features

* Allow customization of which attribute changes are considered a manual change, closes [#109](https://github.com/danobot/entity-controller/issues/109) ([#112](https://github.com/danobot/entity-controller/issues/112)) ([f0ea2a1](https://github.com/danobot/entity-controller/commit/f0ea2a1))



<a name="4.1.6"></a>
## [4.1.6](https://github.com/danobot/entity-controller/compare/v4.1.5...v4.1.6) (2019-12-17)


### Bug Fixes

* rollback implementation for [#98](https://github.com/danobot/entity-controller/issues/98), defective ([66a7a00](https://github.com/danobot/entity-controller/commit/66a7a00))



<a name="4.1.5"></a>
## [4.1.5](https://github.com/danobot/entity-controller/compare/v4.1.4...v4.1.5) (2019-12-17)


### Bug Fixes

* Add state transition for [#98](https://github.com/danobot/entity-controller/issues/98) to ensure requirement 3.2 is fulfilled. ([e0a2a96](https://github.com/danobot/entity-controller/commit/e0a2a96))



<a name="4.1.4"></a>
## [4.1.4](https://github.com/danobot/entity-controller/compare/v4.1.3...v4.1.4) (2019-12-17)



<a name="4.1.3"></a>
## [4.1.3](https://github.com/danobot/entity-controller/compare/v4.1.2...v4.1.3) (2019-12-07)



<a name="4.1.2"></a>
## [4.1.2](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v4.1.1...v4.1.2) (2019-12-07)



<a name="4.1.1"></a>
## [4.1.1](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v4.1.0...v4.1.1) (2019-12-06)



<a name="4.1.0"></a>
# [4.1.0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v4.0.4...v4.1.0) (2019-10-10)


### Bug Fixes

* pull request template and HACS manifest ([25f0a72](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/25f0a72))


### Features

* hacs ([147cd7f](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/147cd7f))



<a name="4.0.4"></a>
## [4.0.4](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v4.0.3...v4.0.4) (2019-09-14)



<a name="4.0.3"></a>
## [4.0.3](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v4.0.2...v4.0.3) (2019-08-13)



<a name="4.0.2"></a>
## [4.0.2](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v4.0.1...v4.0.2) (2019-08-10)



<a name="4.0.1"></a>
## [4.0.1](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v4.0.0...v4.0.1) (2019-06-03)


### Bug Fixes

* add manifest.json for HA v0.94 release ([271b237](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/271b237))



<a name="4.0.0"></a>
# [4.0.0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.3.3...v4.0.0) (2019-05-26)


### Bug Fixes

* Configuration loaded with duplicate entities. Implementation of state entities was erroneous. ([414f6c7](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/414f6c7))


### Features

* Introduce trigger entities whose turn_on service is called when control entities are turned on or off. ([7dc01f6](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/7dc01f6))


### BREAKING CHANGES

* rename entity_on to trigger_on_activate in your configurations!!!

These trigger entities could be scripts that are called whenever control entities are being controlled in some way. For example, when the controller enters active state, control entities are switched on (as usual). At the same time, any defined trigger_on_activate entities will be turned on.



<a name="3.3.3"></a>
## [3.3.3](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.3.2...v3.3.3) (2019-03-20)


### Bug Fixes

* add default delay ([17e3811](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/17e3811)), closes [#47](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/issues/47)
* check state when exiting constrained ([012b94e](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/012b94e)), closes [#43](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/issues/43)
* update readme. closes [#45](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/issues/45) ([0bfed7e](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/0bfed7e))



<a name="3.3.2"></a>
## [3.3.2](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.3.1...v3.3.2) (2019-03-20)



<a name="3.3.1"></a>
## [3.3.1](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.3.0...v3.3.1) (2019-03-11)


### Bug Fixes

* improve debug logging ([1bcccd1](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/1bcccd1))
* **off entities** Array was populated incorrectly on start up.


<a name="3.3.0"></a>
# [3.3.0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.2.0...v3.3.0) (2019-03-06)


### Bug Fixes

* add True and False to state strings ([52ba126](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/52ba126))
* config validation was not working ([330c4c7](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/330c4c7))

### Features

* Support for custom service data for `turn_off` calls ([#36](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/issues/36)) ([45f50cc](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/45f50cc))
* **duration sensor:** updated config keys, added validations, added `sensor_resets_timer` and updated docs ([d7a8093](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/d7a8093))



<a name="3.2.0"></a>
# [3.2.0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.1.4...v3.2.0) (2019-03-04)


### Bug Fixes

* add True and False to state strings ([66d0931](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/66d0931))


### Features

* **duration sensor:** updated config keys, added validations, added `sensor_resets_timer` and updated docs ([340e27d](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/340e27d))



<a name="3.1.4"></a>
## [3.1.4](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.1.3...v3.1.4) (2019-03-03)


### Bug Fixes

* revert defective change ([bce14ae](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/bce14ae))



<a name="3.1.3"></a>
## [3.1.3](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.1.2...v3.1.3) (2019-03-03)



<a name="3.1.2"></a>
## [3.1.2](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.1.1...v3.1.2) (2019-03-03)


### Bug Fixes

* Check that the block timer handle is not None before accessing attr. ([#38](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/issues/38)) ([2b36093](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/2b36093))



<a name="3.1.1"></a>
## [3.1.1](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.1.0...v3.1.1) (2019-02-26)


### Bug Fixes

* **blocked mode:** amendment to block timeout restriction. Controller should turn off control entities when blocked mode is exited via block_timer expiry ([f9702f0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/f9702f0))



<a name="3.1.0"></a>
# [3.1.0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.0.1...v3.1.0) (2019-02-26)


### Features

* **blocked mode:** add timeout to blocked mode such that the controller takes over after some time. ([9160879](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/9160879))



<a name="3.0.1"></a>
## [3.0.1](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v3.0.0...v3.0.1) (2019-02-26)


### Bug Fixes

* **tracker:** update component name and location ([91e4950](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/91e4950))



<a name="3.0.0"></a>
# [3.0.0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.10...v3.0.0) (2019-02-26)


### Chores

* rename component, migrate to new directory/file format ([889d5cd](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/889d5cd))


### BREAKING CHANGES

* component has been renamed to entity_controller and migrated to the new file/directory format. To update your configuration, hard-replace `lightingsm` with `entity_controller` in your configuration files and Lovelace config. The directory/file format change may require you go into your `custom_components` folder and manually remove the `lightingsm.py` file and create the new directory structure.



<a name="2.4.10"></a>
## [2.4.10](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.9...v2.4.10) (2019-02-11)


### Bug Fixes

* **overrides:** Entity does not go into override mode when override entities are active at start_time. ([ae4cff7](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/ae4cff7))



<a name="2.4.9"></a>
## [2.4.9](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.8...v2.4.9) (2019-01-17)



<a name="2.4.8"></a>
## [2.4.8](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.7...v2.4.8) (2019-01-17)


### Bug Fixes

* **constraints:** all the things wrong with it. (losing hope) ([4682b1d](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/4682b1d))



<a name="2.4.7"></a>
## [2.4.7](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.6...v2.4.7) (2019-01-16)


### Bug Fixes

* **constraints:** sunrise returning yesterdays sunrise. Patches futurize to correct symptom. Better fix required. ([ca3c0ea](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/ca3c0ea))



<a name="2.4.6"></a>
## [2.4.6](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.5...v2.4.6) (2019-01-16)



<a name="2.4.5"></a>
## [2.4.5](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.4...v2.4.5) (2019-01-16)



<a name="2.4.4"></a>
## [2.4.4](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.3...v2.4.4) (2019-01-16)


### Bug Fixes

* **constraints:** first start/stop times are set correctly. Subsequent start/stop time parameters to be tested. ([b67541f](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/b67541f))



<a name="2.4.3"></a>
## [2.4.3](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.2...v2.4.3) (2019-01-15)


### Bug Fixes

* **constraints:** End constraint should be adjusted based on current time (does not come after start time if within active period) ([61f7dc1](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/61f7dc1))



<a name="2.4.2"></a>
## [2.4.2](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.1...v2.4.2) (2019-01-15)


### Bug Fixes

* **constrains:** Constrains are not observed. Fixes [#20](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/issues/20) ([b9245f0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/b9245f0))



<a name="2.4.1"></a>
## [2.4.1](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.4.0...v2.4.1) (2019-01-14)



<a name="2.4.0"></a>
# [2.4.0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.3.0...v2.4.0) (2019-01-14)


### Bug Fixes

* **config:** make override config plural insensitive ([db5ac63](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/db5ac63))
* **constrains:** sunset/sunrise callbacks would not fire ([673250f](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/673250f))
* **constraints:** Some edge case defect fixes ([9af3def](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/9af3def))


### Features

* **constraints:** Add sunset / sunrise expressions to night_mode ([1bc74e6](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/1bc74e6))



<a name="2.3.0"></a>
# [2.3.0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/compare/v2.2.10...v2.3.0) (2019-01-14)


### Bug Fixes

* **constrains:** Catch TypeError when times start with number. Fixes [#17](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/issues/17). ([beef4f5](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/beef4f5))
* **constrains:** fixes [#15](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/issues/15) constrain end callback and start callback mixed up ([668b375](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/668b375))
* **test:** entity id already exists ([6646b41](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/6646b41))
* accept time offset with quotes ([98201f0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/98201f0))
* callback parameters ([7d559b0](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/7d559b0))
* idle icon to outline circle ([fb49916](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/fb49916))
* sun component returns UTC time. convert to local time ([c17179e](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/c17179e))


### Features

* **constraints:** Add support for sunset and sunrise expressions ([e9ed0b2](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/e9ed0b2))
* **constraints:** Add support for sunset and sunrise expressions ([91f80f3](https://gitlab.danielha.tk/HA/appdaemon-motion-lights/commit/91f80f3))


# Old Changelog
v0.1.0      First formal Release
v0.2.0      Added customizable state strings, fixes defect
v0.3.0      Add override switch functionality
v0.4.0      Add entities and state_entities configuration (experimental)

v1.0.0      Major rewrite using state machine implementation and more configuration options
v1.0.1      Fix typos in readme, update module reference in test suite
v1.1.0      Implements Home Assistant state entities including state attributes
v1.1.1      Add more information to state attributes

v2.0.0      HA component rewrite
v2.1.0      Implement time constraints and entity icons
v2.2.0      State attributes and defects
v2.2.1      Defect state entity
v2.2.2      Defect constrain times
v2.2.3      Defects: allow transitions in constrained state and lights would not turn off defect
v2.2.4      sensor duration type defect
v2.2.5      override config testing, backoff testing completed
v2.2.6      observe state entities (not control entities), fix function call typo, go to idle when all state entities switched off while active.
v2.2.7      night mode to activate on startup, add mode state attribute
v2.2.8      Error fix: calling entity update before Entity is added to hass
v2.2.9      Improved trigger and event handling, added blocked_by and blocked_at state attributes
v2.2.10     Defect fix #9, #12
v2.3.0      Feature: Sunset/sunrise support in start_time and end_time