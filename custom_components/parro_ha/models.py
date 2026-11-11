from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit

_MIDNIGHT = time(0, 0)
_MEDIA_HOST_SUFFIXES = ("cloudfront.net", "parnassys.net", "parro.com")
_DIRECT_ROOM_TYPES = frozenset({"SINGLE", "FAMILY"})
_UNREAD_KEYS = (
    "numberOfUnreadAnnouncements",
    "numberOfUnreadCalendarItems",
    "numberOfUnreadChatRooms",
    "numberOfUnreadSystemNewsItems",
)


def _str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _strings(value: Any) -> tuple[str, ...]:
    items = value if isinstance(value, list) else []
    return tuple(item.strip() for item in items if isinstance(item, str) and item.strip())


def _self_id(data: Mapping[str, Any]) -> int | None:
    links = (link for link in _mappings(data.get("links")) if link.get("rel") == "self")
    return next((link_id for link in links if (link_id := _int(link.get("id"))) is not None), None)


def _role_ids(items: Iterable[Mapping[str, Any]]) -> tuple[int, ...]:
    return tuple(role_id for item in items if (role_id := _int(item.get("roleId"))) is not None)


def _media_url(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    return value if is_media_url(value) else None


def is_media_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and parts.username is None
        and parts.password is None
        and port in (None, 443)
        and any(host == suffix or host.endswith(f".{suffix}") for suffix in _MEDIA_HOST_SUFFIXES)
    )


def parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None and 1 < parsed.year < 9999 else None


def parse_items[T](rows: Iterable[Mapping[str, Any]], factory: Callable[[Mapping[str, Any]], T | None]) -> list[T]:
    return [item for row in rows if (item := factory(row)) is not None]


def full_name(person: Mapping[str, Any]) -> str:
    return " ".join(part for part in (_str(person, "firstname"), _str(person, "surname")) if part)


@dataclass(frozen=True, slots=True)
class ParroAccount:
    account_id: int
    guardian_id: int | None
    own_ids: frozenset[int]

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ParroAccount | None:
        if (account_id := _self_id(data)) is None:
            return None
        identity = _mapping(data.get("identity"))
        guardian_ids = parse_items(_mappings(identity.get("guardians")), _self_id)
        identity_id = _self_id(identity)
        return cls(
            account_id=account_id,
            guardian_id=min(guardian_ids, default=None),
            own_ids=frozenset(guardian_ids if identity_id is None else [*guardian_ids, identity_id]),
        )


@dataclass(frozen=True, slots=True)
class ParroChild:
    child_id: int
    first_name: str
    avatar_url: str | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ParroChild | None:
        child_id = _self_id(data)
        if child_id is None or data.get("archived") is True:
            return None
        return cls(child_id, _str(data, "firstname"), _media_url(data, "cachedAvatarUrl"))


@dataclass(frozen=True, slots=True)
class ParroGroup:
    group_id: int
    name: str
    group_type: str
    is_class: bool
    school_year: int | None
    unread_count: int
    child_ids: tuple[int, ...]
    last_announcement_title: str | None
    last_announcement_at: datetime | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ParroGroup | None:
        if (group_id := _self_id(data)) is None:
            return None
        last = _mapping(data.get("lastAnnouncement"))
        return cls(
            group_id=group_id,
            name=_str(data, "name"),
            group_type=_str(data, "type"),
            is_class=data.get("stamgroep") is True,
            school_year=_int(data.get("schooljaar")),
            unread_count=_int(data.get("unreadCount")) or 0,
            child_ids=_role_ids(_mappings(data.get("childAvatars"))),
            last_announcement_title=_str(last, "title") or None,
            last_announcement_at=parse_datetime(last.get("date")),
        )


@dataclass(frozen=True, slots=True)
class ParroAttachment:
    kind: str
    url: str | None
    thumbnail_url: str | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ParroAttachment:
        kind = _str(data, "attachmentType") or "FILE"
        url = thumbnail = None
        for entry in _mappings(data.get("entries")):
            if entry.get("type") == "THUMBNAIL":
                thumbnail = thumbnail or _media_url(entry, "url")
            elif entry.get("type") == "SOURCE" and kind == "IMAGE":
                url = url or _media_url(entry, "url")
        return cls(kind, url, thumbnail)

    @property
    def preview_url(self) -> str | None:
        return self.thumbnail_url or self.url


@dataclass(frozen=True, slots=True)
class ParroAnnouncement:
    announcement_id: int
    group_name: str
    title: str
    text: str
    published: datetime | None
    author: str
    read: bool
    pinned: bool
    attachments: tuple[ParroAttachment, ...]

    @classmethod
    def from_api(cls, data: Mapping[str, Any], group: ParroGroup) -> ParroAnnouncement | None:
        announcement_id = _self_id(data)
        if announcement_id is None or data.get("deleted") is True or data.get("draft") is True:
            return None
        return cls(
            announcement_id=announcement_id,
            group_name=group.name,
            title=_str(data, "title"),
            text=_str(data, "contents"),
            published=parse_datetime(data.get("sortDate")) or parse_datetime(data.get("createdAt")),
            author=full_name(_mapping(data.get("owner"))),
            read=data.get("read") is True,
            pinned=data.get("pinned") is True,
            attachments=tuple(map(ParroAttachment.from_api, _mappings(data.get("attachments")))),
        )

    @property
    def images(self) -> tuple[ParroAttachment, ...]:
        return tuple(item for item in self.attachments if item.kind == "IMAGE")


@dataclass(frozen=True, slots=True)
class ParroEvent:
    item_id: int
    title: str
    kind: str
    start: date | datetime
    end: date | datetime
    all_day: bool
    group_names: tuple[str, ...]
    child_ids: tuple[int, ...]

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ParroEvent | None:
        item = _mapping(row.get("calendarItem"))
        item_id = _self_id(item)
        start = parse_datetime(item.get("startDate"))
        end = parse_datetime(item.get("endDate")) or start
        if (
            item_id is None
            or start is None
            or end is None
            or row.get("deleted") is True
            or row.get("cancelled") is True
        ):
            return None
        all_day = start.time() == _MIDNIGHT and end.time() == _MIDNIGHT
        span: tuple[date | datetime, date | datetime]
        if all_day:
            span = (start.date(), max(end.date(), start.date()) + timedelta(days=1))
        else:
            span = (start, end if end > start else start + timedelta(hours=1))
        return cls(
            item_id=item_id,
            title=_str(item, "title"),
            kind=_str(item, "type"),
            start=span[0],
            end=span[1],
            all_day=all_day,
            group_names=tuple(name for group in _mappings(row.get("groups")) if (name := _str(group, "name"))),
            child_ids=_role_ids(_mapping(entry.get("child")) for entry in _mappings(row.get("children"))),
        )


def events_from_rows(rows: Iterable[Mapping[str, Any]]) -> list[ParroEvent]:
    events: dict[int, ParroEvent] = {}
    for event in parse_items(rows, ParroEvent.from_row):
        events.setdefault(event.item_id, event)
    return list(events.values())


@dataclass(frozen=True, slots=True)
class ParroChatRoom:
    room_id: int
    room_type: str
    title: str
    member_names: tuple[str, ...]
    unread_count: int
    replies_enabled: bool
    last_message_at: datetime | None
    last_message: str
    last_sender: str
    last_sender_id: int | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> ParroChatRoom | None:
        room_id = _self_id(data)
        if room_id is None or data.get("archived") is True or data.get("active") is False:
            return None
        last = _mapping(data.get("lastMessage"))
        sender = _mapping(last.get("identity"))
        return cls(
            room_id=room_id,
            room_type=_str(data, "type"),
            title=_str(data, "title"),
            member_names=_strings(data.get("memberNames")),
            unread_count=_int(data.get("unreadCount")) or 0,
            replies_enabled=data.get("repliesEnabled") is True,
            last_message_at=parse_datetime(last.get("createdAt")) or parse_datetime(data.get("sortDate")),
            last_message="" if last.get("deleted") is True else _str(last, "text"),
            last_sender=full_name(sender),
            last_sender_id=_self_id(sender),
        )

    @property
    def kind(self) -> str | None:
        return self.room_type.lower() or None

    @property
    def shown_sender(self) -> str | None:
        return (self.last_sender or None) if self.is_direct else None

    @property
    def is_direct(self) -> bool:
        return self.room_type in _DIRECT_ROOM_TYPES

    @property
    def can_reply(self) -> bool:
        return self.is_direct and self.replies_enabled

    @property
    def name(self) -> str:
        return self.title if self.title or not self.is_direct else ", ".join(self.member_names)


@dataclass(frozen=True, slots=True)
class ParroUnreadCounts:
    announcements: int = 0
    calendar_items: int = 0
    chat_rooms: int = 0
    news: int = 0

    @classmethod
    def from_api(cls, rows: list[Mapping[str, Any]], guardian_id: int | None) -> ParroUnreadCounts:
        fallback = rows[0] if len(rows) == 1 else {}
        row = next((row for row in rows if _self_id(_mapping(row.get("guardian"))) == guardian_id), fallback)
        return cls(*(_int(row.get(key)) or 0 for key in _UNREAD_KEYS))
