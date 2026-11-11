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
`;
const TEXTS = {
  en: {
    unreadAnnouncements: "Unread announcements",
    unreadConversations: "Unread conversations",
    nextEvent: "Next event",
    recentPhotos: "Recent photos",
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
    none: "Ask an administrator to add Parro and sign in with your own Parro account.",
  },
  nl: {
    unreadAnnouncements: "Ongelezen berichten",
    unreadConversations: "Ongelezen gesprekken",
    nextEvent: "Volgende activiteit",
    recentPhotos: "Recente foto's",
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
    none: "Vraag een beheerder om Parro toe te voegen en meld je aan met je eigen Parro-account.",
  },
};

const el = (tag, props, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const valid = (id) => (typeof id === "string" && /^[a-z0-9_]+\.[a-z0-9_]+$/.test(id) ? id : null);
const quote = JSON.stringify;
const ESCAPES = [["<", "&lt;"], [">", "&gt;"], ["[", "&#91;"], ["_", "&#95;"], ["*", "&#42;"], ["`", "&#96;"], ["\\\\", "&#92;"], [":", "&#58;"], ["@", "&#64;"], ["www.", "www&#46;"]];
const esc = (value) => `(${value} or '')` + ESCAPES.map(([from, to]) => ` | replace('${from}', '${to}')`).join("");
const announcements = (id, t) =>
  `{%- for item in state_attr('${id}', 'announcements') or [] %}\n\n**{{ ${esc("item.title")} }}**` +
  `{{ ${quote(` (${t.new})`)} if not item.read }}\n_{{ ${esc("item.group")} }}, {{ ${esc("item.author")} }}` +
  `{% if item.published %}, {{ as_timestamp(item.published) | timestamp_custom(${quote(t.date)}) }}{% endif %}` +
  `{% if item.photos %}, {{ item.photos }} {{ ${quote(t.photo)} if item.photos == 1 else ${quote(t.photos)} }}` +
  `{% endif %}_\n{{ ${esc("(item.text or '') | truncate(280)")} }}\n{%- else %}\n${t.noAnnouncements}\n{%- endfor %}`;
const conversations = (id, t) =>
  `{%- for item in state_attr('${id}', 'conversations') or [] %}\n\n` +
  `**{{ ${esc(`item.name or ${quote(t.conversation)}`)} }}**{{ " (" ~ item.unread ~ ${quote(` ${t.unread})`)} ` +
  `if item.unread }}\n{% if item.last_sender %}_{{ ${esc("item.last_sender")} }}:_ {% endif %}` +
  `{{ ${esc("item.preview")} }}\n{%- else %}\n${t.noConversations}\n{%- endfor %}`;

class ParroCard extends HTMLElement {
  constructor() {
    super();
    this._cards = [];
    this._user = null;
    this.attachShadow({ mode: "open" });
  }

  setConfig() {}

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
    this._hass = hass;
    const user = hass.user?.id || "";
    if (user !== this._user && !this._busy && this.isConnected) this._load(user);
    for (const card of this._cards) card.hass = hass;
    this._sync();
  }

  async _load(user) {
    this._busy = true;
    this._user = user;
    let answer;
    try {
      answer = await this._hass.callWS({ type: "parro_ha/account" });
      if (answer || this._hass.config.state === "RUNNING") {
        const json = JSON.stringify(answer);
        if (json !== this._json) await this._build(answer);
        this._json = json;
      }
    } catch {
      answer = null;
    }
    this._busy = false;
    if (!answer) {
      setTimeout(() => {
        this._user = null;
        if (this.isConnected) this.hass = this._hass;
      }, 30000);
    }
    this.hass = this._hass;
  }

  async _build(answer) {
    const helpers = await window.loadCardHelpers();
    const hass = this._hass;
    const t = TEXTS[/^nl/.test(hass.locale?.language || hass.language) ? "nl" : "en"];
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
    const tile = (entity, name) => entity && { type: "tile", entity, name };
    const picture = (entity, ratio) => ({
      type: "picture-entity",
      entity,
      show_name: false,
      show_state: false,
      aspect_ratio: ratio,
    });
    this._chat = null;
    if (answer) {
      const latest = ids.latest_announcement;
      block(
        tile(ids.unread_announcements, t.unreadAnnouncements),
        latest && { type: "markdown", content: announcements(latest, t) },
      );
      for (const child of answer.children || []) {
        const photo = valid(child?.photo);
        const group = valid(child?.class);
        const top = [photo && picture(photo, "1:1"), group && { type: "tile", entity: group }].filter(Boolean);
        block(top.length && { type: "grid", columns: 2, square: false, cards: top });
      }
      const photos = (answer.recent_photos || []).map(valid).filter(Boolean);
      if (photos.length) {
        block(
          { type: "heading", heading: t.recentPhotos, icon: "mdi:image-multiple" },
          { type: "grid", columns: 2, square: false, cards: photos.map((photo) => picture(photo, "4:3")) },
        );
      }
      const chats = ids.unread_conversations;
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
          items: null,
          key: "",
          list: card({ type: "markdown", content: conversations(chats, t) }),
          form: el("ha-card", { header: t.reply, hidden: true }, form),
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
            status.textContent = err?.message || String(err);
          }
          button.disabled = false;
        };
        block(tile(chats, t.unreadConversations), this._chat.list, this._chat.form);
      }
      const school = ids.school_calendar;
      block(
        tile(ids.next_event, t.nextEvent),
        school && { type: "calendar", entities: [school], initial_view: "dayGridMonth" },
      );
    }
    this._cards = cards;
    const content = answer ? grid : el("ha-card", {}, el("div", { className: "text", textContent: t.none }));
    this.shadowRoot.replaceChildren(el("style", { textContent: STYLE }), content);
  }

  _sync() {
    const chat = this._chat;
    const items = chat && this._hass.states[chat.id]?.attributes.conversations;
    if (!chat || items === chat.items) return;
    chat.items = items;
    chat.list.hidden = !Array.isArray(items);
    const rooms = (Array.isArray(items) ? items : []).filter((item) => item?.can_reply === true);
    const key = JSON.stringify(rooms.map((item) => [item.id, item.name]));
    if (key === chat.key) return;
    chat.key = key;
    chat.form.hidden = !rooms.length;
    const value = chat.select.value;
    const option = (item) => el("option", { value: String(item.id), textContent: item.name || chat.t.conversation });
    chat.select.replaceChildren(...rooms.map(option));
    if (rooms.some((item) => String(item.id) === value)) chat.select.value = value;
  }
}

if (!customElements.get("parro-card")) {
  customElements.define("parro-card", ParroCard);
  (window.customCards = window.customCards || []).push({
    type: "parro-card",
    name: "Parro",
    description: "Announcements, conversations, calendars and photos of the Parro account of whoever views it.",
  });
}
