from __future__ import annotations

import re
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import ParroConfigEntry, ParroDataUpdateCoordinator, entry_key
from .entity import ParroChildEntity, ParroEntity, async_add_child_entities
from .media import photo_cache
from .models import ParroChild

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ParroConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    options, account = coordinator.options, re.escape(entry_key(entry))
    recent, child = re.compile(rf"{account}_recent_photo_([0-9]+)"), re.compile(rf"{account}_[0-9]+_photo")
    registry = er.async_get(hass)
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.domain == "image" and (
            ((match := recent.fullmatch(item.unique_id)) and int(match[1]) > options.photo_count)
            or (not options.child_photos and child.fullmatch(item.unique_id))
        ):
            registry.async_remove(item.entity_id)
    async_add_entities(ParroRecentPhoto(coordinator, index) for index in range(options.photo_count))
    if options.child_photos:
        async_add_child_entities(entry, async_add_entities, ParroChildPhoto)


class _ParroImage(ImageEntity):
    _url: str | None = None

    def _init_image(self, hass: HomeAssistant) -> None:
        ImageEntity.__init__(self, hass, verify_ssl=True)
        self._update_url()

    def _current_url(self) -> str | None:
        raise NotImplementedError

    def _update_url(self) -> None:
        url = self._current_url()
        if url != self._url:
            self._url = url
            self._attr_image_last_updated = dt_util.utcnow() if url else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_url()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        return await photo_cache(self.hass).async_get(self._url) if self.available else None


class ParroChildPhoto(_ParroImage, ParroChildEntity):
    _attr_translation_key = "child_photo"

    def __init__(self, coordinator: ParroDataUpdateCoordinator, child: ParroChild) -> None:
        ParroChildEntity.__init__(self, coordinator, child, "photo")
        self._init_image(coordinator.hass)

    def _current_url(self) -> str | None:
        return self.child.avatar_url if self.child else None


class ParroRecentPhoto(_ParroImage, ParroEntity):
    _attr_translation_key = "recent_photo"
    _unrecorded_attributes = frozenset({"title", "group"})

    def __init__(self, coordinator: ParroDataUpdateCoordinator, index: int) -> None:
        ParroEntity.__init__(self, coordinator, f"recent_photo_{index + 1}")
        self._index = index
        self._attr_translation_placeholders = {"number": str(index + 1)}
        self._init_image(coordinator.hass)

    def _current_url(self) -> str | None:
        photos = self.coordinator.data.photos
        return photos[self._index] if self._index < len(photos) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.coordinator.options.announcement_details:
            return None
        item = next((item for item in self.coordinator.data.announcements if self._url in item.photo_urls), None)
        return {"title": item.title, "group": item.group_name} if item else None
