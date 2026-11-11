from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, WEB_APP_URL
from .coordinator import ParroConfigEntry, ParroDataUpdateCoordinator, child_device_key, entry_key
from .models import ParroChild


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 3].rstrip()}..."


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class ParroEntity(CoordinatorEntity[ParroDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ParroDataUpdateCoordinator, key: str, child: ParroChild | None = None) -> None:
        super().__init__(coordinator)
        account = entry_key(coordinator.config_entry)
        device_key = account if child is None else child_device_key(account, child.child_id)
        self._attr_unique_id = f"{device_key}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name="Parro" if child is None else child.first_name or "Child",
            manufacturer=MANUFACTURER,
            model="Parro" if child is None else "Child",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=WEB_APP_URL if child is None else None,
        )


class ParroChildEntity(ParroEntity):
    def __init__(self, coordinator: ParroDataUpdateCoordinator, child: ParroChild, key: str) -> None:
        super().__init__(coordinator, key, child)
        self.child_id = child.child_id

    @property
    def child(self) -> ParroChild | None:
        return self.coordinator.data.children.get(self.child_id)

    @property
    def available(self) -> bool:
        return super().available and self.child is not None


def async_add_child_entities(
    entry: ParroConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[ParroDataUpdateCoordinator, ParroChild], Iterable[Entity]],
) -> None:
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def async_add_new_children() -> None:
        if coordinator.data.children:
            known.intersection_update(coordinator.data.children)
        children = [child for child_id, child in coordinator.data.children.items() if child_id not in known]
        known.update(child.child_id for child in children)
        if children:
            async_add_entities(entity for child in children for entity in factory(coordinator, child))

    async_add_new_children()
    entry.async_on_unload(coordinator.async_add_listener(async_add_new_children))
