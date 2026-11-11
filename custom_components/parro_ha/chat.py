from __future__ import annotations

import asyncio
import hashlib
import re
from typing import TYPE_CHECKING, Any, NamedTuple
import unicodedata

from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .api import ParroAuthenticationError, ParroError, ParroRefusedError, ParroUncertainError
from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import ParroDataUpdateCoordinator

MAX_MESSAGE_LENGTH = 1000
MAX_MESSAGE_LINES = 20
COOLDOWN_SECONDS = 60
MAX_PER_HOUR = 5
MAX_PER_DAY = 20
DUPLICATE_WINDOW_SECONDS = 6 * 3600
BLOCK_SECONDS = 3600
_HOUR = 3600
_DAY = 24 * _HOUR
_LINE_BREAKS = {0x09: " ", 0x0B: "\n", 0x0C: "\n", 0x0D: "\n", 0x2028: "\n", 0x2029: "\n"}
_KEPT_FORMAT_CHARACTERS = frozenset(map(chr, (0x0A, 0x200C, 0x200D)))
_REMOVED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co"})
_LINK = re.compile(r"[a-z][a-z0-9+.-]*://|www\.[^\s/$.?#]\S|[\w.%+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)
_MARKUP = re.compile(r"<[a-z/!?]|[`{}\[\]\\]|&(?:#|lt|gt|amp|quot|\w+;)", re.IGNORECASE)
_PLACEHOLDERS = frozenset({"unknown", "unavailable", "none", "null"})
_BLANK = frozenset(
    map(chr, (0x115F, 0x1160, 0x2065, 0x2800, 0x3164, 0xFFA0, *range(0xFFF0, 0xFFF9), *range(0xE0000, 0xE1000)))
)


class Attempt(NamedTuple):
    at: float
    room_id: int
    digest: str


def _refusal(key: str) -> ServiceValidationError:
    return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)


def _failure(key: str) -> HomeAssistantError:
    return HomeAssistantError(translation_domain=DOMAIN, translation_key=key)


def _stored_attempt(item: Any) -> Attempt | None:
    match item:
        case [int() | float() as at, int() as room_id, str() as digest]:
            return Attempt(float(at), room_id, digest)
    return None


def _visible(char: str) -> bool:
    category = unicodedata.category(char)
    return char not in _BLANK and (category[0] in "LNPS" or category == "Cn")


def clean_message(text: Any) -> str:
    if not isinstance(text, str):
        raise _refusal("message_empty")
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n")).translate(_LINE_BREAKS)
    text = "".join(
        char
        for char in text
        if char in _KEPT_FORMAT_CHARACTERS or unicodedata.category(char) not in _REMOVED_CATEGORIES
    )
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.split("\n"))).strip()
    if not any(map(_visible, text)):
        raise _refusal("message_empty")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise _refusal("message_too_long")
    if text.count("\n") >= MAX_MESSAGE_LINES:
        raise _refusal("message_too_many_lines")
    if text.casefold() in _PLACEHOLDERS:
        raise _refusal("message_template")
    plain = "".join(c for c in f"{text}\n{unicodedata.normalize('NFKC', text)}" if _visible(c) or c.isspace())
    if _MARKUP.search(plain):
        raise _refusal("message_markup")
    if _LINK.search(plain):
        raise _refusal("message_link")
    return text


class SendGuard:
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry_id}.replies", private=True)
        self._attempts: list[Attempt] = []
        self._blocked_until = 0.0
        self._cleanup = HassJob(self._async_cleanup, f"{DOMAIN} reply cleanup", cancel_on_shutdown=True)
        self._cancel_cleanup: CALLBACK_TYPE | None = None
        self.lock = asyncio.Lock()
        self.removed = False

    @staticmethod
    def attempt(room_id: int, text: str) -> Attempt:
        digest = hashlib.sha256(f"{room_id}\n{text}".encode()).hexdigest()
        return Attempt(dt_util.utcnow().timestamp(), room_id, digest)

    async def async_load(self) -> None:
        async with self.lock:
            stored = await self._store.async_load()
            data = stored if isinstance(stored, dict) else {}
            attempts, blocked = data.get("attempts"), data.get("blocked_until")
            items = attempts if isinstance(attempts, list) else []
            self._attempts = [attempt for item in items if (attempt := _stored_attempt(item)) is not None]
            self._blocked_until = float(blocked) if isinstance(blocked, int | float) else 0.0
            await self._async_update(dt_util.utcnow().timestamp(), save=False)

    async def async_remove(self) -> None:
        async with self.lock:
            self.removed = True
            self._attempts, self._blocked_until = [], 0.0
            self._schedule_cleanup()
            await self._store.async_remove()

    def check(self, attempt: Attempt) -> None:
        now = attempt.at
        if now < self._blocked_until:
            raise _refusal("sending_paused")
        recent = [item for item in self._attempts if now - item.at < _DAY]
        if (
            len(recent) >= MAX_PER_DAY
            or sum(now - item.at < _HOUR for item in recent) >= MAX_PER_HOUR
            or any(item.room_id == attempt.room_id and now - item.at < COOLDOWN_SECONDS for item in recent)
        ):
            raise _refusal("rate_limited")
        if any(item.digest == attempt.digest and now - item.at < DUPLICATE_WINDOW_SECONDS for item in recent):
            raise _refusal("duplicate_message")

    async def async_record(self, attempt: Attempt) -> None:
        self._attempts.append(attempt)
        await self._async_update(attempt.at, save=True)

    async def async_not_sent(self, attempt: Attempt, *, pause: bool) -> None:
        self._attempts = [item._replace(digest="") if item is attempt else item for item in self._attempts]
        if pause:
            self._blocked_until = attempt.at + BLOCK_SECONDS
        await self._async_update(dt_util.utcnow().timestamp(), save=True)

    async def _async_cleanup(self) -> None:
        async with self.lock:
            await self._async_update(dt_util.utcnow().timestamp(), save=False)

    def _prune(self, now: float) -> bool:
        attempts = [
            item._replace(digest="") if item.digest and now - item.at >= DUPLICATE_WINDOW_SECONDS else item
            for item in self._attempts
            if now - item.at < _DAY
        ]
        blocked_until = self._blocked_until if now < self._blocked_until else 0.0
        changed = attempts != self._attempts or blocked_until != self._blocked_until
        self._attempts, self._blocked_until = attempts, blocked_until
        return changed

    async def _async_update(self, now: float, *, save: bool) -> None:
        if self._prune(now) or save:
            if self._attempts or self._blocked_until:
                await self._store.async_save(
                    {"attempts": list(map(list, self._attempts)), "blocked_until": self._blocked_until}
                )
            else:
                await self._store.async_remove()
        self._schedule_cleanup()

    def _schedule_cleanup(self) -> None:
        if self._cancel_cleanup is not None:
            self._cancel_cleanup()
        now = dt_util.utcnow().timestamp()
        delays = [(DUPLICATE_WINDOW_SECONDS if item.digest else _DAY) - (now - item.at) for item in self._attempts]
        if self._blocked_until:
            delays.append(self._blocked_until - now)
        hass = self._hass
        self._cancel_cleanup = (
            hass.loop.call_later(max(min(delays), 0), hass.async_run_hass_job, self._cleanup).cancel if delays else None
        )


GUARDS: HassKey[dict[str, SendGuard]] = HassKey(f"{DOMAIN}_reply_guards")


async def async_get_guard(hass: HomeAssistant, entry_id: str) -> SendGuard:
    guards = hass.data.setdefault(GUARDS, {})
    if (guard := guards.get(entry_id)) is None:
        guard = SendGuard(hass, entry_id)
        await guard.async_load()
        guards[entry_id] = guard
    return guard


async def async_remove_guard(hass: HomeAssistant, entry_id: str) -> None:
    guard = hass.data.get(GUARDS, {}).pop(entry_id, None) or SendGuard(hass, entry_id)
    await guard.async_remove()


class ParroChat:
    def __init__(self, coordinator: ParroDataUpdateCoordinator, guard: SendGuard) -> None:
        self._coordinator = coordinator
        self.guard = guard

    def _error(self, err: ParroError) -> HomeAssistantError:
        if isinstance(err, ParroAuthenticationError):
            return self._coordinator.session_ended()
        return _failure("send_refused" if isinstance(err, ParroRefusedError) else "send_failed")

    async def async_send(self, room_id: int, message: Any) -> None:
        coordinator, guard = self._coordinator, self.guard
        if room_id not in coordinator.options.reply_conversations:
            raise _refusal("conversation_not_allowed")
        text = clean_message(message)
        async with guard.lock:
            if guard.removed:
                raise _refusal("entry_not_loaded")
            attempt = SendGuard.attempt(room_id, text)
            guard.check(attempt)
            try:
                rooms = await coordinator.async_get_chat_rooms()
            except ParroError as err:
                raise self._error(err) from err
            if not any(room.room_id == room_id and room.can_reply for room in rooms):
                raise _refusal("conversation_not_available")
            await guard.async_record(attempt)
            try:
                await coordinator.client.async_send_chat_message(room_id, text)
            except ParroUncertainError as err:
                raise _failure("send_uncertain") from err
            except ParroError as err:
                await guard.async_not_sent(attempt, pause=isinstance(err, ParroRefusedError))
                raise self._error(err) from err
        await coordinator.async_request_refresh()
