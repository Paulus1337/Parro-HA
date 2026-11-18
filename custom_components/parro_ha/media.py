from __future__ import annotations

import asyncio
from collections import OrderedDict
import io
import logging
import re
import struct
import time

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.singleton import singleton
from homeassistant.util.hass_dict import HassKey
from PIL import Image
from PIL.Image import DecompressionBombError

from .api import REQUEST_ERRORS, ParroError, read_body
from .const import DOMAIN, LOGGER, MAX_PARALLEL_REQUESTS
from .models import is_media_url

IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=9)
MAX_DOWNLOAD_BYTES = 15 * 1024 * 1024
MAX_EDGE = 65535
MAX_PARTS = 65536
MAX_PIXELS = 24_000_000
MAX_SCANS = 32
MAX_SIDE = 1600
CACHE_ITEMS = 256
FAILED_ITEMS = 1024
CACHE_BYTES = 24 * 1024 * 1024
RETRY_AFTER = 300
CONTENT_TYPES = frozenset({"image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/webp"})
FORMATS = ("JPEG", "PNG", "WEBP")
JPEG_KEPT = frozenset({*range(0xC0, 0xC5), *range(0xDA, 0xDE), 0xE0, 0xEE})
JPEG_KNOWN = JPEG_KEPT | {*range(0xE1, 0xEE), 0xEF, 0xFE}
JPEG_FRAMES = frozenset(range(0xC0, 0xC4))
JPEG_FILL = b"\xff" * 65536
JPEG_MARKER = re.compile(rb"\xff[^\xff]")
PNG_KEPT = frozenset({b"PLTE", b"tRNS", b"IDAT", b"IEND"})
ORIENTATION = {b"II*\x00": struct.pack("<HHI", 0x0112, 3, 1), b"MM\x00*": struct.pack(">HHI", 0x0112, 3, 1)}
TURNS = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
PHOTOS: HassKey[PhotoCache] = HassKey(f"{DOMAIN}_photos")


def _area(size: bytes) -> int:
    return int.from_bytes(size[: len(size) // 2]) * int.from_bytes(size[len(size) // 2 :])


def _jpeg(content: bytes) -> tuple[bytes, bytes]:
    parts, exif, at = [content[:2]], b"", 2
    for _ in range(MAX_PARTS):
        if (found := JPEG_MARKER.search(content, at)) is None:
            break
        marker, size = struct.unpack_from(">xBH", content, at := found.start())
        frame = marker in JPEG_FRAMES and (size > 20 or _area(content[at + 5 : at + 9]) > MAX_PIXELS)
        if size < 2 or marker not in JPEG_KNOWN or frame:
            break
        if marker == 0xDA:
            tail = b"".join(content[at:].partition(b"\xff\xd9")[:2])
            if tail.count(b"\xff\xda") > MAX_SCANS or JPEG_FILL in tail:
                break
            return b"".join((*parts, tail)), exif
        segment = content[at : at + 2 + size]
        if marker == 0xE1 and segment[4:10] == b"Exif\x00\x00":
            exif = exif or segment[10:]
        elif marker in JPEG_KEPT:
            parts.append(segment)
        at += 2 + size
    raise ValueError


def _png(content: bytes) -> tuple[bytes, bytes]:
    if content[8:16] != b"\x00\x00\x00\x0dIHDR" or _area(content[16:24]) > MAX_PIXELS:
        raise ValueError
    parts, exif, at = [content[:33]], b"", 33
    kept = PNG_KEPT - {b"tRNS"} if content[24:25] == b"\x10" else PNG_KEPT
    while len(head := content[at : at + 8]) == 8 and len(parts) < MAX_PARTS and parts[-1][4:8] != b"IEND":
        chunk = content[at : at + 12 + int.from_bytes(head[:4])]
        at += len(chunk)
        if head[4:] == b"eXIf":
            exif = exif or chunk[8:-4]
        elif head[4:] in kept:
            parts.append(chunk)
    return b"".join(parts), exif


def _turn(exif: bytes) -> Image.Transpose | None:
    exif = exif.removeprefix(b"Exif\x00\x00")
    order = "little" if exif[:2] == b"II" else "big"
    start = int.from_bytes(exif[4:8], order)
    for at in range(start + 2, start + 2 + 12 * int.from_bytes(exif[start : start + 2], order), 12):
        if exif[at : at + 8] == ORIENTATION.get(exif[:4]) and len(exif) >= at + 12:
            return TURNS.get(int.from_bytes(exif[at + 8 : at + 10], order))
    return None


def _webp(content: bytes) -> int:
    kind, bits = content[12:16], int.from_bytes(content[21:25], "little")
    if kind == b"VP8X":
        return (int.from_bytes(content[24:27], "little") + 1) * (int.from_bytes(content[27:30], "little") + 1)
    if kind == b"VP8L":
        return ((bits & 0x3FFF) + 1) * ((bits >> 14 & 0x3FFF) + 1)
    return (int.from_bytes(content[26:28], "little") & 0x3FFF) * (int.from_bytes(content[28:30], "little") & 0x3FFF)


def reencode(content: bytes) -> bytes | None:
    try:
        exif = b""
        if content[:2] == b"\xff\xd8":
            content, exif = _jpeg(content)
        elif content[:8] == b"\x89PNG\r\n\x1a\n":
            content, exif = _png(content)
        elif content[:4] == b"RIFF" and _webp(content) > MAX_PIXELS:
            return None
        with Image.open(io.BytesIO(content), formats=FORMATS) as source:
            if source.width * source.height > MAX_PIXELS or max(source.size) > MAX_EDGE:
                return None
            turn = _turn(exif or source.info.get("exif", b""))
            image = source.copy() if turn is None else source.transpose(turn)
            if image.mode == "I;16":
                image = image.point(lambda value: value / 256).convert("L")
            if image.mode in ("1", "P") or "transparency" in image.info:
                image = image.convert("RGBA")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            if image.mode != "RGB":
                image = image.convert("RGBA")
                flat = Image.new("RGB", image.size, "white")
                flat.paste(image, mask=image)
                image = flat
            image.info.clear()
            output = io.BytesIO()
            image.save(output, "JPEG", quality=85, optimize=True)
            return output.getvalue()
    except (DecompressionBombError, KeyError, MemoryError, OSError, SyntaxError, TypeError, ValueError, struct.error):
        return None


async def _async_download(hass: HomeAssistant, url: str, level: int) -> bytes | None:
    try:
        async with async_get_clientsession(hass).get(url, timeout=IMAGE_TIMEOUT, allow_redirects=False) as response:
            valid = response.status == 200 and response.content_type in CONTENT_TYPES
            content = await read_body(response, MAX_DOWNLOAD_BYTES) if valid else b""
            status, kind = response.status, response.content_type if valid else "no image"
    except (*REQUEST_ERRORS, ParroError) as err:
        LOGGER.log(level, "Could not load a Parro photo (%s)", type(err).__name__)
        return None
    async with photo_cache(hass).decoding:
        image = await hass.async_add_executor_job(reencode, content) if content else None
    if image is None:
        LOGGER.log(level, "Could not load a Parro photo (HTTP %s, %s)", status, kind)
    return image


class PhotoCache:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._images: OrderedDict[str, bytes] = OrderedDict()
        self._failed: dict[str, float] = {}
        self._pending: dict[str, asyncio.Task[bytes | None]] = {}
        self.decoding = asyncio.Lock()
        self._slots = asyncio.Semaphore(MAX_PARALLEL_REQUESTS)

    def clear(self) -> None:
        self._images, self._failed = OrderedDict(), {}

    async def async_get(self, url: str | None) -> bytes | None:
        if not is_media_url(url):
            return None
        if (image := self._images.get(url)) is not None:
            self._images.move_to_end(url)
            return image
        if (task := self._pending.get(url)) is None:
            if time.monotonic() - self._failed.get(url, -RETRY_AFTER) < RETRY_AFTER:
                return None
            task = self._hass.async_create_background_task(self._async_load(url), f"{DOMAIN} photo")
            self._pending[url] = task
            task.add_done_callback(lambda _: self._pending.pop(url, None))
        return await asyncio.shield(task)

    async def _async_load(self, url: str) -> bytes | None:
        images, failed = self._images, self._failed
        async with self._slots:
            image = await _async_download(self._hass, url, logging.DEBUG if url in failed else logging.WARNING)
        if image is None:
            failed[url] = time.monotonic()
            while len(failed) > FAILED_ITEMS:
                del failed[next(iter(failed))]
            return None
        failed.pop(url, None)
        images[url] = image
        while len(images) > CACHE_ITEMS or sum(map(len, images.values())) > CACHE_BYTES:
            images.popitem(last=False)
        return image


@singleton(PHOTOS)
def photo_cache(hass: HomeAssistant) -> PhotoCache:
    return PhotoCache(hass)
