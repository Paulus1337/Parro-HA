const STYLE = `
:host { display: block; }
.grid { columns: 340px 3; column-gap: 8px; orphans: 1; widows: 1; }
.block {
  display: inline-grid; grid-template-columns: minmax(0, 1fr); gap: 8px; width: 100%; margin-bottom: 8px;
  vertical-align: top;
}
[hidden] { display: none !important; }
.text { padding: 16px; }
.form { display: grid; gap: 12px; padding: 0 16px 16px; }
label { display: grid; gap: 4px; color: var(--secondary-text-color); }
select, textarea {
  box-sizing: border-box; width: 100%; padding: 8px; border: 1px solid var(--divider-color); border-radius: 8px;
  background: var(--card-background-color); color: var(--primary-text-color); font: inherit;
}
textarea { resize: vertical; }
.row { display: flex; align-items: center; gap: 12px; }
.row span { flex: 1; }
.error { color: var(--error-color); }
button {
  padding: 8px 20px; border: 0; border-radius: 18px; background: var(--primary-color);
  color: var(--text-primary-color); font: inherit; cursor: pointer;
}
button:disabled { opacity: 0.5; cursor: default; }
.title { padding: 0 4px 12px; font-size: 24px; line-height: 32px; color: var(--ha-card-header-color, inherit); }
`;
const TEXTS = {
  en: {
    unreadAnnouncements: "Unread announcements",
    unreadConversations: "Unread conversations",
    nextEvent: "Next event",
    recentPhotos: "Recent photos",
    announcement: "Announcement",
    new: "new",
    photo: "photo",
    photos: "photos",
    unread: "unread",
    date: "%d %b %H:%M",
    noAnnouncements: "No announcements yet.",
    noConversations: "No conversations.",
    conversation: "Conversation",
    reply: "Reply",
    message: "Message",
    send: "Send",
    sent: "Sent.",
    lost: "The connection to Home Assistant was lost. Check the conversation in Parro before you send it again.",
    none: "Ask an administrator to add Parro and sign in with your own Parro account.",
    show_announcements: "Announcements",
    show_children: "Children",
    show_photos: "Recent photos",
    show_conversations: "Conversations",
    show_reply: "Reply form",
    show_calendar: "Calendar",
    title: "Title",
    announcement_count: "Number of announcements",
    group: "Group",
    details: "Turn on Show conversation details in the Parro options to see the conversations here.",
  },
  nl: {
    unreadAnnouncements: "Ongelezen berichten",
    unreadConversations: "Ongelezen gesprekken",
    nextEvent: "Volgende activiteit",
    recentPhotos: "Recente foto's",
    announcement: "Bericht",
    new: "nieuw",
    photo: "foto",
    photos: "foto's",
    unread: "ongelezen",
    date: "%d-%m %H:%M",
    noAnnouncements: "Nog geen berichten.",
    noConversations: "Geen gesprekken.",
    conversation: "Gesprek",
    reply: "Antwoorden",
    message: "Bericht",
    send: "Versturen",
    sent: "Verstuurd.",
    lost: "De verbinding met Home Assistant is verbroken. Kijk in het gesprek in Parro voordat je opnieuw verstuurt.",
    none: "Vraag een beheerder om Parro toe te voegen en meld je aan met je eigen Parro-account.",
    show_announcements: "Berichten",
    show_children: "Kinderen",
    show_photos: "Recente foto's",
    show_conversations: "Gesprekken",
    show_reply: "Antwoordformulier",
    show_calendar: "Agenda",
    title: "Titel",
    announcement_count: "Aantal berichten",
    group: "Groep",
    details: "Zet Gespreksdetails tonen aan in de Parro-opties om de gesprekken hier te zien.",
  },
};

const el = (tag, props, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const valid = (id) => (typeof id === "string" && /^[a-z0-9_]+\.[a-z0-9_]+$/.test(id) ? id : null);
const quote = JSON.stringify;
const texts = (hass) => TEXTS[/^nl/.test(hass?.locale?.language || hass?.language || "") ? "nl" : "en"];
const PARTS = ["announcements", "children", "photos", "conversations", "reply", "calendar"].map((p) => `show_${p}`);
const DEFAULTS = Object.fromEntries(PARTS.map((part) => [part, true]));
const cardHelpers = async () => {
  if (!window.loadCardHelpers) {
    const resolver = document.createElement("partial-panel-resolver");
    await resolver._getRoutes([{ component_name: "lovelace", url_path: "parro-ha" }]).routes["parro-ha"].load();
  }
  return window.loadCardHelpers();
};
const ESCAPES = [
  ["&", "&amp;"], ["<", "&lt;"], [">", "&gt;"], ["[", "&#91;"], ["_", "&#95;"], ["*", "&#42;"], ["`", "&#96;"],
  ["~", "&#126;"], ["\\\\", "&#92;"], [":", "&#58;"], ["@", "&#64;"], ["www.", "www&#46;"], ["\\r\\n", "<br>"],
  ["\\r", "<br>"], ["\\n", "<br>"],
];
const esc = (value) => `(${value} or '')` + ESCAPES.map(([from, to]) => ` | replace('${from}', '${to}')`).join("");
const literal = (value) => {
  const hex = (c) => `\\U${c.codePointAt(0).toString(16).padStart(8, "0")}`;
  return `"${[...value].map((c) => (/[A-Za-z0-9 ]/.test(c) ? c : hex(c))).join("")}"`;
};
const announcements = (id, t, { group, announcement_count: count } = {}) =>
  `{%- for item in ((state_attr('${id}', 'announcements') or [])` +
  `${group ? ` | selectattr('groups', 'defined') | selectattr('groups', 'contains', ${literal(group)})` : ""}` +
  ` | list)${count ? `[:${count}]` : ""} %}` +
  `{% set meta = [(item.get('groups') or [item.group]) | join(', '), item.author, ` +
  `as_timestamp(item.published) | timestamp_custom(${quote(t.date)}) if item.published else '', ` +
  `item.photos ~ ' ' ~ (${quote(t.photo)} if item.photos == 1 else ${quote(t.photos)}) if item.photos else ''] ` +
  `| select | join(', ') %}\n\n**{{ ${esc(`item.title or ${quote(t.announcement)}`)} }}**` +
  `{{ ${quote(` (${t.new})`)} if not item.read }}{% if meta %}<br>_{{ ${esc("meta")} }}_{% endif %}` +
  `{% if item.text %}<br>{{ ${esc("item.text | truncate(280)")} }}{% endif %}\n` +
  `{%- else %}\n${t.noAnnouncements}\n{%- endfor %}`;
const conversations = (id, t) =>
  `{%- for item in state_attr('${id}', 'conversations') or [] %}\n\n` +
  `**{{ ${esc(`item.name or ${quote(t.conversation)}`)} }}**{{ " (" ~ item.unread ~ ${quote(` ${t.unread})`)} ` +
  `if item.unread }}<br>{% if item.last_sender %}_{{ ${esc("item.last_sender")} }}:_ {% endif %}` +
  `{{ ${esc("item.preview")} }}\n{%- else %}\n${t.noConversations}\n{%- endfor %}`;

class ParroCard extends HTMLElement {
  constructor() {
    super();
    this._cards = [];
    this._user = null;
    this._config = DEFAULTS;
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    const options = { ...DEFAULTS, ...config };
    const count = options.announcement_count;
    if (
      PARTS.some((part) => typeof options[part] !== "boolean") ||
      ["title", "group"].some((key) => options[key] !== undefined && typeof options[key] !== "string") ||
      (count !== undefined && !(Number.isInteger(count) && count >= 1 && count <= 20))
    ) {
      throw new Error(`${PARTS.join(", ")}: true or false; title, group: text; announcement_count: 1 to 20`);
    }
    if (JSON.stringify(options) === JSON.stringify(this._config)) return;
    this._config = options;
    this._user = null;
    if (this._hass) this.hass = this._hass;
  }

  set account(account) {
    if (JSON.stringify(account) === JSON.stringify(this._account)) return;
    this._account = account;
    this._user = null;
    if (this._hass) this.hass = this._hass;
  }

  static async getConfigForm() {
    const hass = document.querySelector("home-assistant")?.hass;
    const t = texts(hass);
    let groups = [];
    try {
      const { entities, children } = (await hass.callWS({ type: "parro_ha/account" })) || {};
      const items = hass.states[entities?.latest_announcement]?.attributes.announcements;
      const classes = (children || []).map((child) => hass.states[child?.class]?.state);
      groups = [...(Array.isArray(items) ? items.flatMap((item) => item?.groups || []) : []), ...classes];
    } catch {
      groups = [];
    }
    const real = (group) => typeof group === "string" && group && !["unknown", "unavailable"].includes(group);
    const options = [...new Set(groups.filter(real))].sort();
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        { name: "announcement_count", selector: { number: { min: 1, max: 20, mode: "box" } } },
        { name: "group", selector: { select: { options, custom_value: true, mode: "dropdown" } } },
        ...PARTS.map((name) => ({ name, default: true, selector: { boolean: {} } })),
      ],
      computeLabel: (schema) => t[schema.name],
    };
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: "full" };
  }

  static getStubConfig() {
    return {};
  }

  connectedCallback() {
    if (this._hass) this.hass = this._hass;
  }

  set hass(hass) {
    if (this._hass && hass.entities !== this._hass.entities) this._user = null;
    this._hass = hass;
    const user = hass.user?.id || "";
    if (user !== this._user && !this._busy && this.isConnected) this._load(user);
    for (const card of this._cards) card.hass = hass;
    this._sync();
  }

  async _load(user) {
    this._busy = true;
    this._user = user;
    clearTimeout(this._retry);
    let answer;
    try {
      answer = await this._hass.callWS({ type: "parro_ha/account" });
      const own = this._account;
      if (own && answer?.entry_id !== own.entry_id) answer = own.entities ? { ...own, foreign: true } : null;
      if (answer || this._hass.config.state === "RUNNING") {
        const json = JSON.stringify([answer, this._config]);
        if (json !== this._json) await this._build(answer);
        this._json = json;
      }
    } catch {
      answer = null;
    }
    this._busy = false;
    if (!answer) {
      this._retry = setTimeout(() => {
        this._user = null;
        if (this.isConnected) this.hass = this._hass;
      }, 30000);
    }
    this.hass = this._hass;
  }

  async _build(answer) {
    const helpers = await cardHelpers();
    const hass = this._hass;
    const t = texts(hass);
    const show = this._config;
    const cards = [];
    const grid = el("div", { className: "grid" });
    const card = (config) => {
      const element = helpers.createCardElement(config);
      element.hass = hass;
      cards.push(element);
      return element;
    };
    const block = (...items) => {
      const nodes = items.filter(Boolean).map((item) => (item instanceof Node ? item : card(item)));
      if (nodes.length) grid.append(el("div", { className: "block" }, ...nodes));
    };
    const ids = Object.fromEntries(Object.entries(answer?.entities || {}).map(([key, id]) => [key, valid(id)]));
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
    this._chat = null;
    if (answer) {
      if (show.show_announcements) {
        const latest = ids.latest_announcement;
        block(
          tile(ids.unread_announcements, t.unreadAnnouncements),
          latest && { type: "markdown", content: announcements(latest, t, show) },
        );
      }
      for (const child of show.show_children ? answer.children || [] : []) {
        const photo = valid(child?.photo);
        const group = valid(child?.class);
        const top = [photo && picture(photo, "1:1"), group && { type: "tile", entity: group }].filter(Boolean);
        block(top.length && { type: "grid", columns: 2, square: false, cards: top });
      }
      const photos = show.show_photos ? (answer.recent_photos || []).map(valid).filter(Boolean) : [];
      if (photos.length) {
        block(
          shown(photos[0], { type: "heading", heading: t.recentPhotos, icon: "mdi:image-multiple" }),
          { type: "grid", columns: 2, square: false, cards: photos.map((photo) => picture(photo, "4:3")) },
        );
      }
      const chats = show.show_conversations && ids.unread_conversations;
      if (chats) {
        const select = el("select");
        const text = el("textarea", { maxLength: 1000, rows: 3 });
        const status = el("span", { role: "status" });
        const button = el("button", { textContent: t.send });
        const label = (name, control) => el("label", {}, name, control);
        const row = el("div", { className: "row" }, status, button);
        const form = el("div", { className: "form" }, label(t.conversation, select), label(t.message, text), row);
        this._chat = {
          id: chats,
          t,
          select,
          text,
          items: null,
          key: "",
          list: el("div", { hidden: true }, card({ type: "markdown", content: conversations(chats, t) })),
          form: el("ha-card", { header: t.reply, hidden: true }, form),
          hint: this.popup && el("ha-card", { hidden: true }, el("div", { className: "text", textContent: t.details })),
        };
        button.onclick = async () => {
          button.disabled = true;
          status.className = "";
          status.textContent = "";
          try {
            const data = { conversation_id: select.value, message: text.value };
            await this._hass.callService("parro_ha", "send_message", data, undefined, false);
            text.value = "";
            status.textContent = t.sent;
          } catch (err) {
            status.className = "error";
            status.textContent = await this._explain(err, t);
          }
          button.disabled = false;
        };
        const reply = show.show_reply && !answer.foreign && this._chat.form;
        block(tile(chats, t.unreadConversations, show.show_reply), this._chat.list, this._chat.hint, reply);
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
    const content = answer ? grid : el("ha-card", {}, el("div", { className: "text", textContent: t.none }));
    const title = show.title && el("div", { className: "title", textContent: show.title });
    this.shadowRoot.replaceChildren(...[el("style", { textContent: STYLE }), title, content].filter(Boolean));
  }

  async _explain(err, t) {
    const { translation_domain: domain, translation_key: key, translation_placeholders: values } = err || {};
    let text = "";
    try {
      const localize = domain && key && (await this._hass.loadBackendTranslation("exceptions", domain));
      text = (localize && localize(`component.${domain}.exceptions.${key}.message`, values || {})) || "";
    } catch {
      text = "";
    }
    return text || (typeof err?.message === "string" && err.message) || t.lost;
  }

  _sync() {
    const chat = this._chat;
    const entity = chat && this._hass.states[chat.id];
    const items = entity?.attributes.conversations;
    const quiet = Array.isArray(items) || ["unavailable", "unknown", undefined].includes(entity?.state);
    if (chat?.hint) chat.hint.hidden = quiet;
    if (!chat || items === chat.items) return;
    chat.items = items;
    chat.list.hidden = !Array.isArray(items);
    const rooms = (Array.isArray(items) ? items : []).filter((item) => item?.can_reply === true);
    const key = JSON.stringify(rooms.map((item) => [item.id, item.name]));
    if (key === chat.key) return;
    chat.key = key;
    chat.form.hidden = !rooms.length;
    if (!rooms.length) return;
    const value = chat.select.value;
    const option = (item) => el("option", { value: String(item.id), textContent: item.name || chat.t.conversation });
    chat.select.replaceChildren(...rooms.map(option));
    if (rooms.some((item) => String(item.id) === value)) chat.select.value = value;
    else chat.text.value = "";
  }
}

class ParroMoreInfo extends HTMLElement {
  constructor() {
    super();
    this._card = document.createElement("parro-ha-card");
    this._card.popup = true;
    this.attachShadow({ mode: "open" }).append(this._card);
  }

  set stateObj(stateObj) {
    this._state = stateObj;
    if (this._hass) this.hass = this._hass;
  }

  set hass(hass) {
    this._hass = hass;
    const id = this._state?.entity_id;
    const entities = Object.values(hass.entities || {});
    const item = hass.entities?.[id];
    const attributes = this._state?.attributes || {};
    const kind = item?.translation_key || ("conversations" in attributes ? "unread_conversations" : "");
    const mine = (entry) => item && entry.device_id === item.device_id;
    const find = (key) => entities.find((entry) => mine(entry) && entry.translation_key === key)?.entity_id;
    const chats = kind === "unread_conversations";
    const key = chats ? kind : "latest_announcement";
    const parts = chats ? ["show_conversations", "show_reply"] : ["show_announcements", "show_photos"];
    this._card.setConfig(Object.fromEntries(PARTS.map((part) => [part, parts.includes(part)])));
    this._card.account = {
      entry_id: hass.devices?.[item?.device_id]?.config_entries?.[0] || null,
      entities: { [key]: item ? find(key) || null : id },
      recent_photos: entities
        .filter((entry) => mine(entry) && entry.translation_key === "recent_photo")
        .map((entry) => entry.entity_id)
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
    };
    this._card.hass = hass;
  }
}

const register = () => {
  if (!customElements.get("parro-ha-more-info")) customElements.define("parro-ha-more-info", ParroMoreInfo);
  if (customElements.get("parro-ha-card")) return;
  customElements.define("parro-ha-card", ParroCard);
  (window.customCards = window.customCards || []).push({
    type: "parro-ha-card",
    name: "Parro",
    description: "Announcements, conversations, calendars and photos of the Parro account of whoever views it.",
  });
};

if (customElements.get("home-assistant")) register();
else customElements.whenDefined("home-assistant").then(register);
