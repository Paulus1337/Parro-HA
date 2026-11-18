from __future__ import annotations

from collections.abc import Callable
from functools import partial
from http import HTTPStatus
from typing import Any

from aiohttp import web
from homeassistant.auth import EVENT_USER_REMOVED, EVENT_USER_UPDATED
from homeassistant.auth.models import User
from homeassistant.components import websocket_api
from homeassistant.components.http import KEY_HASS_USER, HomeAssistantView
from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigEntryChange,
    ConfigEntryState,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import config_validation as cv, entity_registry as er, issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.http import KEY_HASS
import voluptuous as vol

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_COUNT,
    CHAT_PREVIEW_LIMIT,
    CONF_USER,
    DOCUMENTATION,
    DOMAIN,
    FULL_TEXT_LIMIT,
    SERVICE_GET_ANNOUNCEMENTS,
    SERVICE_GET_CONVERSATIONS,
    SIGNAL_UPDATE,
    TEXT_LIMIT,
)
from .coordinator import ParroConfigEntry, ParroData, ParroOptions, entry_key
from .entity import iso, truncate
from .media import photo_cache
from .models import ParroAnnouncement

type Check = Callable[[ParroConfigEntry, User | None], bool]
ACCOUNT_KEYS = ("unread_announcements", "unread_conversations", "latest_announcement", "next_event", "school_calendar")
CHILD_KEYS = ("photo", "class", "calendar")
NO_STORE = {"Cache-Control": "private, no-store"}
ENTRY_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})
ANNOUNCEMENTS_SCHEMA = ENTRY_SCHEMA.extend({vol.Optional(ATTR_COUNT): vol.All(vol.Coerce(int), vol.Range(1, 20))})


def _options(entry: ParroConfigEntry) -> ParroOptions:
    return ParroOptions.from_mapping(entry.options)


@callback
def async_details_issue(hass: HomeAssistant, entry: ParroConfigEntry) -> None:
    if (options := _options(entry)).announcement_details or options.chat_details:
        ir.async_create_issue(
            hass,
            DOMAIN,
            f"details_{entry.entry_id}",
            is_fixable=False,
            learn_more_url=f"{DOCUMENTATION}#options",
            severity=ir.IssueSeverity.WARNING,
            translation_key="details_public",
            translation_placeholders={"title": entry.title},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, f"details_{entry.entry_id}")


def _entry(hass: HomeAssistant, entry_id: str) -> ParroConfigEntry | None:
    entry = hass.config_entries.async_get_entry(entry_id)
    return entry if entry and entry.domain == DOMAIN else None


def owns(entry: ParroConfigEntry, user: User | None) -> bool:
    return user is not None and user.is_active and entry.data.get(CONF_USER) == user.id


def can_read(entry: ParroConfigEntry, user: User | None) -> bool:
    return owns(entry, user) or (user is not None and user.is_active and user.id in _options(entry).viewers)


def _user(connection: websocket_api.ActiveConnection) -> User | None:
    return connection.user if connection.refresh_token_id in connection.user.refresh_tokens else None


def ready(hass: HomeAssistant, entry: ParroConfigEntry) -> bool:
    return (
        entry.state is ConfigEntryState.LOADED
        and not entry.runtime_data.ended
        and not any(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))
    )


@callback
def async_account(hass: HomeAssistant, user_id: str) -> ParroConfigEntry | None:
    own = [entry for entry in hass.config_entries.async_loaded_entries(DOMAIN) if entry.data.get(CONF_USER) == user_id]
    return min(own, key=lambda entry: entry.created_at, default=None)


def announcement(item: ParroAnnouncement, limit: int = FULL_TEXT_LIMIT) -> dict[str, Any]:
    return {
        "id": item.announcement_id,
        "title": item.title,
        "text": truncate(item.text, limit),
        "author": item.author,
        "groups": list(item.group_names),
        "published": iso(item.published),
        "read": item.read,
        "pinned": item.pinned,
        "photos": len(item.photo_urls),
        "attachments": len(item.attachments),
    }


def _shown(data: ParroData, count: int, group: str | None) -> list[ParroAnnouncement]:
    return [item for item in data.announcements if not group or group in item.group_names][:count]


def announcements(data: ParroData, count: int, group: str | None = None) -> list[dict[str, Any]]:
    return [announcement(item) for item in _shown(data, count, group)]


def conversations(
    data: ParroData, options: ParroOptions, count: int | None = None, limit: int = CHAT_PREVIEW_LIMIT
) -> list[dict[str, Any]]:
    return [
        {
            "id": room.room_id,
            "type": room.kind,
            "name": room.name or None,
            "members": len(room.member_names),
            "unread": room.unread_count,
            "last_message_at": iso(room.last_message_at),
            "last_sender": room.shown_sender,
            "preview": truncate(room.last_message, limit),
            "can_reply": room.can_reply and room.room_id in options.reply_conversations,
        }
        for room in data.chat_rooms[:count]
    ]


def groups(data: ParroData) -> list[str]:
    return sorted(filter(None, {group.name for group in data.groups.values()}))


@callback
def _async_readable(hass: HomeAssistant, user: User | None) -> list[ParroConfigEntry]:
    entries = hass.config_entries.async_entries(DOMAIN, include_ignore=False, include_disabled=False)
    return sorted(
        (entry for entry in entries if can_read(entry, user)),
        key=lambda entry: (not owns(entry, user), entry.state is not ConfigEntryState.LOADED, entry.created_at),
    )


@callback
def _async_payload(hass: HomeAssistant, user: User | None, entry_id: str | None, group: str | None) -> dict[str, Any]:
    entry = next(iter(_async_readable(hass, user)), None) if entry_id is None else _entry(hass, entry_id)
    if entry is None:
        return {"entry_id": None}
    if not can_read(entry, user):
        return {"entry_id": entry.entry_id, "access": False}
    options, own = _options(entry), owns(entry, user)
    base = {"entry_id": entry.entry_id, "access": True, "own": own}
    if not ready(hass, entry):
        reauth = entry.state is ConfigEntryState.LOADED or any(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))
        return {**base, "state": "reauth" if reauth else "not_loaded"}
    coordinator, account = entry.runtime_data, entry_key(entry)
    ids = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if not item.disabled
    }
    photos = (ids.get(f"{account}_recent_photo_{number}") for number in range(1, options.photo_count + 1))
    children = [{key: ids.get(f"{account}_{child}_{key}") for key in CHILD_KEYS} for child in coordinator.child_ids]
    return {
        **base,
        "state": "loaded" if coordinator.last_update_success else "failed",
        "updated": iso(coordinator.last_update_success_time),
        "entities": {key: ids.get(f"{account}_{key}") for key in ACCOUNT_KEYS},
        "recent_photos": [entity_id for entity_id in photos if entity_id],
        "children": children,
        "announcement_photos": options.announcement_photos,
        "announcements": announcements(coordinator.data, options.announcement_count, group),
        "conversations": (
            conversations(coordinator.data, options, limit=TEXT_LIMIT) if own and options.card_conversations else None
        ),
    }


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/subscribe", vol.Optional("entry_id"): str, vol.Optional("group"): str}
)
@callback
def _websocket_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    sent: list[dict[str, Any]] = []

    @callback
    def forward() -> None:
        payload = _async_payload(hass, _user(connection), msg.get("entry_id"), msg.get("group"))
        if sent != [payload]:
            sent[:] = [payload]
            connection.send_message(websocket_api.event_message(msg["id"], payload))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, SIGNAL_UPDATE, forward)
    connection.send_result(msg["id"])
    forward()


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/accounts"})
@callback
def _websocket_accounts(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    user = _user(connection)
    connection.send_result(
        msg["id"],
        [
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "own": owns(entry, user),
                "groups": groups(entry.runtime_data.data) if ready(hass, entry) else [],
            }
            for entry in _async_readable(hass, user)
        ],
    )


def _photo_url(request: web.Request, user: User | None) -> str | None:
    hass, path = request.app[KEY_HASS], request.match_info
    entry = _entry(hass, path["entry_id"])
    urls: tuple[str, ...] = ()
    if entry and can_read(entry, user) and ready(hass, entry):
        options, data = _options(entry), entry.runtime_data.data
        count = options.announcement_count if options.announcement_photos else 0
        item = next((item for item in data.announcements if str(item.announcement_id) == path["announcement_id"]), None)
        if item and any(item in _shown(data, count, group) for group in (None, *item.group_names)):
            urls = item.full_photo_urls if request.query.get("size") == "full" else item.photo_urls
    return next((url for number, url in enumerate(urls) if str(number) == path["index"]), None)


class ParroPhotoView(HomeAssistantView):
    url = f"/api/{DOMAIN}/photo/{{entry_id}}/{{announcement_id}}/{{index}}"
    name = f"api:{DOMAIN}:photo"

    async def get(self, request: web.Request, **_: str) -> web.Response:
        hass, user = request.app[KEY_HASS], request[KEY_HASS_USER]
        image = await photo_cache(hass).async_get(url := _photo_url(request, user))
        if image is None or _photo_url(request, await hass.auth.async_get_user(user.id)) != url:
            return web.Response(status=HTTPStatus.NOT_FOUND, headers=NO_STORE)
        return web.Response(body=image, content_type="image/jpeg", headers=NO_STORE)


async def async_service_entry(hass: HomeAssistant, call: ServiceCall, check: Check) -> ParroConfigEntry:
    user_id = call.context.user_id
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entry = _entry(hass, entry_id)
    elif user_id is None or (entry := async_account(hass, user_id)) is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_account")
    if user_id is not None and (entry is None or not check(entry, await hass.auth.async_get_user(user_id))):
        raise Unauthorized(context=call.context)
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_loaded")
    if not ready(hass, entry):
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="authentication_failed")
    return entry


@callback
def async_setup_content(hass: HomeAssistant) -> None:
    update = partial(async_dispatcher_send, hass, SIGNAL_UPDATE)

    @callback
    def async_entry_changed(change: ConfigEntryChange, entry: ConfigEntry) -> None:
        if entry.domain == DOMAIN:
            if change is ConfigEntryChange.UPDATED:
                async_details_issue(hass, entry)
            update()

    @callback
    def async_changed(event: Event) -> None:
        update()

    @callback
    def async_parro_entity(data: er.EventEntityRegistryUpdatedData) -> bool:
        registry, entity_id = er.async_get(hass), data["entity_id"]
        items = registry.deleted_entities.values() if data["action"] == "remove" else [registry.async_get(entity_id)]
        return any(item and item.entity_id == entity_id and item.platform == DOMAIN for item in items)

    async def async_get_announcements(call: ServiceCall) -> dict[str, Any]:
        coordinator = (await async_service_entry(hass, call, can_read)).runtime_data
        count = coordinator.options.announcement_count
        return {"announcements": announcements(coordinator.data, min(call.data.get(ATTR_COUNT, count), count))}

    async def async_get_conversations(call: ServiceCall) -> dict[str, Any]:
        coordinator = (await async_service_entry(hass, call, owns)).runtime_data
        if not coordinator.options.needs_chat_rooms:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="conversations_off")
        return {"conversations": conversations(coordinator.data, coordinator.options)}

    for service, handler, schema in (
        (SERVICE_GET_ANNOUNCEMENTS, async_get_announcements, ANNOUNCEMENTS_SCHEMA),
        (SERVICE_GET_CONVERSATIONS, async_get_conversations, ENTRY_SCHEMA),
    ):
        hass.services.async_register(DOMAIN, service, handler, schema=schema, supports_response=SupportsResponse.ONLY)
    async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, async_entry_changed)
    hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, async_changed, event_filter=async_parro_entity)
    for event_type in (EVENT_USER_REMOVED, EVENT_USER_UPDATED):
        hass.bus.async_listen(event_type, async_changed)
    websocket_api.async_register_command(hass, _websocket_subscribe)
    websocket_api.async_register_command(hass, _websocket_accounts)
    hass.http.register_view(ParroPhotoView())
