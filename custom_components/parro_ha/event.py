from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CHAT_PREVIEW_LIMIT, DOMAIN, EVENT_NEW_ANNOUNCEMENT, EVENT_NEW_CHAT_MESSAGE
from .coordinator import ParroConfigEntry, ParroDataUpdateCoordinator, entry_key
from .entity import ParroEntity, iso, truncate
from .models import ParroAnnouncement, ParroChatRoom

if TYPE_CHECKING:
    from homeassistant.components.event import EventExtraStoredData

PARALLEL_UPDATES = 0
SEEN_LIMIT = 500


async def async_setup_entry(
    hass: HomeAssistant, entry: ParroConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[EventEntity] = [ParroAnnouncementEvent(coordinator)]
    if coordinator.options.needs_chat_rooms:
        entities.append(ParroChatMessageEvent(coordinator))
    else:
        registry = er.async_get(hass)
        if entity_id := registry.async_get_entity_id("event", DOMAIN, f"{entry_key(entry)}_chat_message"):
            registry.async_remove(entity_id)
    async_add_entities(entities)


class _ParroEvent(ParroEntity, EventEntity):
    @property
    def available(self) -> bool:
        return True


class ParroAnnouncementEvent(_ParroEvent):
    _attr_translation_key = "announcement"
    _unrecorded_attributes = frozenset({"title", "group", "author"})

    def __init__(self, coordinator: ParroDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "announcement")
        self._attr_event_types = [EVENT_NEW_ANNOUNCEMENT]
        announcements = coordinator.data.announcements
        self._seen = [item.announcement_id for item in reversed(announcements)]
        self._watermark = max((item.published for item in announcements if item.published), default=dt_util.utcnow())

    def _is_new(self, item: ParroAnnouncement, seen: set[int]) -> bool:
        recent = item.published is not None and item.published >= self._watermark
        return recent and item.announcement_id not in seen

    @callback
    def _handle_coordinator_update(self) -> None:
        seen = set(self._seen)
        new = [item for item in reversed(self.coordinator.data.announcements) if self._is_new(item, seen)]
        for item in new:
            self._seen.append(item.announcement_id)
            self._watermark = max(self._watermark, item.published or self._watermark)
            attributes = {
                "title": item.title,
                "group": item.group_name,
                "author": item.author,
                "published": iso(item.published),
                "photos": len(item.images),
            }
            self._trigger_event(EVENT_NEW_ANNOUNCEMENT, attributes)
            self.async_write_ha_state()
        del self._seen[:-SEEN_LIMIT]
        if not new:
            super()._handle_coordinator_update()


class ParroChatMessageEvent(_ParroEvent):
    _attr_translation_key = "chat_message"
    _unrecorded_attributes = frozenset({"sender", "preview"})

    def __init__(self, coordinator: ParroDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "chat_message")
        self._attr_event_types = [EVENT_NEW_CHAT_MESSAGE]
        self._started = dt_util.utcnow()
        self._last_message_at = {room.room_id: room.last_message_at for room in coordinator.data.chat_rooms or []}

    async def async_get_last_event_data(self) -> EventExtraStoredData | None:
        data = await super().async_get_last_event_data()
        if data is None or not data.last_event_attributes or self.coordinator.options.chat_details:
            return data
        hidden = self._unrecorded_attributes
        attributes = {key: value for key, value in data.last_event_attributes.items() if key not in hidden}
        return replace(data, last_event_attributes=attributes)

    def _is_new(self, room: ParroChatRoom) -> bool:
        previous = self._last_message_at.get(room.room_id, self._started)
        return room.last_message_at is not None and (previous is None or room.last_message_at > previous)

    def _attributes(self, room: ParroChatRoom) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            "conversation_id": room.room_id,
            "conversation_type": room.kind,
            "received": iso(room.last_message_at),
        }
        if self.coordinator.options.chat_details:
            attributes["sender"] = room.shown_sender
            attributes["preview"] = truncate(room.last_message, CHAT_PREVIEW_LIMIT)
        return attributes

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        new = [room for room in data.chat_rooms or [] if self._is_new(room)]
        self._last_message_at |= {room.room_id: room.last_message_at for room in data.chat_rooms or []}
        fired = [room for room in new if room.last_sender_id not in data.account.own_ids]
        for room in fired:
            self._trigger_event(EVENT_NEW_CHAT_MESSAGE, self._attributes(room))
            self.async_write_ha_state()
        if not fired:
            super()._handle_coordinator_update()
