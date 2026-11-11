from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp
from homeassistant.components.image import Image, ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import REQUEST_ERRORS, ParroError, read_body
from .const import DOMAIN, LOGGER, PHOTO_COUNT
from .coordinator import ParroConfigEntry, ParroDataUpdateCoordinator, ParroPhoto, entry_key
from .entity import ParroChildEntity, ParroEntity, async_add_child_entities
from .models import ParroChild, is_media_url

PARALLEL_UPDATES = 0
IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=9)
MAX_IMAGE_BYTES = 15 * 1024 * 1024
RETRY_AFTER = 300
CONTENT_TYPES = {
    "image/gif": "image/gif",
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ParroConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    photo_count = coordinator.options.photo_count
    registry = er.async_get(hass)
    for number in range(photo_count + 1, PHOTO_COUNT.maximum + 1):
        unique_id = f"{entry_key(entry)}_recent_photo_{number}"
        if entity_id := registry.async_get_entity_id("image", DOMAIN, unique_id):
            registry.async_remove(entity_id)
    async_add_entities(ParroRecentPhoto(coordinator, index) for index in range(photo_count))
    async_add_child_entities(
        entry, async_add_entities, lambda coordinator, child: [ParroChildPhoto(coordinator, child)]
    )


async def _async_download(hass: HomeAssistant, url: str) -> Image | None:
    try:
        async with async_get_clientsession(hass).get(url, timeout=IMAGE_TIMEOUT, allow_redirects=False) as response:
            content_type = CONTENT_TYPES.get(response.content_type)
            content = await read_body(response, MAX_IMAGE_BYTES) if response.status == 200 and content_type else b""
            if not content or content_type is None:
                LOGGER.warning(
                    "Could not load a Parro image (HTTP %s, %s)", response.status, content_type or "no image"
                )
                return None
            return Image(content_type, content)
    except (*REQUEST_ERRORS, ParroError) as err:
        LOGGER.warning("Could not load a Parro image (%s)", type(err).__name__)
        return None


class _ImageSource:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._lock = asyncio.Lock()
        self._image: Image | None = None
        self._failed_at: float | None = None
        self.url: str | None = None

    def set_url(self, url: str | None) -> bool:
        if url == self.url:
            return False
        self.url, self._image, self._failed_at = url, None, None
        return True

    async def async_get(self) -> Image | None:
        async with self._lock:
            url = self.url
            paused = self._failed_at is not None and time.monotonic() - self._failed_at < RETRY_AFTER
            if self._image is not None or paused or not is_media_url(url):
                return self._image
            image = await _async_download(self._hass, url)
            if url == self.url:
                self._image, self._failed_at = image, (None if image else time.monotonic())
            return image


class _ParroImage(ImageEntity):
    _source: _ImageSource

    def _init_image(self, hass: HomeAssistant) -> None:
        ImageEntity.__init__(self, hass, verify_ssl=True)
        self._source = _ImageSource(hass)
        self._update_source()

    def _current_url(self) -> str | None:
        raise NotImplementedError

    def _update_source(self) -> None:
        url = self._current_url()
        if self._source.set_url(url):
            self._attr_image_last_updated = dt_util.utcnow() if url else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_source()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        image = await self._source.async_get()
        if image is None:
            return None
        self._attr_content_type = image.content_type
        return image.content


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

    def _photo(self) -> ParroPhoto | None:
        photos = self.coordinator.data.photos
        return photos[self._index] if self._index < len(photos) else None

    def _current_url(self) -> str | None:
        photo = self._photo()
        return photo.url if photo else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        photo = self._photo()
        return {"title": photo.announcement_title, "group": photo.group_name} if photo else None
