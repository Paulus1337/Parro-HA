from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import ParroConfigEntry, ParroDataUpdateCoordinator, as_datetime
from .entity import ParroChildEntity, ParroEntity, async_add_child_entities
from .models import ParroChild, ParroEvent

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ParroConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([ParroSchoolCalendar(entry.runtime_data)])
    async_add_child_entities(
        entry, async_add_entities, lambda coordinator, child: [ParroChildCalendar(coordinator, child)]
    )


def _calendar_event(event: ParroEvent) -> CalendarEvent:
    return CalendarEvent(
        start=event.start,
        end=event.end,
        summary=event.title or "Parro",
        description=", ".join(event.group_names) or None,
        uid=str(event.item_id),
    )


class _ParroCalendar(CalendarEntity):
    coordinator: ParroDataUpdateCoordinator
    _unrecorded_attributes = frozenset({"message", "start_time", "end_time", "all_day", "location"})

    def _includes(self, event: ParroEvent) -> bool:
        return True

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        events = (event for event in self.coordinator.data.events if as_datetime(event.end) > now)
        return next((_calendar_event(event) for event in events if self._includes(event)), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        events = await self.coordinator.async_get_events(start_date, end_date)
        return [_calendar_event(event) for event in events if self._includes(event)]


class ParroSchoolCalendar(ParroEntity, _ParroCalendar):
    _attr_translation_key = "school_calendar"

    def __init__(self, coordinator: ParroDataUpdateCoordinator) -> None:
        super().__init__(coordinator, "school_calendar")


class ParroChildCalendar(ParroChildEntity, _ParroCalendar):
    _attr_translation_key = "child_calendar"

    def __init__(self, coordinator: ParroDataUpdateCoordinator, child: ParroChild) -> None:
        super().__init__(coordinator, child, "calendar")

    def _includes(self, event: ParroEvent) -> bool:
        return self.child_id in event.child_ids
