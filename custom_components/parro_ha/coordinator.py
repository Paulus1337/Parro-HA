from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ParroAuthenticationError, ParroClient, ParroError, ParroForbiddenError, TokenSet
from .chat import ParroChat, async_get_guard
from .const import (
    ACCOUNT_REFRESH_SECONDS,
    ANNOUNCEMENT_COUNT,
    CALENDAR_QUERY_ROW_LIMIT,
    CHAT_ROOM_LIMIT,
    CONF_CHAT_DETAILS,
    CONF_REPLY_CONVERSATIONS,
    CONF_TOKEN,
    DOMAIN,
    EVENT_CACHE_SECONDS,
    LOGGER,
    MAX_PARALLEL_REQUESTS,
    PHOTO_COUNT,
    UPCOMING_EVENT_ROWS,
    UPDATE_INTERVAL,
)
from .models import (
    ParroAccount,
    ParroAnnouncement,
    ParroChatRoom,
    ParroChild,
    ParroEvent,
    ParroGroup,
    ParroUnreadCounts,
)

type ParroConfigEntry = ConfigEntry[ParroDataUpdateCoordinator]

_OLDEST = datetime.min.replace(tzinfo=UTC)


def entry_key(entry: ConfigEntry) -> str:
    return entry.unique_id or entry.entry_id


def child_device_key(account: str, child_id: int) -> str:
    return f"{account}_{child_id}"


def device_keys(entry: ConfigEntry, child_ids: Iterable[int]) -> set[str]:
    account = entry_key(entry)
    return {account, *(child_device_key(account, child_id) for child_id in child_ids)}


def as_datetime(value: date | datetime) -> datetime:
    return value if isinstance(value, datetime) else dt_util.start_of_local_day(value)


async def _optional[T](request: Awaitable[T], default: T) -> T:
    try:
        return await request
    except ParroForbiddenError:
        return default


@dataclass(frozen=True, slots=True)
class ParroOptions:
    update_interval: int
    announcement_count: int
    photo_count: int
    chat_details: bool
    reply_conversations: frozenset[int]

    @classmethod
    def from_mapping(cls, options: Mapping[str, Any]) -> ParroOptions:
        rooms = options.get(CONF_REPLY_CONVERSATIONS)
        room_ids = (item for item in (rooms if isinstance(rooms, list | tuple) else ()) if isinstance(item, str | int))
        return cls(
            update_interval=UPDATE_INTERVAL.read(options),
            announcement_count=ANNOUNCEMENT_COUNT.read(options),
            photo_count=PHOTO_COUNT.read(options),
            chat_details=options.get(CONF_CHAT_DETAILS) is True,
            reply_conversations=frozenset(int(item) for item in room_ids if str(item).isdecimal()),
        )

    @property
    def needs_chat_rooms(self) -> bool:
        return self.chat_details or bool(self.reply_conversations)


@dataclass(frozen=True, slots=True)
class ParroPhoto:
    url: str
    announcement_title: str
    group_name: str


@dataclass(frozen=True, slots=True)
class ParroData:
    account: ParroAccount
    children: dict[int, ParroChild]
    groups: dict[int, ParroGroup]
    unread: ParroUnreadCounts
    announcements: list[ParroAnnouncement]
    events: list[ParroEvent]
    photos: list[ParroPhoto]
    chat_rooms: list[ParroChatRoom] | None

    def groups_for_child(self, child_id: int) -> list[ParroGroup]:
        return [group for group in self.groups.values() if child_id in group.child_ids]

    def class_for_child(self, child_id: int) -> ParroGroup | None:
        groups = self.groups_for_child(child_id)
        return next((group for group in groups if group.is_class), groups[0] if groups else None)


class ParroDataUpdateCoordinator(DataUpdateCoordinator[ParroData]):
    config_entry: ParroConfigEntry
    chat: ParroChat

    def __init__(self, hass: HomeAssistant, entry: ParroConfigEntry) -> None:
        self.options = ParroOptions.from_mapping(entry.options)
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=self.options.update_interval),
        )
        tokens = TokenSet.from_dict(entry.data.get(CONF_TOKEN))
        self.client = ParroClient(async_get_clientsession(hass), tokens, self._async_store_tokens)
        self._account: tuple[float, ParroAccount] | None = None
        self._events: dict[tuple[datetime, datetime], tuple[float, list[ParroEvent]]] = {}
        self._event_lock = asyncio.Lock()
        self._request_slots = asyncio.Semaphore(MAX_PARALLEL_REQUESTS)

    async def _async_setup(self) -> None:
        self.chat = ParroChat(self, await async_get_guard(self.hass, self.config_entry.entry_id))

    @callback
    def _async_store_tokens(self, tokens: TokenSet) -> None:
        entry = self.config_entry
        self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOKEN: tokens.as_dict()})

    def session_ended(self) -> HomeAssistantError:
        self.config_entry.async_start_reauth(self.hass)
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="authentication_failed")

    async def _async_update_data(self) -> ParroData:
        try:
            data = await self._async_fetch()
        except ParroAuthenticationError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="authentication_failed") from err
        except ParroError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="update_failed", translation_placeholders={"error": str(err)}
            ) from err
        self._async_remove_stale_devices(data.children)
        return data

    async def _async_fetch(self) -> ParroData:
        account = await self._async_account()
        client, options = self.client, self.options
        children, groups, unread = await asyncio.gather(
            client.async_get_children(),
            client.async_get_groups(),
            _optional(client.async_get_unread_counts(), ParroUnreadCounts()),
        )
        announcements = await self._async_announcements(groups.values())
        since = dt_util.start_of_local_day() - timedelta(days=1)
        events = await _optional(client.async_get_events(since, limit=UPCOMING_EVENT_ROWS), [])
        photos = [
            ParroPhoto(image.preview_url, item.title, item.group_name)
            for item in announcements
            for image in item.images
            if image.preview_url
        ]
        return ParroData(
            account=account,
            children=children,
            groups=groups,
            unread=unread,
            announcements=announcements,
            events=sorted(events, key=lambda event: as_datetime(event.start)),
            photos=photos[: options.photo_count],
            chat_rooms=await self.async_get_chat_rooms() if options.needs_chat_rooms else None,
        )

    async def _async_account(self) -> ParroAccount:
        now = time.monotonic()
        if self._account is not None and now - self._account[0] < ACCOUNT_REFRESH_SECONDS:
            return self._account[1]
        account = await self.client.async_get_account()
        if str(account.account_id) != self.config_entry.unique_id:
            raise ParroAuthenticationError("The Parro session belongs to another account")
        self._account = (now, account)
        return account

    async def _async_announcements(self, groups: Iterable[ParroGroup]) -> list[ParroAnnouncement]:
        limit = max(self.options.announcement_count, ANNOUNCEMENT_COUNT.default)

        async def fetch(group: ParroGroup) -> list[ParroAnnouncement]:
            async with self._request_slots:
                return await _optional(self.client.async_get_announcements(group, limit), [])

        per_group = await asyncio.gather(*map(fetch, groups))
        unique = {item.announcement_id: item for items in per_group for item in items}
        return sorted(unique.values(), key=lambda item: item.published or _OLDEST, reverse=True)

    async def async_get_chat_rooms(self) -> list[ParroChatRoom]:
        return await _optional(self.client.async_get_chat_rooms(CHAT_ROOM_LIMIT), [])

    @callback
    def _async_remove_stale_devices(self, children: Mapping[int, ParroChild]) -> None:
        if not children:
            return
        current = device_keys(self.config_entry, children)
        registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(registry, self.config_entry.entry_id):
            identifiers = {identifier for domain, identifier in device.identifiers if domain == DOMAIN}
            if identifiers and not identifiers & current:
                registry.async_remove_device(device.id)

    async def async_get_events(self, start: datetime, end: datetime) -> list[ParroEvent]:
        async with self._event_lock:
            now = time.monotonic()
            self._events = {key: value for key, value in self._events.items() if now - value[0] < EVENT_CACHE_SECONDS}
            if (cached := self._events.get((start, end))) is not None:
                return cached[1]
            try:
                rows = await _optional(
                    self.client.async_get_events(start - timedelta(days=1), limit=CALENDAR_QUERY_ROW_LIMIT, until=end),
                    [],
                )
            except ParroAuthenticationError as err:
                raise self.session_ended() from err
            except ParroError as err:
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="calendar_failed") from err
            events = [event for event in rows if as_datetime(event.start) < end and as_datetime(event.end) > start]
            events.sort(key=lambda event: as_datetime(event.start))
            self._events[(start, end)] = (now, events)
            return events
