from __future__ import annotations

from contextlib import suppress
from functools import partial
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration
import voluptuous as vol

from .api import ParroAuth, ParroAuthenticationError, ParroError, TokenSet
from .chat import async_get_guard, async_remove_guard
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CONVERSATION_ID,
    ATTR_MESSAGE,
    CONF_ANNOUNCEMENT_DETAILS,
    CONF_ANNOUNCEMENT_PHOTOS,
    CONF_CARD_CONVERSATIONS,
    CONF_CHAT_DETAILS,
    CONF_CHILD_PHOTOS,
    CONF_CHILDREN,
    CONF_TOKEN,
    DOMAIN,
    SERVICE_SEND_MESSAGE,
    SIGNAL_UPDATE,
)
from .content import async_issues, async_service_entry, async_setup_content, owns
from .coordinator import ParroConfigEntry, ParroDataUpdateCoordinator, device_keys
from .media import PhotoArchive, photo_cache

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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def async_send_message(call: ServiceCall) -> None:
        entry = await async_service_entry(hass, call, owns)
        await entry.runtime_data.chat.async_send(call.data[ATTR_CONVERSATION_ID], call.data[ATTR_MESSAGE])

    hass.services.async_register(DOMAIN, SERVICE_SEND_MESSAGE, async_send_message, schema=SEND_MESSAGE_SCHEMA)
    async_setup_content(hass)
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)])
    add_extra_js_url(hass, f"{CARD_URL}?v={(await async_get_integration(hass, DOMAIN)).version}")
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ParroConfigEntry) -> bool:
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        chats = entry.options.get(CONF_CHAT_DETAILS) is True
        kept = {CONF_ANNOUNCEMENT_PHOTOS: False, CONF_CARD_CONVERSATIONS: chats, CONF_ANNOUNCEMENT_DETAILS: True}
        options = {CONF_CHILDREN: True, CONF_CHILD_PHOTOS: True, **kept, **entry.options}
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
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
    entry.async_on_unload(coordinator.async_add_listener(partial(async_dispatcher_send, hass, SIGNAL_UPDATE)))
    entry.async_on_unload(hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, coordinator.async_stop))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParroConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.client.async_close()
    photo_cache(hass).clear()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ParroConfigEntry) -> None:
    async_issues(hass, entry, removed=True)
    await async_remove_guard(hass, entry.entry_id)
    await PhotoArchive(hass, entry).async_remove()
    with suppress(ParroError):
        await ParroAuth(async_get_clientsession(hass)).async_revoke(TokenSet.from_dict(entry.data.get(CONF_TOKEN)))


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ParroConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    if entry.state is not ConfigEntryState.LOADED:
        return False
    in_use = device_keys(entry, entry.runtime_data.child_ids)
    return not any(domain == DOMAIN and identifier in in_use for domain, identifier in device_entry.identifiers)
