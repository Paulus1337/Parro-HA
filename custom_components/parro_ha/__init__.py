from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ServiceValidationError, Unauthorized
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
import voluptuous as vol

from .api import ParroAuth, ParroAuthenticationError, ParroError, TokenSet
from .chat import async_get_guard, async_remove_guard
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CONVERSATION_ID,
    ATTR_MESSAGE,
    CONF_TOKEN,
    CONF_USER,
    DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from .coordinator import ParroConfigEntry, ParroDataUpdateCoordinator, device_keys, entry_key

PLATFORMS = [Platform.CALENDAR, Platform.EVENT, Platform.IMAGE, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SEND_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_CONVERSATION_ID): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Required(ATTR_MESSAGE): cv.string,
    }
)
CARD_URL = f"/{DOMAIN}/parro-card.js"
CARD_PATH = Path(__file__).parent / "frontend" / "parro-card.js"
ACCOUNT_ENTITIES = (
    "unread_announcements",
    "unread_conversations",
    "unread_calendar_items",
    "latest_announcement",
    "next_event",
    "school_calendar",
    "announcement",
    "chat_message",
)
CHILD_ENTITIES = ("photo", "class", "calendar")


@callback
def _async_account(hass: HomeAssistant, user_id: str) -> ParroConfigEntry | None:
    own = [entry for entry in hass.config_entries.async_loaded_entries(DOMAIN) if entry.data.get(CONF_USER) == user_id]
    return min(own, key=lambda entry: entry.created_at, default=None)


@callback
def _async_entities(hass: HomeAssistant, entry: ParroConfigEntry) -> dict[str, Any]:
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    ids = {item.unique_id: item.entity_id for item in entities if not item.disabled}
    account, coordinator = entry_key(entry), entry.runtime_data
    photos = (ids.get(f"{account}_recent_photo_{number}") for number in range(1, coordinator.options.photo_count + 1))
    return {
        "entry_id": entry.entry_id,
        "entities": {key: ids.get(f"{account}_{key}") for key in ACCOUNT_ENTITIES},
        "recent_photos": [entity_id for entity_id in photos if entity_id],
        "children": [
            {key: ids.get(f"{account}_{child_id}_{key}") for key in CHILD_ENTITIES}
            for child_id in coordinator.data.children
        ],
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/account"})
@callback
def _websocket_account(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    entry = _async_account(hass, connection.user.id)
    connection.send_result(msg["id"], None if entry is None else _async_entities(hass, entry))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def async_send_message(call: ServiceCall) -> None:
        user_id = call.context.user_id
        if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
            entry = hass.config_entries.async_get_entry(entry_id)
        elif user_id is None or (entry := _async_account(hass, user_id)) is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_account")
        if user_id is not None:
            user = await hass.auth.async_get_user(user_id)
            owner = entry.data.get(CONF_USER) if entry is not None and entry.domain == DOMAIN else None
            if user is None or not user.is_active or user.id != owner:
                raise Unauthorized(context=call.context)
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_loaded")
        await entry.runtime_data.chat.async_send(call.data[ATTR_CONVERSATION_ID], call.data[ATTR_MESSAGE])

    hass.services.async_register(DOMAIN, SERVICE_SEND_MESSAGE, async_send_message, schema=SEND_MESSAGE_SCHEMA)
    websocket_api.async_register_command(hass, _websocket_account)
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)])
    add_extra_js_url(hass, f"{CARD_URL}?v={(await async_get_integration(hass, DOMAIN)).version}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ParroConfigEntry) -> bool:
    await async_get_guard(hass, entry.entry_id)
    try:
        coordinator = ParroDataUpdateCoordinator(hass, entry)
    except ParroAuthenticationError as err:
        raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="authentication_failed") from err
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParroConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.client.async_settle()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ParroConfigEntry) -> None:
    await async_remove_guard(hass, entry.entry_id)
    with suppress(ParroError):
        await ParroAuth(async_get_clientsession(hass)).async_revoke(TokenSet.from_dict(entry.data.get(CONF_TOKEN)))


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ParroConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    if entry.state is not ConfigEntryState.LOADED:
        return False
    in_use = device_keys(entry, entry.runtime_data.data.children)
    return not any(domain == DOMAIN and identifier in in_use for domain, identifier in device_entry.identifiers)
