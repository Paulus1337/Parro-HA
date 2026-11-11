from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import MAX_LENGTH_STATE_STATE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import (
    CHAT_PREVIEW_LIMIT,
    CONVERSATION_ATTRIBUTE_LIMIT,
    SUMMARY_TEXT_LIMIT,
    TEXT_ATTRIBUTE_LIMIT,
    UPCOMING_EVENT_ATTRIBUTE_LIMIT,
)
from .coordinator import ParroConfigEntry, ParroData, ParroDataUpdateCoordinator, ParroOptions, as_datetime
from .entity import ParroChildEntity, ParroEntity, async_add_child_entities, iso, truncate
from .models import ParroAnnouncement, ParroChatRoom, ParroChild, ParroEvent

PARALLEL_UPDATES = 0
UNRECORDED_ATTRIBUTES = frozenset(
    {
        "all_day",
        "announcements",
        "attachments",
        "author",
        "conversations",
        "end",
        "group",
        "groups",
        "last_announcement",
        "photos",
        "start",
        "text",
        "title",
        "upcoming",
    }
)


def _upcoming(data: ParroData) -> list[ParroEvent]:
    now = dt_util.now()
    return [event for event in data.events if as_datetime(event.end) > now]


def _announcement(item: ParroAnnouncement, text_limit: int) -> dict[str, Any]:
    return {
        "title": item.title,
        "group": item.group_name,
        "author": item.author,
        "published": iso(item.published),
        "text": truncate(item.text, text_limit),
        "photos": len(item.images),
        "attachments": len(item.attachments),
        "read": item.read,
        "pinned": item.pinned,
    }


def _event(event: ParroEvent) -> dict[str, Any]:
    return {
        "title": event.title,
        "start": as_datetime(event.start).isoformat(),
        "end": as_datetime(event.end).isoformat(),
        "all_day": event.all_day,
        "groups": list(event.group_names),
    }


def _conversation(room: ParroChatRoom, options: ParroOptions) -> dict[str, Any]:
    return {
        "id": room.room_id,
        "type": room.kind,
        "name": room.name or None,
        "members": len(room.member_names),
        "unread": room.unread_count,
        "last_message_at": iso(room.last_message_at),
        "last_sender": room.shown_sender,
        "preview": truncate(room.last_message, CHAT_PREVIEW_LIMIT),
        "can_reply": room.can_reply and room.room_id in options.reply_conversations,
    }


def _latest_announcement_attributes(data: ParroData, options: ParroOptions) -> dict[str, Any]:
    items = data.announcements[: options.announcement_count]
    latest = _announcement(items[0], TEXT_ATTRIBUTE_LIMIT) if items else {}
    return {**latest, "announcements": [_announcement(item, SUMMARY_TEXT_LIMIT) for item in items]}


def _next_event_attributes(data: ParroData, options: ParroOptions) -> dict[str, Any]:
    upcoming = [_event(event) for event in _upcoming(data)[:UPCOMING_EVENT_ATTRIBUTE_LIMIT]]
    return {**(upcoming[0] if upcoming else {}), "upcoming": upcoming}


def _conversation_attributes(data: ParroData, options: ParroOptions) -> dict[str, Any]:
    if not options.chat_details or data.chat_rooms is None:
        return {}
    rooms = data.chat_rooms[:CONVERSATION_ATTRIBUTE_LIMIT]
    return {"conversations": [_conversation(room, options) for room in rooms]}


@dataclass(frozen=True, kw_only=True)
class ParroSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[ParroData], StateType | datetime]
    attributes_fn: Callable[[ParroData, ParroOptions], dict[str, Any]] | None = None


ACCOUNT_SENSORS = (
    ParroSensorEntityDescription(
        key="unread_announcements",
        translation_key="unread_announcements",
        value_fn=lambda data: data.unread.announcements,
    ),
    ParroSensorEntityDescription(
        key="unread_conversations",
        translation_key="unread_conversations",
        value_fn=lambda data: data.unread.chat_rooms,
        attributes_fn=_conversation_attributes,
    ),
    ParroSensorEntityDescription(
        key="unread_calendar_items",
        translation_key="unread_calendar_items",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.unread.calendar_items,
    ),
    ParroSensorEntityDescription(
        key="latest_announcement",
        translation_key="latest_announcement",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.announcements[0].published if data.announcements else None,
        attributes_fn=_latest_announcement_attributes,
    ),
    ParroSensorEntityDescription(
        key="next_event",
        translation_key="next_event",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: as_datetime(events[0].start) if (events := _upcoming(data)) else None,
        attributes_fn=_next_event_attributes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ParroConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ParroAccountSensor(coordinator, description) for description in ACCOUNT_SENSORS)
    async_add_child_entities(
        entry, async_add_entities, lambda coordinator, child: [ParroClassSensor(coordinator, child)]
    )


class ParroAccountSensor(ParroEntity, SensorEntity):
    entity_description: ParroSensorEntityDescription
    _unrecorded_attributes = UNRECORDED_ATTRIBUTES

    def __init__(self, coordinator: ParroDataUpdateCoordinator, description: ParroSensorEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes_fn = self.entity_description.attributes_fn
        return attributes_fn(self.coordinator.data, self.coordinator.options) if attributes_fn else None


class ParroClassSensor(ParroChildEntity, SensorEntity):
    _attr_translation_key = "class"
    _unrecorded_attributes = UNRECORDED_ATTRIBUTES

    def __init__(self, coordinator: ParroDataUpdateCoordinator, child: ParroChild) -> None:
        super().__init__(coordinator, child, "class")

    @property
    def native_value(self) -> str | None:
        group = self.coordinator.data.class_for_child(self.child_id)
        return truncate(group.name, MAX_LENGTH_STATE_STATE) if group else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        group = data.class_for_child(self.child_id)
        return {
            "school_year": group.school_year if group else None,
            "unread_announcements": sum(item.unread_count for item in data.groups_for_child(self.child_id)),
            "last_announcement": group.last_announcement_title if group else None,
            "last_announcement_at": iso(group.last_announcement_at) if group else None,
        }
