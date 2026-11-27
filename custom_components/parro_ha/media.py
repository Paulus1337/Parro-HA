from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Iterable, Iterator
from contextlib import suppress
import errno
import hashlib
import io
import logging
import os
from pathlib import Path
import re
import shutil
import struct
import time
import uuid

import aiohttp
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.singleton import singleton
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey
from homeassistant.util.package import is_docker_env
from PIL import Image
from PIL.Image import DecompressionBombError

from .api import REQUEST_ERRORS, ParroError, read_body
from .const import DOMAIN, LOGGER, MAX_PARALLEL_REQUESTS
from .models import ParroAnnouncement, is_media_url

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
RETRY_SAVING = 24 * 3600
SAVE_DELAY = 10
TEMP_AGE = 3600
MIN_FREE_BYTES = 3 * 1024**3
RUNNING = (ConfigEntryState.LOADED, ConfigEntryState.SETUP_IN_PROGRESS)
MOUNTS = Path("/proc/self/mounts")
OCTAL = re.compile(r"\\([0-7]{3})")
SAVED_NAME = re.compile(r"(-?\d+)-\d+-([0-9a-f]{10})\.jpg")
TEMP_NAME = re.compile(r"\.[0-9a-f]{32}\.tmp")
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
        self._loads: dict[str, asyncio.Task[bytes | None]] = {}
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
        if url not in self._pending and time.monotonic() - self._failed.get(url, -RETRY_AFTER) < RETRY_AFTER:
            return None
        return await self._async_shared(url, keep=True)

    async def async_load(self, url: str) -> bytes | None:
        return await self._async_shared(url, keep=False) if is_media_url(url) else None

    async def _async_shared(self, url: str, *, keep: bool) -> bytes | None:
        pending = self._pending if keep else self._loads
        if (task := pending.get(url)) is None:
            task = self._hass.async_create_background_task(self._async_load(url, keep=keep), f"{DOMAIN} photo")
            if not task.done():
                pending[url] = task
                task.add_done_callback(lambda _: pending.pop(url, None))
        return await asyncio.shield(task)

    async def _async_load(self, url: str, *, keep: bool) -> bytes | None:
        images, failed = self._images, self._failed
        async with self._slots:
            level = logging.WARNING if keep and url not in failed else logging.DEBUG
            image = await _async_download(self._hass, url, level)
        if image is None:
            failed[url] = time.monotonic()
            while len(failed) > FAILED_ITEMS:
                del failed[next(iter(failed))]
            return None
        failed.pop(url, None)
        if keep:
            images[url] = image
            while len(images) > CACHE_ITEMS or sum(map(len, images.values())) > CACHE_BYTES:
                images.popitem(last=False)
        return image


@singleton(PHOTOS)
def photo_cache(hass: HomeAssistant) -> PhotoCache:
    return PhotoCache(hass)


def photo_files(item: ParroAnnouncement) -> Iterator[tuple[str, Path, str]]:
    day = dt_util.as_local(item.published).date().isoformat() if item.published else ""
    folder = Path(day[:4], day) if day else Path("Undated")
    for number, url in enumerate(item.full_photo_urls, 1):
        digest = hashlib.sha256(url.encode(errors="surrogatepass")).hexdigest()[:10]
        yield f"{item.announcement_id}-{digest}", folder / f"{item.announcement_id}-{number:02}-{digest}.jpg", url


def _mounted(folder: Path) -> bool:
    try:
        lines = os.fsdecode(MOUNTS.read_bytes()).split("\n")
    except OSError:
        return False
    points = {OCTAL.sub(lambda found: chr(int(found[1], 8)), line.split(" ")[1]) for line in lines if " " in line}
    return any(folder.is_relative_to(point) for point in points - {"/"})


def _parro_folder(local: str, www: str) -> Path | str:
    public, folder, root = Path(www).resolve(), Path(local).resolve(), Path(local, "Parro").resolve()
    if folder.is_relative_to(public) or root.is_relative_to(public):
        return "the local media folder is inside the public www folder"
    if is_docker_env() and os.stat(local).st_dev == os.stat("/").st_dev and not _mounted(folder):
        return "the media folder is not a mounted folder that survives an update of Home Assistant"
    return root


def _saved_keys(root: Path) -> set[str]:
    keys = set()
    for path in root.rglob("*"):
        if found := SAVED_NAME.fullmatch(path.name):
            keys.add("-".join(found.groups()))
        elif TEMP_NAME.fullmatch(path.name):
            with suppress(OSError):
                if time.time() - path.lstat().st_mtime > TEMP_AGE:
                    path.unlink()
    return keys


def _free(root: Path) -> int:
    root.mkdir(exist_ok=True)
    return shutil.disk_usage(root).free


def _write(root: Path, path: Path, content: bytes) -> None:
    if not (folder := path.parent.resolve()).is_relative_to(root.resolve()):
        raise ValueError
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / f".{uuid.uuid4().hex}.tmp"
    try:
        with temp.open("wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, folder / path.name)
    finally:
        temp.unlink(missing_ok=True)
    handle = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(handle)
    except OSError as err:
        if err.errno not in (errno.EINVAL, errno.ENOTSUP):
            raise
    finally:
        os.close(handle)


class PhotoArchive:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass, self._entry = hass, entry
        self._store: Store[list[str]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.saved", private=True)
        self._saved: set[str] | None = None
        self._failed: dict[str, float] = {}
        self._warned: set[str] = set()
        self._seen: set[str] = set()
        self._task: asyncio.Task[None] | None = None
        self._stopped = False

    @callback
    def async_start(self, announcements: Iterable[ParroAnnouncement]) -> None:
        if not self._stopped and self._entry.state in RUNNING and (self._task is None or self._task.done()):
            self._task = self._entry.async_create_background_task(
                self._hass, self._async_run(announcements), f"{DOMAIN} save photos"
            )

    async def async_stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
        if self._saved is not None:
            await self._store.async_save(sorted(self._saved))

    async def async_remove(self) -> None:
        await self._store.async_remove()

    def _warn(self, message: str, *args: str) -> None:
        text = message % args
        LOGGER.log(logging.DEBUG if text in self._warned | self._seen else logging.WARNING, message, *args)
        self._seen.add(text)

    async def _async_run(self, announcements: Iterable[ParroAnnouncement]) -> None:
        self._seen = set()
        await self._async_save(announcements)
        self._warned = self._seen

    async def _async_save(self, announcements: Iterable[ParroAnnouncement]) -> None:
        hass, now = self._hass, time.monotonic()
        if (saved := self._saved) is None:
            try:
                stored = await self._store.async_load()
            except HomeAssistantError:
                self._warn("Could not read which Parro photos were saved")
                return
            saved = self._saved = {key for key in stored if isinstance(key, str)} if isinstance(stored, list) else set()
        self._failed = {key: at for key, at in self._failed.items() if now - at < RETRY_SAVING}
        photos = {
            key: (path, url)
            for item in announcements
            for key, path, url in photo_files(item)
            if key not in saved and key not in self._failed
        }
        if not photos:
            self._seen = self._warned
            return
        if not (local := hass.config.media_dirs.get("local")):
            self._warn("Could not save Parro photos, because Home Assistant has no media folder named local")
            return
        try:
            root = await hass.async_add_executor_job(_parro_folder, local, hass.config.path("www"))
            if isinstance(root, str):
                self._warn("Could not save Parro photos, because %s", root)
                return
            found = await hass.async_add_executor_job(_saved_keys, root)
            for key, (path, url) in photos.items():
                if await hass.async_add_executor_job(_free, root) < MIN_FREE_BYTES:
                    self._warn("Stopped saving Parro photos, because the media folder has less than 3 GB free")
                    return
                if key in found or await self._async_write(root, root / path, url):
                    saved.add(key)
                    self._store.async_delay_save(lambda: sorted(saved), SAVE_DELAY)
                else:
                    self._failed[key] = time.monotonic()
        except OSError as err:
            self._warn("Could not save Parro photos (%s)", type(err).__name__)

    async def _async_write(self, root: Path, path: Path, url: str) -> bool:
        if (image := await photo_cache(self._hass).async_load(url)) is None:
            self._warn("Could not save some Parro photos; they are tried again in 24 hours")
            return False
        try:
            await self._hass.async_add_executor_job(_write, root, path, image)
        except (OSError, ValueError) as err:
            self._warn("Could not save a Parro photo (%s)", type(err).__name__)
            return False
        return True
