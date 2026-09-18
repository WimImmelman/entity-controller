// SPDX-License-Identifier: GPL-3.0-or-later
// Entity Controller dashboard card. Plain web component, no build step.
//
//   type: custom:entity-controller-card
//   entity: entity_controller.auto_kitchen_lights      # detail card for one controller
//
//   type: custom:entity-controller-card
//   title: Auto lights                                  # compact list, one row per controller
//   entities:
//     - entity_controller.auto_kitchen_lights
//     - entity: entity_controller.auto_boundary_light
//       name: Boundary
//
// Options: name, show_entities (default true), show_buttons (default true),
// sort_by_state (list mode, default true; false keeps the configured order).

const CARD_TYPE = "entity-controller-card";
const GLOBAL_SWITCH = "switch.entity_controller";

const STATE_META = {
  active_timer: { label: "Active", color: "#43a047", icon: "mdi:timer-outline", order: 0 },
  active_stay_on: { label: "Stay on", color: "#43a047", icon: "mdi:timer-lock-outline", order: 0 },
  active: { label: "Active", color: "#43a047", icon: "mdi:check-circle", order: 0 },
  blocked: { label: "Blocked", color: "#fb8c00", icon: "mdi:close-circle", order: 1 },
  overridden: { label: "Overridden", color: "#8e24aa", icon: "mdi:timer-off-outline", order: 2 },
  idle: { label: "Idle", color: "#9e9e9e", icon: "mdi:circle-outline", order: 3 },
  constrained: { label: "Constrained", color: "#1e88e5", icon: "mdi:cancel", order: 4 },
  pending: { label: "Starting", color: "#9e9e9e", icon: "mdi:eye", order: 5 },
  unavailable: { label: "Unavailable", color: "#bdbdbd", icon: "mdi:help-circle-outline", order: 6 },
};

// ---------------------------------------------------------------- helpers

/** EC writes naive local timestamps: "2026-09-18T07:16:15.956272" or "2026-09-18 07:40:10.076". */
function parseLocal(value) {
  if (!value || typeof value !== "string") return null;
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?/);
  if (!m) {
    const d = new Date(value);
    return isNaN(d) ? null : d;
  }
  const ms = m[7] ? Math.round(Number(("0." + m[7])) * 1000) : 0;
  return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6], ms);
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function fmtDuration(ms) {
  if (ms <= 0) return "now";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${pad(s % 60)}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${pad(m % 60)}m`;
  return `${Math.floor(h / 24)}d ${pad(h % 24)}h`;
}

function fmtAgo(date) {
  return date ? `${fmtDuration(Date.now() - date.getTime())} ago` : "";
}

function fmtClock(date) {
  if (!date) return "";
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  const hm = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  return sameDay ? hm : `${hm} ${date.toLocaleDateString(undefined, { weekday: "short" })}`;
}

function minutes(delay) {
  const n = parseInt(String(delay ?? "").replace("s", ""), 10);
  return isNaN(n) ? null : Math.round(n / 60);
}

function shortName(entityId) {
  return String(entityId || "").split(".").pop().replace(/_/g, " ");
}

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Countdown span: the ticker updates its text every second without a re-render. */
function countdown(date) {
  if (!date) return "";
  return `<span class="cd" data-until="${date.getTime()}">${fmtDuration(date.getTime() - Date.now())}</span>`;
}

/** "auto_playroom_light" -> "Playroom light": used when a controller has no friendly_name of its own. */
function humanize(objectId) {
  const words = String(objectId || "").replace(/^auto_/, "").split("_").filter(Boolean);
  return words.map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(" ");
}

function friendly(hass, entityId, fallback) {
  const st = hass.states[entityId];
  const objectId = String(entityId || "").split(".").pop();
  const fn = st && st.attributes && st.attributes.friendly_name;
  // EC uses the YAML key as friendly_name unless `friendly_name:` is configured
  if (fn && fn !== objectId) return fn;
  return fallback || humanize(objectId);
}

// ---------------------------------------------------------------- card

class EntityControllerCard extends HTMLElement {
  static getStubConfig(hass) {
    const first = Object.keys(hass.states).find((id) => id.startsWith("entity_controller."));
    return { entity: first || "entity_controller.example" };
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TYPE);
  }

  setConfig(config) {
    if (!config || (!config.entity && !config.entities)) {
      throw new Error("entity-controller-card: set `entity` or `entities`");
    }
    this._config = {
      show_entities: true,
      show_buttons: true,
      sort_by_state: true,
      ...config,
    };
    this._list = Array.isArray(config.entities)
      ? config.entities.map((e) => (typeof e === "string" ? { entity: e } : e))
      : null;
    this._rendered = "";
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._list ? Math.ceil(this._list.length / 2) + 1 : 4;
  }

  connectedCallback() {
    this._tick = setInterval(() => this._updateCountdowns(), 1000);
    this.addEventListener("click", (ev) => this._onClick(ev));
  }

  disconnectedCallback() {
    clearInterval(this._tick);
  }

  // ---- rendering ---------------------------------------------------------

  _render() {
    if (!this._hass || !this._config) return;
    const html = this._list ? this._renderList() : this._renderDetail(this._config.entity, this._config.name);
    if (html === this._rendered) return; // nothing changed, keep the DOM (and the countdown spans) stable
    this._rendered = html;
    this.innerHTML = `<ha-card>${STYLE}${html}</ha-card>`;
    this._updateCountdowns();
  }

  _globalOffBanner() {
    const sw = this._hass.states[GLOBAL_SWITCH];
    if (sw && sw.state === "off") {
      return `<div class="banner"><ha-icon icon="mdi:motion-sensor-off"></ha-icon>Entity Controller is switched off</div>`;
    }
    return "";
  }

  _renderDetail(entityId, name) {
    const hass = this._hass;
    const st = hass.states[entityId];
    if (!st) {
      return `<div class="warn">${esc(entityId)} not found</div>`;
    }
    const a = st.attributes || {};
    const meta = STATE_META[st.state] || STATE_META.unavailable;
    const delay = minutes(a.delay);
    const window = a.start && a.end ? `${esc(a.start)} → ${esc(a.end)}` : "";

    const lines = this._stateLines(st);
    if (a.notes) lines.push(`<div class="note">${esc(a.notes)}</div>`);

    let entities = "";
    if (this._config.show_entities) {
      entities = this._entityRows(a);
    }

    let buttons = "";
    if (this._config.show_buttons) {
      const b = [];
      // idle and blocked are the only states with an `activate` transition
      if (["idle", "blocked"].includes(st.state)) b.push(this._button("activate", "Activate", entityId));
      if (st.state === "blocked") b.push(this._button("clear_block", "Clear block", entityId));
      if (st.state === "active_timer") b.push(this._button("enable_block", "Block", entityId));
      if (b.length) buttons = `<div class="buttons">${b.join("")}</div>`;
    }

    return `
      ${this._globalOffBanner()}
      <div class="head">
        <ha-icon class="state-icon" icon="${meta.icon}" style="color:${meta.color}"></ha-icon>
        <div class="titles">
          <div class="name">${esc(name || friendly(hass, entityId))}</div>
          <div class="sub">${delay !== null ? `${delay} min` : ""}${window ? ` · ${window}` : ""}</div>
        </div>
        <div class="chip" style="background:${meta.color}">${meta.label}</div>
        <ha-icon class="more" icon="mdi:information-outline" title="Details" data-action="more-info" data-entity="${esc(entityId)}"></ha-icon>
      </div>
      <div class="body">${lines.join("")}</div>
      ${entities}
      ${buttons}`;
  }

  /** The per-state detail lines, shared by the detail card and the list rows. */
  _stateLines(st, compact = false) {
    const a = st.attributes || {};
    const L = [];
    const line = (icon, text) => L.push(`<div class="line"><ha-icon icon="${icon}"></ha-icon><span>${text}</span></div>`);
    const trig = a.last_triggered_by ? `${esc(shortName(a.last_triggered_by))}` : "";
    const graceful = parseLocal(a.graceful_off_expires_at);

    switch (st.state) {
      case "active_timer":
      case "active": {
        const expires = a.expires_at === "pending sensor" ? null : parseLocal(a.expires_at);
        if (trig) line("mdi:motion-sensor", `Triggered by <b>${trig}</b> ${esc(fmtAgo(parseLocal(a.last_triggered_at)))}`);
        if (a.expires_at === "pending sensor") line("mdi:timer-sand", "Waiting for the sensor to clear");
        else if (expires) line("mdi:timer-outline", `Switching off in <b>${countdown(expires)}</b> (${fmtClock(expires)})`);
        if (!compact && a.reset_at) line("mdi:restart", `Timer reset ${esc(fmtAgo(parseLocal(a.reset_at)))}`);
        break;
      }
      case "active_stay_on":
        line("mdi:timer-lock-outline", "Stays on until switched off by hand");
        break;
      case "blocked": {
        const at = parseLocal(a.blocked_at);
        line("mdi:hand-back-left", `Blocked by <b>${esc(shortName(a.blocked_by) || "manual control")}</b> ${esc(fmtAgo(at))}`);
        if (at && a.block_timeout) {
          const until = new Date(at.getTime() + Number(a.block_timeout) * 1000);
          line("mdi:timer-outline", `Block clears in <b>${countdown(until)}</b> (${fmtClock(until)})`);
        } else if (!compact) {
          line("mdi:timer-off-outline", "Block clears when the light is switched off");
        }
        break;
      }
      case "overridden":
        line("mdi:pause-circle-outline", `Overridden by <b>${esc(shortName(a.overridden_by) || "override entity")}</b> ${esc(fmtAgo(parseLocal(a.overridden_at)))}`);
        if (graceful) line("mdi:lightbulb-off-outline", `Still switching off in <b>${countdown(graceful)}</b>`);
        break;
      case "constrained": {
        const opens = parseLocal(a.start_time);
        line("mdi:clock-outline", opens ? `Outside window · opens <b>${esc(fmtClock(opens))}</b>` : "Outside the active window");
        if (graceful) line("mdi:lightbulb-off-outline", `Still switching off in <b>${countdown(graceful)}</b>`);
        break;
      }
      case "idle": {
        if (trig) line("mdi:motion-sensor", `Last triggered by <b>${trig}</b> ${esc(fmtAgo(parseLocal(a.last_triggered_at)))}`);
        else line("mdi:motion-sensor", "Waiting for motion");
        const closes = parseLocal(a.end_time);
        if (!compact && closes) line("mdi:clock-outline", `Window closes <b>${esc(fmtClock(closes))}</b>`);
        if (!compact && a.lux_blocked_at) line("mdi:brightness-6", `Too bright at ${esc(fmtClock(parseLocal(a.lux_blocked_at)))}`);
        break;
      }
      case "pending":
        line("mdi:eye", "Starting up");
        break;
      default:
        line("mdi:help-circle-outline", esc(st.state));
    }
    return L;
  }

  _entityRows(a) {
    const hass = this._hass;
    const groups = [
      ["Sensors", a.sensor_entities, ""],
      ["Hold", a.hold_sensor_entities, "hold"],
      ["Forced", a.forced_sensor_entities, "forced"],
      ["Lights", a.control_entities, ""],
      ["Overrides", a.override_entities, ""],
    ];
    const rows = [];
    for (const [label, list, tag] of groups) {
      if (!Array.isArray(list) || !list.length) continue;
      const items = list.map((id) => {
        const s = hass.states[id];
        const on = s && ["on", "open", "playing", "home"].includes(s.state);
        const missing = !s;
        return `<span class="ent ${on ? "on" : ""} ${missing ? "missing" : ""}" data-action="more-info" data-entity="${esc(id)}" title="${esc(id)}">
          <i class="dot"></i>${esc(friendly(hass, id))}${tag ? `<em>${tag}</em>` : ""}</span>`;
      });
      rows.push(`<div class="group"><span class="glabel">${label}</span>${items.join("")}</div>`);
    }
    return rows.length ? `<div class="entities">${rows.join("")}</div>` : "";
  }

  _button(service, label, entityId) {
    return `<button data-action="${service}" data-entity="${esc(entityId)}">${label}</button>`;
  }

  _renderList() {
    const hass = this._hass;
    let rows = this._list.map((item) => ({ item, st: hass.states[item.entity] }));
    if (this._config.sort_by_state) {
      rows = rows.sort((x, y) => {
        const ox = (STATE_META[x.st?.state] || STATE_META.unavailable).order;
        const oy = (STATE_META[y.st?.state] || STATE_META.unavailable).order;
        return ox - oy || String(x.item.name || x.item.entity).localeCompare(String(y.item.name || y.item.entity));
      });
    }
    rows = rows.map(({ item, st }) => {
        const meta = STATE_META[st?.state] || STATE_META.unavailable;
        const detail = st ? this._stateLines(st, true).join("") : `<div class="line">not found</div>`;
        return `
          <div class="row" data-action="more-info" data-entity="${esc(item.entity)}">
            <ha-icon icon="${meta.icon}" style="color:${meta.color}"></ha-icon>
            <div class="rtext">
              <div class="rname">${esc(item.name || friendly(hass, item.entity))}<span class="rdelay">${minutes(st?.attributes?.delay) ?? ""}${st?.attributes?.delay ? " min" : ""}</span></div>
              <div class="rdetail">${detail}</div>
            </div>
            <div class="chip" style="background:${meta.color}">${meta.label}</div>
          </div>`;
      });
    const title = this._config.title ? `<div class="head"><div class="titles"><div class="name">${esc(this._config.title)}</div></div></div>` : "";
    return `${this._globalOffBanner()}${title}<div class="list">${rows.join("")}</div>`;
  }

  // ---- behaviour ---------------------------------------------------------

  _updateCountdowns() {
    const now = Date.now();
    let expired = false;
    this.querySelectorAll(".cd").forEach((el) => {
      const left = Number(el.dataset.until) - now;
      el.textContent = fmtDuration(left);
      if (left <= 0) expired = true;
    });
    if (expired) {
      // let the next state push re-render; nothing else to do here
    }
  }

  _onClick(ev) {
    const target = ev.target.closest("[data-action]");
    if (!target) return;
    ev.stopPropagation();
    const { action, entity } = target.dataset;
    if (action === "more-info") {
      this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: entity } }));
      return;
    }
    this._hass.callService("entity_controller", action, { entity_id: entity });
  }
}

const STYLE = `<style>
  ha-card { padding: 12px 16px; font-size: 14px; }
  .banner { display:flex; align-items:center; gap:8px; background:#8e24aa22; color:#8e24aa; border-radius:8px; padding:6px 10px; margin-bottom:8px; font-weight:500; }
  .head { display:flex; align-items:center; gap:12px; }
  .state-icon { --mdc-icon-size: 32px; }
  .titles { flex:1; min-width:0; }
  .name { font-size: 16px; font-weight: 500; color: var(--primary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .sub { color: var(--secondary-text-color); font-size: 12px; }
  .chip { color:#fff; border-radius: 12px; padding: 2px 10px; font-size: 12px; font-weight:500; white-space:nowrap; }
  .more { --mdc-icon-size: 20px; color: var(--secondary-text-color); cursor: pointer; flex:none; }
  .more:hover { color: var(--primary-color); }
  .body { margin: 10px 0 4px; display:flex; flex-direction:column; gap:4px; }
  .line { display:flex; align-items:center; gap:8px; color: var(--primary-text-color); }
  .line ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); flex:none; }
  .line b { font-weight: 600; }
  .note { color: var(--secondary-text-color); font-style: italic; font-size: 12px; margin-top:2px; }
  .warn { color: var(--error-color, #db4437); }
  .entities { border-top: 1px solid var(--divider-color); margin-top: 8px; padding-top: 8px; display:flex; flex-direction:column; gap:4px; }
  .group { display:flex; flex-wrap:wrap; align-items:center; gap:6px; }
  .glabel { color: var(--secondary-text-color); font-size: 12px; width: 62px; flex:none; }
  .ent { display:inline-flex; align-items:center; gap:5px; background: var(--secondary-background-color, #f0f0f0); border-radius: 12px; padding: 2px 9px; font-size: 12px; cursor:pointer; }
  .ent em { font-style: normal; color: var(--secondary-text-color); font-size: 10px; text-transform: uppercase; }
  .ent.missing { opacity: .5; text-decoration: line-through; }
  .dot { width:8px; height:8px; border-radius:50%; background:#bdbdbd; display:inline-block; }
  .ent.on .dot { background:#fdd835; box-shadow: 0 0 4px #fdd835; }
  .buttons { display:flex; gap:8px; margin-top: 10px; flex-wrap:wrap; }
  button { background: none; border: 1px solid var(--primary-color); color: var(--primary-color); border-radius: 6px; padding: 4px 12px; font: inherit; font-size: 13px; cursor: pointer; }
  button:hover { background: var(--primary-color); color: #fff; }
  .list { display:flex; flex-direction:column; }
  .row { display:flex; align-items:center; gap:12px; padding: 8px 0; border-bottom: 1px solid var(--divider-color); cursor:pointer; }
  .row:last-child { border-bottom: none; }
  .row ha-icon { --mdc-icon-size: 24px; flex:none; }
  .rtext { flex:1; min-width:0; }
  .rname { font-weight: 500; color: var(--primary-text-color); }
  .rdelay { color: var(--secondary-text-color); font-size: 12px; margin-left: 6px; font-weight: normal; }
  .rdetail { color: var(--secondary-text-color); font-size: 12px; }
  .rdetail .line { color: inherit; gap: 6px; }
  .rdetail ha-icon { --mdc-icon-size: 14px; }
</style>`;

// ---------------------------------------------------------------- visual editor

const EDITOR_TYPE = "entity-controller-card-editor";
const ROW_EDITOR = "hui-entities-card-row-editor";

const EDITOR_LABELS = {
  mode: "Layout",
  entity: "Controller",
  entities: "Controllers",
  name: "Name (optional)",
  title: "Title (optional)",
  show_entities: "Show sensors and lights",
  show_buttons: "Show action buttons",
  sort_by_state: "Sort by state (off keeps the order below)",
};

/** ha-form is part of HA's editor bundle; make sure it is loaded before we render it. */
async function ensureHaForm() {
  if (customElements.get("ha-form")) return;
  try {
    const helpers = await window.loadCardHelpers();
    const probe = await helpers.createCardElement({ type: "entities", entities: [] });
    if (probe && probe.constructor && probe.constructor.getConfigElement) {
      await probe.constructor.getConfigElement();
    }
  } catch (e) {
    // fall through: ha-form may still turn up, and the YAML editor keeps working regardless
  }
  await customElements.whenDefined("ha-form");
}

class EntityControllerCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    this._render();
  }

  async _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      if (this._loading) return;
      this._loading = true;
      await ensureHaForm();
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => EDITOR_LABELS[schema.name] || schema.name;
      this._form.addEventListener("value-changed", (ev) => this._valueChanged(ev));
      this.innerHTML = "";
      this.appendChild(this._form);
      // HA's own entities-card row editor: drag to reorder, add, remove. It is
      // part of the editor bundle ensureHaForm() loaded; fall back to a plain
      // multi-select in the form if a future HA drops it.
      if (customElements.get(ROW_EDITOR)) {
        this._rows = document.createElement(ROW_EDITOR);
        this._rows.addEventListener("entities-changed", (ev) => this._rowsChanged(ev));
        this.appendChild(this._rows);
      }
      this._loading = false;
    }
    const list = Array.isArray(this._config.entities);
    this._form.hass = this._hass;
    if (this._rows) {
      this._rows.hass = this._hass;
      this._rows.entities = list ? this._config.entities : [];
      this._rows.style.display = list ? "" : "none";
    }
    this._form.schema = list
      ? [
          this._modeSchema(),
          { name: "title", selector: { text: {} } },
          { name: "sort_by_state", selector: { boolean: {} } },
          ...(this._rows ? [] : [{ name: "entities", selector: { entity: { domain: "entity_controller", multiple: true } } }]),
        ]
      : [
          this._modeSchema(),
          { name: "entity", selector: { entity: { domain: "entity_controller" } } },
          { name: "name", selector: { text: {} } },
          { name: "show_entities", selector: { boolean: {} } },
          { name: "show_buttons", selector: { boolean: {} } },
        ];
    this._form.data = {
      mode: list ? "list" : "single",
      entity: this._config.entity || "",
      name: this._config.name || "",
      title: this._config.title || "",
      // the multi-entity selector works on ids; {entity, name} items keep their name on the way back
      entities: list ? this._config.entities.map((e) => (typeof e === "string" ? e : e.entity)) : [],
      show_entities: this._config.show_entities !== false,
      show_buttons: this._config.show_buttons !== false,
      sort_by_state: this._config.sort_by_state !== false,
    };
  }

  /** The row editor changed the list (reorder, add, remove): keep the rest of the config. */
  _rowsChanged(ev) {
    ev.stopPropagation();
    const entities = (ev.detail.entities || []).map((e) =>
      typeof e === "string" ? e : e.name ? { entity: e.entity, name: e.name } : e.entity
    );
    this._emit({ ...this._config, entities });
  }

  _emit(config) {
    this._config = config;
    this._render();
    this.dispatchEvent(new CustomEvent("config-changed", { bubbles: true, composed: true, detail: { config } }));
  }

  _modeSchema() {
    return {
      name: "mode",
      selector: {
        select: {
          mode: "dropdown",
          options: [
            { value: "single", label: "One controller in detail" },
            { value: "list", label: "Compact list of controllers" },
          ],
        },
      },
    };
  }

  _valueChanged(ev) {
    ev.stopPropagation();
    const v = ev.detail.value || {};
    const config = { type: `custom:${CARD_TYPE}` };
    if (v.mode === "list") {
      if (v.title) config.title = v.title;
      if (v.sort_by_state === false) config.sort_by_state = false;
      const previous = Array.isArray(this._config.entities) ? this._config.entities : [];
      if (this._rows) {
        config.entities = previous;  // the row editor owns the list
      } else {
        const names = new Map(previous.filter((e) => typeof e === "object" && e.name).map((e) => [e.entity, e.name]));
        config.entities = (v.entities || []).map((id) => (names.has(id) ? { entity: id, name: names.get(id) } : id));
      }
    } else {
      if (v.entity) config.entity = v.entity;
      if (v.name) config.name = v.name;
      if (v.show_entities === false) config.show_entities = false;
      if (v.show_buttons === false) config.show_buttons = false;
    }
    this._emit(config);
  }
}

if (!customElements.get(EDITOR_TYPE)) {
  customElements.define(EDITOR_TYPE, EntityControllerCardEditor);
}
if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, EntityControllerCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === CARD_TYPE)) {
  window.customCards.push({
    type: CARD_TYPE,
    name: "Entity Controller Card",
    description: "State, timers, sensors and controls of one Entity Controller instance, or a compact list of several.",
    preview: false,
    documentationURL: "https://github.com/WimImmelman/entity-controller#dashboard-card",
  });
}
