const STYLE = `
:host { display: block; overflow-wrap: anywhere; }
.grid { columns: 340px 3; column-gap: 8px; orphans: 1; widows: 1; }
.block {
  display: inline-grid; grid-template-columns: minmax(0, 1fr); gap: 8px; width: 100%; margin-bottom: 8px;
  vertical-align: top;
}
[hidden] { display: none !important; }
.text { padding: 16px; }
.status { margin-bottom: 8px; }
.status.empty { position: absolute; width: 1px; height: 1px; margin: 0; overflow: hidden; clip-path: inset(50%); }
.list { padding: 4px 16px; }
.item { padding: 12px 0; border-bottom: 1px solid var(--divider-color); }
.item:last-child { border-bottom: 0; }
h3 { margin: 0; font: inherit; }
.name { font-weight: 500; }
.meta { color: var(--secondary-text-color); font-size: 0.9em; }
.body { margin-top: 4px; white-space: pre-line; }
.photos { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 4px; margin-top: 8px; }
.photo {
  display: grid; place-items: center; aspect-ratio: 4 / 3; padding: 0; border-radius: 8px; overflow: hidden;
  background: var(--secondary-background-color); color: var(--secondary-text-color); text-align: center;
}
.photo > * { grid-area: 1 / 1; }
.photo img { width: 100%; height: 100%; object-fit: cover; }
.more {
  place-self: stretch; display: grid; place-items: center; background: rgba(0, 0, 0, 0.5); color: #fff; font-size: 24px;
}
dialog {
  width: 100%; height: 100vh; height: 100dvh; max-width: none; max-height: none; margin: 0; padding: 0; border: 0;
  background: #000; color: #fff; touch-action: none; -webkit-user-select: none; user-select: none;
}
dialog[open] { display: grid; grid-template: minmax(0, 1fr) auto / minmax(0, 1fr); place-items: center; }
dialog::backdrop { background: #000; }
dialog:focus-visible { outline-offset: -2px; }
dialog img { max-width: 100%; max-height: 100%; object-fit: contain; }
dialog p { place-self: stretch; display: grid; place-items: center; margin: 0; text-align: center; }
.bar {
  grid-row: 2; justify-self: stretch; display: grid; grid-template-columns: 1fr auto auto auto 1fr; gap: 8px;
  place-items: center start; padding: 8px 8px calc(8px + var(--safe-area-inset-bottom, env(safe-area-inset-bottom)));
}
.bar button { min-width: 44px; padding: 0; background: none; color: inherit; }
.form { display: grid; gap: 12px; padding: 0 16px 16px; }
label { display: grid; gap: 4px; color: var(--secondary-text-color); }
select, textarea {
  box-sizing: border-box; width: 100%; min-height: 44px; padding: 8px; border: 1px solid var(--divider-color);
  border-radius: 8px; background: var(--card-background-color); color: var(--primary-text-color); font: inherit;
}
textarea { resize: vertical; }
.row { display: flex; align-items: center; gap: 12px; }
.row span { flex: 1; }
.error { color: var(--error-color); }
button {
  min-height: 44px; padding: 8px 20px; border: 0; border-radius: 22px; background: var(--primary-color);
  color: var(--text-primary-color); font: inherit; cursor: pointer;
}
button.link { padding: 0; background: none; color: var(--primary-color); }
button:disabled { opacity: 0.5; cursor: default; }
:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
h2 {
  margin: 0; padding: 0 4px 12px; font-size: 24px; font-weight: 400; line-height: 32px;
  color: var(--ha-card-header-color, inherit);
}
`;
const TEXTS = {
  en: {
    unreadAnnouncements: "Unread announcements",
    unreadConversations: "Unread conversations",
    nextEvent: "Next event",
    recentPhotos: "Recent photos",
    announcement: "Announcement",
    event: "Calendar item",
    new: "new",
    photo: "Photo {number} of {total}",
    onePhoto: "1 photo",
    photoCount: "{count} photos",
    noPhoto: "Photo not available",
    previous: "Previous photo",
    next: "Next photo",
    close: "Close",
    unread: "unread",
    more: "Show more",
    less: "Show less",
    allDay: "all day",
    noAnnouncements: "No announcements yet.",
    noGroup: "No announcements for {group}.",
    noConversations: "No conversations.",
    noEvents: "Nothing on the calendar.",
    conversation: "Conversation",
    roomsOff: "An administrator can turn on Conversations in the Parro card in the Parro options.",
    roomsOwn: "Only the Home Assistant user of this account can read its conversations.",
    reply: "Reply",
    message: "Message",
    send: "Send",
    sent: "Sent.",
    lost: "The connection to Home Assistant was lost. Check the conversation in Parro before you send it again.",
    loading: "Loading Parro",
    none: "Ask an administrator to add your Parro account, or to let you read an account in the Parro options.",
    noAccess: "You cannot read this Parro account. An administrator can add you in the Parro options.",
    not_loaded: "Parro is not available right now. An administrator can check Settings > Devices & services.",
    reauth: "The Parro session has ended. An administrator signs in again under Settings > Devices & services.",
    failed: "The Parro data could not be updated. This is the data of {time}.",
    show_announcements: "Announcements",
    show_children: "Children",
    show_photos: "Photos",
    show_conversations: "Conversations",
    show_reply: "Reply form",
    show_calendar: "Calendar",
    title: "Title",
    account: "Parro account",
    accountHelp: "Leave empty to show the account of whoever views the card.",
    announcement_count: "Number of announcements",
    group: "Group",
  },
  nl: {
    unreadAnnouncements: "Ongelezen berichten",
    unreadConversations: "Ongelezen gesprekken",
    nextEvent: "Volgende activiteit",
    recentPhotos: "Recente foto's",
    announcement: "Bericht",
    event: "Agenda-item",
    new: "nieuw",
    photo: "Foto {number} van {total}",
    onePhoto: "1 foto",
    photoCount: "{count} foto's",
    noPhoto: "Foto niet beschikbaar",
    previous: "Vorige foto",
    next: "Volgende foto",
    close: "Sluiten",
    unread: "ongelezen",
    more: "Meer tonen",
    less: "Minder tonen",
    allDay: "hele dag",
    noAnnouncements: "Nog geen berichten.",
    noGroup: "Geen berichten voor {group}.",
    noConversations: "Geen gesprekken.",
    noEvents: "Niets in de agenda.",
    conversation: "Gesprek",
    roomsOff: "Een beheerder kan Gesprekken in de Parro-kaart aanzetten in de Parro-opties.",
    roomsOwn: "Alleen de Home Assistant-gebruiker van dit account kan de gesprekken lezen.",
    reply: "Antwoorden",
    message: "Bericht",
    send: "Versturen",
    sent: "Verstuurd.",
    lost: "De verbinding met Home Assistant is verbroken. Kijk in het gesprek in Parro voordat je opnieuw verstuurt.",
    loading: "Parro laden",
    none:
      "Vraag een beheerder om je Parro-account toe te voegen, of om je een account te laten lezen in de Parro-opties.",
    noAccess: "Je kunt dit Parro-account niet lezen. Een beheerder kan je toevoegen in de Parro-opties.",
    not_loaded: "Parro is nu niet beschikbaar. Een beheerder kan kijken in Instellingen > Apparaten en diensten.",
    reauth: "De Parro-sessie is afgelopen. Een beheerder meldt zich weer aan in Instellingen > Apparaten en diensten.",
    failed: "De Parro-gegevens konden niet worden bijgewerkt. Dit zijn de gegevens van {time}.",
    show_announcements: "Berichten",
    show_children: "Kinderen",
    show_photos: "Foto's",
    show_conversations: "Gesprekken",
    show_reply: "Antwoordformulier",
    show_calendar: "Agenda",
    title: "Titel",
    account: "Parro-account",
    accountHelp: "Laat leeg om het account te tonen van wie de kaart bekijkt.",
    announcement_count: "Aantal berichten",
    group: "Groep",
  },
};

const el = (tag, props = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "role" || key.startsWith("aria-")) node.setAttribute(key, value);
    else node[key] = value;
  }
  node.append(...children.filter(Boolean));
  return node;
};
const valid = (id) => (typeof id === "string" && /^[a-z0-9_]+\.[a-z0-9_]+$/.test(id) ? id : null);
const language = (hass) => hass?.locale?.language || hass?.language || "";
const texts = (hass) => TEXTS[/^nl/.test(language(hass)) ? "nl" : "en"];
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ""));
const objects = (value) => (Array.isArray(value) ? value : []).filter((item) => item?.constructor === Object);
const strings = (value) => (Array.isArray(value) ? value : []).filter((item) => typeof item === "string");
const PARTS = ["announcements", "children", "photos", "conversations", "reply", "calendar"].map((p) => `show_${p}`);
const DEFAULTS = Object.fromEntries(PARTS.map((part) => [part, true]));
const PREVIEW = 280;
const PHOTOS = 4;
const GESTURES = "pointerdown pointermove pointerup pointercancel touchstart touchmove touchend touchcancel wheel";
const SCROLLS = ["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"];
const DAY = { weekday: "short", day: "numeric", month: "short" };
const TIME = { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" };
const hourCycle = (hass) => {
  const clock = hass?.locale?.time_format;
  if (clock === "system") return new Date(2023, 0, 1, 22).toLocaleString().includes("10") ? "h12" : "h23";
  return { 24: "h23", 12: "h12" }[clock];
};
const regional = (hass) => JSON.stringify([language(hass), hass?.locale?.time_format, hass?.config?.time_zone]);
const format = (hass, value, options, end) => {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "";
  try {
    const timeZone = hass?.config?.time_zone;
    const cycle = options.hour ? hourCycle(hass) : undefined;
    const intl = new Intl.DateTimeFormat(language(hass) || "en", { ...options, timeZone, hourCycle: cycle });
    return end > date ? intl.formatRange(date, end) : intl.format(date);
  } catch {
    return end === undefined ? date.toLocaleString() : format(hass, value, options);
  }
};
const cardHelpers = async () => {
  if (!window.loadCardHelpers) {
    const resolver = document.createElement("partial-panel-resolver");
    await resolver._getRoutes([{ component_name: "lovelace", url_path: "parro-ha" }]).routes["parro-ha"].load();
  }
  return window.loadCardHelpers();
};

class ParroCard extends HTMLElement {
  constructor() {
    super();
    this._cards = [];
    this._config = DEFAULTS;
    this._photos = new Map();
    this._pending = new Map();
    this._open = new Set();
    this._run = 0;
    this._ids = 0;
    this._status = el("div", { className: "text", role: "status" });
    this._statusCard = el("ha-card", { className: "status empty" }, this._status);
    this._head = el("div");
    this._main = el("div");
    const style = el("style", { textContent: STYLE });
    this.attachShadow({ mode: "open" }).append(style, this._head, this._statusCard, this._main);
  }

  setConfig(config) {
    const options = { ...DEFAULTS, ...config };
    const count = options.announcement_count;
    const bad = (keys, ...types) => keys.find((key) => !types.includes(typeof options[key]));
    const part = bad(PARTS, "boolean");
    const text = bad(["title", "group", "account"], "string", "undefined");
    if (part || text) throw new Error(`${part || text}: ${part ? "true or false" : "text"}`);
    if (count !== undefined && !(Number.isInteger(count) && count >= 1 && count <= 20)) {
      throw new Error("announcement_count: 1 to 20");
    }
    if (JSON.stringify(options) === JSON.stringify(this._config)) return;
    const old = this._config;
    this._config = options;
    if (["account", "group"].some((key) => (options[key] || "") !== (old[key] || ""))) {
      this._unsubscribe();
      this._data = null;
    }
    this._connect();
    this._render();
  }

  static async getConfigForm() {
    const hass = document.querySelector("home-assistant")?.hass;
    const t = texts(hass);
    const answer = await hass?.callWS({ type: "parro_ha/accounts" }).catch(() => null);
    const accounts = objects(answer).filter((item) => typeof item.entry_id === "string");
    const groups = [...new Set(accounts.flatMap((item) => strings(item.groups)).filter(Boolean))].sort();
    const choices = accounts.map((item) => ({ value: item.entry_id, label: String(item.title || item.entry_id) }));
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        ...(choices.length ? [{ name: "account", selector: { select: { options: choices, mode: "dropdown" } } }] : []),
        { name: "announcement_count", selector: { number: { min: 1, max: 20, mode: "box" } } },
        { name: "group", selector: { select: { options: groups, custom_value: true, mode: "dropdown" } } },
        ...PARTS.map((name) => ({ name, default: true, selector: { boolean: {} } })),
      ],
      computeLabel: (schema) => t[schema.name],
      computeHelper: (schema) => (schema.name === "account" ? t.accountHelp : undefined),
    };
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: "full" };
  }

  connectedCallback() {
    this._connect();
    this._render();
  }

  disconnectedCallback() {
    this._unsubscribe();
    this._drop();
    if (this._list) this._list.key = "";
  }

  set hass(hass) {
    const running = hass.config?.state === "RUNNING";
    const changed = !this._hass || running !== this._running || regional(hass) !== regional(this._hass);
    if (running && this._running === false) {
      this._cancelRetry();
      if (this._data?.missing) this._data = null;
    }
    this._hass = hass;
    this._running = running;
    if (!this._live()) this._sub = null;
    for (const card of this._cards) card.hass = hass;
    this._connect();
    if (changed) this._render();
  }

  set public(value) {
    const old = this._public || {};
    this._public = value;
    const keys = ["announcements", "conversations"];
    if (keys.some((key) => old[key] !== value[key]) || String(old.recent_photos) !== String(value.recent_photos)) {
      this._render();
    }
  }

  _live() {
    const connection = this._hass?.connection;
    return Boolean(connection) && connection.connected !== false && connection.socket === this._socket;
  }

  _cancelRetry() {
    clearTimeout(this._retry);
    this._retry = null;
  }

  _connect() {
    const connection = this._hass?.connection;
    if (this._sub || this._retry || !connection || connection.connected === false || !this.isConnected) return;
    const { account, group } = this._config;
    const message = { type: "parro_ha/subscribe", ...(account && { entry_id: account }), ...(group && { group }) };
    this._socket = connection.socket;
    const sub = connection.subscribeMessage((payload) => this._receive(sub, payload), message, { resubscribe: false });
    this._sub = sub;
    sub.catch(() => {
      if (this._sub !== sub) return;
      this._sub = null;
      if (!this._live()) return;
      this._failures = (this._failures || 0) + 1;
      if (!this._data?.entry_id || (this._failures > 1 && this._running)) this._receive(null, { missing: true });
      this._retry = setTimeout(() => {
        this._retry = null;
        this._connect();
      }, 30000);
    });
  }

  _unsubscribe() {
    this._cancelRetry();
    const sub = this._sub;
    this._sub = null;
    if (sub && this._live()) sub.then((unsubscribe) => unsubscribe()).catch(() => undefined);
  }

  _merge(data) {
    const extra = this.popup && this._public;
    if (!extra || !data?.entry_id) return data;
    const show = this._config;
    const announcements = show.show_announcements && Array.isArray(extra.announcements) ? extra.announcements : null;
    const conversations = show.show_conversations && Array.isArray(extra.conversations) ? extra.conversations : null;
    if (data.access === false) {
      if (!announcements && !conversations) return data;
      return { ...extra, entry_id: data.entry_id, state: "loaded", announcements, conversations };
    }
    return { ...data, conversations: data.conversations ?? conversations };
  }

  _receive(sub, payload) {
    if (sub && sub !== this._sub) return;
    if (sub) this._failures = 0;
    this._data = payload && typeof payload === "object" ? payload : null;
    this._render();
  }

  async _render() {
    const hass = this._hass;
    if (!hass || !this.isConnected) return;
    const run = ++this._run;
    const data = this._merge(this._data);
    const show = this._config;
    let state = data?.state;
    if (!data || (data.missing && !this._running)) state = "loading";
    else if (data.missing || !data.entry_id) state = "none";
    else if (data.access === false) state = "noAccess";
    const content = state === "loaded" || state === "failed";
    const parts = content && [data.entry_id, data.own, data.entities, data.children, data.recent_photos];
    const lists = content && [Array.isArray(data.announcements), Array.isArray(data.conversations)];
    const layout = JSON.stringify([content, parts, lists, show, this.popup, regional(hass)]);
    if (layout !== this._layout) {
      const helpers = content ? await cardHelpers().catch(() => null) : null;
      if (run !== this._run) return;
      this._layout = layout;
      this._build(content ? data : null, helpers);
    }
    this._fill(state, data);
  }

  _build(data, helpers) {
    const hass = this._hass;
    const t = texts(hass);
    const show = this._config;
    const cards = [];
    const grid = el("div", { className: "grid" });
    const card = (config) => {
      if (!helpers || !config) return null;
      const element = helpers.createCardElement(config);
      element.hass = hass;
      cards.push(element);
      return element;
    };
    const block = (...items) => {
      const nodes = items.map((item) => (item instanceof Node ? item : card(item))).filter(Boolean);
      if (nodes.length) grid.append(el("div", { className: "block" }, ...nodes));
    };
    const ids = Object.fromEntries(Object.entries(data?.entities || {}).map(([key, id]) => [key, valid(id)]));
    const none = { action: "none" };
    const closed = { tap_action: none, icon_tap_action: none, hold_action: none };
    const tile = (entity, name, open = true) =>
      entity && !this.popup && { type: "tile", entity, name, ...(open ? {} : closed) };
    const shown = (entity, config) => ({
      type: "conditional",
      conditions: [{ condition: "state", entity, state_not: ["unknown", "unavailable"] }],
      card: config,
    });
    const picture = (entity, ratio) =>
      shown(entity, { type: "picture-entity", entity, show_name: false, show_state: false, aspect_ratio: ratio });
    const list = () => el("div", { className: "list", role: "list" });
    const chat = this._chat;
    const draft = chat && !chat.button.disabled && chat.text.value;
    if (draft) this._draft = { entry: chat.entry, room: chat.select.value, text: draft };
    this._list = this._rooms = this._chat = null;
    if (data) {
      if (show.show_announcements && Array.isArray(data.announcements)) {
        this._list = list();
        block(tile(ids.unread_announcements, t.unreadAnnouncements), el("ha-card", {}, this._list));
      }
      for (const child of objects(show.show_children && data.children)) {
        const photo = valid(child.photo);
        const group = valid(child.class);
        const top = [photo && picture(photo, "1:1"), group && { type: "tile", entity: group }].filter(Boolean);
        block(top.length && { type: "grid", columns: 2, square: false, cards: top });
      }
      const photos = strings(show.show_photos && data.recent_photos).filter(valid);
      if (photos.length) {
        block(
          shown(photos[0], { type: "heading", heading: t.recentPhotos, icon: "mdi:image-multiple" }),
          { type: "grid", columns: 2, square: false, cards: photos.map((photo) => picture(photo, "4:3")) },
        );
      }
      if (show.show_conversations) {
        this._rooms = Array.isArray(data.conversations) ? list() : null;
        const note = this.popup && el("div", { className: "text", textContent: data.own ? t.roomsOff : t.roomsOwn });
        const body = this._rooms || note;
        const counter = tile(ids.unread_conversations, t.unreadConversations, show.show_reply);
        const form = this._rooms && data.own && show.show_reply && this._form(t, data.entry_id);
        block(counter, body && el("ha-card", {}, body), form);
      }
      if (show.show_calendar) {
        const school = ids.school_calendar;
        block(
          tile(ids.next_event, t.nextEvent),
          school && { type: "calendar", entities: [school], initial_view: "dayGridMonth" },
        );
      }
    }
    this._cards = cards;
    if (!this._list) this._drop();
    this._head.replaceChildren(...(show.title ? [el("h2", { textContent: show.title })] : []));
    this._main.replaceChildren(grid);
  }

  _form(t, entry) {
    const select = el("select");
    const text = el("textarea", { maxLength: 1000, rows: 3 });
    const status = el("span", { role: "status" });
    const button = el("button", { textContent: t.send });
    const label = (name, control) => el("label", {}, name, control);
    const row = el("div", { className: "row" }, status, button);
    const fields = el("div", { className: "form" }, label(t.conversation, select), label(t.message, text), row);
    const form = el("ha-card", { header: t.reply, hidden: true }, fields);
    this._chat = { select, text, form, entry, button, key: "" };
    button.onclick = async () => {
      button.disabled = true;
      status.textContent = "";
      status.className = "";
      status.setAttribute("role", "status");
      try {
        const data = { config_entry_id: entry, conversation_id: select.value, message: text.value };
        await this._hass.callService("parro_ha", "send_message", data, undefined, false);
        text.value = "";
        status.textContent = t.sent;
      } catch (err) {
        status.className = "error";
        status.setAttribute("role", "alert");
        status.textContent = await this._explain(err, t);
      }
      button.disabled = false;
    };
    return form;
  }

  _fill(state, data) {
    const hass = this._hass;
    const t = texts(hass);
    const time = format(hass, data?.updated, TIME).replace(/\.$/, "");
    const message = state === "loaded" ? "" : fill(t[state] || "", { time });
    this._statusCard.className = message ? "status" : "status empty";
    if (this._status.textContent !== message) this._status.textContent = message;
    this._status.setAttribute("aria-busy", String(state === "loading"));
    if (!data?.entry_id) return;
    this._fillAnnouncements(data, t);
    this._fillConversations(data, t);
  }

  _fillAnnouncements(data, t) {
    const list = this._list;
    if (!list) return;
    const show = this._config;
    const items = objects(data.announcements).slice(0, show.announcement_count);
    const photos = show.show_photos && data.announcement_photos === true;
    const key = JSON.stringify([data.entry_id, items, photos]);
    if (key === list.key) return;
    list.key = key;
    const used = new Map();
    const focused = this.shadowRoot.activeElement?.key;
    this._observer?.disconnect();
    this._pending.clear();
    const nodes = items.map((item) => this._announcement(item, data.entry_id, t, used, photos));
    const empty = show.group ? fill(t.noGroup, { group: show.group }) : t.noAnnouncements;
    const none = el("div", { className: "item", role: "listitem", textContent: empty });
    list.replaceChildren(...(nodes.length ? nodes : [none]));
    used.get(focused)?.focus({ preventScroll: true });
    this._tiles = used;
    if (this._dialog?.open && used.get(this._opener)?.total !== this._total) this._dialog.close();
    this._revoke(used);
  }

  _revoke(used, photos = this._photos) {
    for (const [key, photo] of photos) {
      if (used.has(key)) continue;
      photos.delete(key);
      photo.then((url) => url && URL.revokeObjectURL(url));
    }
  }

  _drop() {
    this._observer?.disconnect();
    this._pending.clear();
    this._revoke(new Set());
    if (this._dialog?.open) this._dialog.close();
  }

  _announcement(item, entry, t, used, photos) {
    const total = Number.isInteger(item.photos) ? item.photos : 0;
    const count = photos || total < 1 ? "" : total === 1 ? t.onePhoto : fill(t.photoCount, { count: total });
    const meta = [strings(item.groups).join(", "), item.author, format(this._hass, item.published, TIME), count];
    const extra = item.read === false ? ` (${t.new})` : "";
    const title = item.title || t.announcement;
    const node = this._item(title, extra, meta, item.text, `a${item.id}`, t);
    if (photos && total > 0 && /^[A-Za-z0-9]+$/.test(entry) && Number.isInteger(item.id)) {
      const path = `${entry}/${item.id}`;
      const tiles = Array.from({ length: Math.min(total, PHOTOS) }, (_, index) => {
        const tile = this._image(`${path}/${index}`, fill(t.photo, { number: index + 1, total }), t, used);
        return Object.assign(tile, { total, onclick: () => this._slideshow(path, index, total, title) });
      });
      const more = total > PHOTOS && `+${total - PHOTOS}`;
      if (more) tiles[PHOTOS - 1].append(el("span", { className: "more", "aria-hidden": "true", textContent: more }));
      node.append(el("div", { className: "photos" }, ...tiles));
    }
    return node;
  }

  _item(title, extra, meta, value, key, t) {
    const text = typeof value === "string" ? value : "";
    const chars = Array.from(text);
    const short = chars.length > PREVIEW ? `${chars.slice(0, PREVIEW).join("").trimEnd()}...` : text;
    const body = el("div", { className: "body", textContent: short });
    const line = meta.filter(Boolean).join(", ");
    const head = el("h3", {}, el("span", { className: "name", textContent: title }), extra);
    const node = el("div", { className: "item", role: "listitem" }, head);
    if (line) node.append(el("div", { className: "meta", textContent: line }));
    if (text) node.append(body);
    if (short !== text) {
      const button = el("button", { className: "link" });
      body.id = `parro-${++this._ids}`;
      button.setAttribute("aria-controls", body.id);
      const toggle = (open) => {
        this._open[open ? "add" : "delete"](key);
        body.textContent = open ? text : short;
        button.textContent = open ? t.less : t.more;
        button.setAttribute("aria-expanded", String(open));
      };
      button.onclick = () => toggle(!this._open.has(key));
      toggle(this._open.has(key));
      node.append(button);
    }
    return node;
  }

  _load(path, photos = this._photos) {
    let photo = photos.get(path);
    if (!photo) {
      photo = this._hass
        .fetchWithAuth(`/api/parro_ha/photo/${path}`)
        .then(async (response) => {
          const blob = response.ok ? await response.blob() : null;
          return blob && /^image\//.test(blob.type) && blob.size < 8000000 ? URL.createObjectURL(blob) : null;
        })
        .catch(() => null);
      photos.set(path, photo);
    }
    return photo.then((url) => {
      const current = photos.get(path) === photo;
      if (!url && current) photos.delete(path);
      return current && url;
    });
  }

  _image(key, alt, t, used) {
    const image = el("img", { alt });
    const tile = el("button", { className: "photo", key }, image);
    const show = (url) => {
      if (url) image.src = url;
      else {
        tile.setAttribute("aria-label", `${alt}, ${t.noPhoto}`);
        image.replaceWith(el("span", { textContent: t.noPhoto }));
      }
    };
    used.set(key, tile);
    this._observer ||= new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const start = entry.isIntersecting && this._pending.get(entry.target);
        if (!start) continue;
        this._pending.delete(entry.target);
        this._observer.unobserve(entry.target);
        start();
      }
    });
    this._pending.set(image, () => this._load(key).then(show));
    this._observer.observe(image);
    return tile;
  }

  _slideshow(path, start, total, title) {
    if (!this._dialog) this.shadowRoot.append((this._dialog = el("dialog", { tabIndex: -1 })));
    const dialog = this._dialog;
    if (!dialog.showModal) return;
    const t = texts(this._hass);
    const photos = new Map();
    const load = (number) => this._load(`${path}/${number}?size=full`, photos);
    const opener = `${path}/${start}`;
    const image = el("img", { draggable: false });
    const note = el("p", { role: "status" });
    const counter = el("span", { "aria-live": "polite" });
    const button = (icon, label, onclick) => el("button", { "aria-label": label, onclick }, el("ha-icon", { icon }));
    const close = button("mdi:close", t.close, () => dialog.close());
    const previous = button("mdi:chevron-left", t.previous, () => go(index - 1));
    const next = button("mdi:chevron-right", t.next, () => go(index + 1));
    let index, down, up, x, y;
    const go = (number) => {
      if (number < 0 || number >= total) return;
      const focused = this.shadowRoot.activeElement;
      index = number;
      counter.textContent = image.alt = fill(t.photo, { number: number + 1, total });
      previous.disabled = number === 0;
      next.disabled = number === total - 1;
      if (focused?.disabled) dialog.focus();
      [image.hidden, note.hidden, note.textContent] = [true, false, ""];
      load(number).then((url) => {
        if (number !== index) return;
        [image.hidden, note.hidden, note.textContent] = [!url, Boolean(url), url ? "" : t.noPhoto];
        if (!url) return;
        image.src = url;
        if (number + 1 < total) load(number + 1);
      });
    };
    image.onpointerup = note.onpointerup = (event) => {
      const [dx, dy] = [Math.abs(event.clientX - x), Math.abs(event.clientY - y)];
      if (event.isPrimary && event.target === down && dx >= 40 && dx > dy) go(index + Math.sign(x - event.clientX));
    };
    const stop = (event) => {
      event.stopPropagation();
      if (event.type === "wheel") event.preventDefault();
      if (event.type === "pointerdown") [down, x, y] = [event.isPrimary && event.target, event.clientX, event.clientY];
      if (event.type === "pointerup") up = event.target;
    };
    for (const type of GESTURES.split(" ")) dialog[`on${type}`] = stop;
    dialog.setAttribute("aria-label", title);
    dialog.replaceChildren(image, note, el("div", { className: "bar" }, close, previous, counter, next));
    dialog.onclick = (event) => {
      if (event.target === dialog && down === dialog && up === dialog && event.detail === 1) dialog.close();
    };
    dialog.onkeydown = (event) => {
      event.stopPropagation();
      const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
      if (step) go(index + step);
      if (SCROLLS.includes(event.key) || (event.key === " " && event.target === dialog)) event.preventDefault();
    };
    dialog.onclose = () => {
      this._revoke(new Set(), photos);
      this._tiles.get(opener)?.focus({ preventScroll: true });
    };
    [this._opener, this._total] = [opener, total];
    go(start);
    dialog.showModal();
  }

  _fillConversations(data, t) {
    const rooms = objects(data.conversations);
    const list = this._rooms;
    const shown = JSON.stringify(rooms.slice(0, 10));
    if (list && shown !== list.key) {
      list.key = shown;
      const row = (room) => {
        const meta = [room.last_sender, format(this._hass, room.last_message_at, TIME)];
        const extra = room.unread ? ` (${room.unread} ${t.unread})` : "";
        return this._item(room.name || t.conversation, extra, meta, room.preview, `c${room.id}`, t);
      };
      const items = rooms.slice(0, 10).map(row);
      const empty = el("div", { className: "item", role: "listitem", textContent: t.noConversations });
      list.replaceChildren(...(items.length ? items : [empty]));
    }
    const chat = this._chat;
    if (!chat) return;
    const allowed = rooms.filter((room) => room.can_reply === true && Number.isInteger(room.id));
    const key = JSON.stringify(allowed.map((room) => [room.id, room.name]));
    if (key === chat.key) return;
    chat.key = key;
    chat.form.hidden = !allowed.length;
    const draft = this._draft?.entry === chat.entry ? this._draft : null;
    this._draft = null;
    const value = draft ? draft.room : chat.select.value;
    const option = (room) => el("option", { value: String(room.id), textContent: room.name || t.conversation });
    chat.select.replaceChildren(...allowed.map(option));
    if (allowed.some((room) => String(room.id) === value)) {
      chat.select.value = value;
      if (draft) chat.text.value = draft.text;
    } else chat.text.value = "";
  }

  async _explain(err, t) {
    const { translation_domain: domain, translation_key: key, translation_placeholders: values } = err || {};
    let text;
    try {
      const localize = domain && key && (await this._hass.loadBackendTranslation("exceptions", domain));
      text = localize && localize(`component.${domain}.exceptions.${key}.message`, values || {});
    } catch {}
    return text || (typeof err?.message === "string" && err.message) || t.lost;
  }
}

class ParroMoreInfo extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  set stateObj(stateObj) {
    this._state = stateObj;
    this._update();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _update() {
    const hass = this._hass;
    if (!hass) return;
    const item = hass.entities?.[this._state?.entity_id];
    const kind = item?.translation_key;
    if (kind === "next_event") {
      this._card = null;
      this._agenda(hass);
      return;
    }
    this._key = null;
    if (!this._card) {
      this._card = document.createElement("parro-ha-card");
      this._card.popup = true;
      this.shadowRoot.replaceChildren(this._card);
    }
    const chats = kind === "unread_conversations";
    const parts = chats ? ["show_conversations", "show_reply"] : ["show_announcements", "show_photos"];
    const device = hass.devices?.[item?.device_id];
    const account = device?.config_entry_id || device?.config_entries?.[0] || "unknown";
    const mine = Object.values(hass.entities || {}).filter((entry) => item && entry.device_id === item.device_id);
    const find = (key) => mine.find((entry) => entry.translation_key === key)?.entity_id;
    const attributes = (key) => hass.states?.[find(key)]?.attributes;
    const recent = mine.filter((entry) => entry.translation_key === "recent_photo").map((entry) => entry.entity_id);
    this._card.setConfig({ ...Object.fromEntries(PARTS.map((part) => [part, parts.includes(part)])), account });
    this._card.public = {
      announcements: attributes("latest_announcement")?.announcements,
      conversations: attributes("unread_conversations")?.conversations,
      recent_photos: recent.sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
    };
    this._card.hass = hass;
  }

  _agenda(hass) {
    const t = texts(hass);
    const upcoming = this._state?.attributes?.upcoming;
    const items = objects(upcoming);
    const key = JSON.stringify([items, Array.isArray(upcoming), regional(hass)]);
    if (key === this._key) return;
    this._key = key;
    const when = (event) => {
      const options = event.all_day ? DAY : { ...DAY, hour: "2-digit", minute: "2-digit" };
      const date = format(hass, event.start, options, new Date(event.end) - (event.all_day ? 1 : 0));
      return event.all_day ? `${date}, ${t.allDay}` : date;
    };
    const row = (event) => {
      const groups = strings(event.groups);
      return el(
        "div",
        { className: "item", role: "listitem" },
        el("h3", { className: "name", textContent: event.title || t.event }),
        el("div", { className: "meta", textContent: [when(event), groups.join(", ")].filter(Boolean).join(", ") }),
      );
    };
    const none = el("div", { className: "item", role: "listitem", textContent: t.noEvents });
    const list = el("div", { className: "list", role: "list" }, ...(items.length ? items.map(row) : [none]));
    const parts = Array.isArray(upcoming) ? [el("style", { textContent: STYLE }), el("ha-card", {}, list)] : [];
    this.shadowRoot.replaceChildren(...parts);
  }
}

const register = () => {
  if (!customElements.get("parro-ha-more-info")) customElements.define("parro-ha-more-info", ParroMoreInfo);
  if (customElements.get("parro-ha-card")) return;
  customElements.define("parro-ha-card", ParroCard);
  (window.customCards = window.customCards || []).push({
    type: "parro-ha-card",
    name: "Parro",
    description: "Announcements, photos, conversations and calendars of the Parro account of whoever views it.",
  });
};

if (customElements.get("home-assistant")) register();
else customElements.whenDefined("home-assistant").then(register);
