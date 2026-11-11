from __future__ import annotations

import math
import re
import time
from typing import Any

from homeassistant.core import HomeAssistant

from .api import TokenSet, finite_number, token_claims
from .const import CONF_USER
from .coordinator import ParroConfigEntry

_KIND = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}")


def _kinds(values: Any) -> list[str]:
    return sorted({value for value in values if _KIND.fullmatch(value)})


def _seconds(later: Any, earlier: Any) -> int | None:
    later, earlier = finite_number(later), finite_number(earlier)
    difference = None if later is None or earlier is None else later - earlier
    return round(difference) if difference is not None and math.isfinite(difference) else None


def _session(tokens: TokenSet) -> dict[str, Any]:
    now = time.time()
    claims = token_claims(tokens.refresh_token)
    issued, expires, count = claims.get("iat"), claims.get("exp"), claims.get("refresh_count")
    return {
        "access_token_expires_in": round(tokens.expires_at - now),
        "has_refresh_token": tokens.refresh_token is not None,
        "refresh_token_age": _seconds(now, issued),
        "refresh_token_expires_in": _seconds(expires, now),
        "refresh_token_lifetime": _seconds(expires, issued),
        "refresh_count": count if isinstance(count, int) and not isinstance(count, bool) else None,
    }


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ParroConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    options, data = coordinator.options, coordinator.data
    return {
        "options": {
            "update_interval": options.update_interval,
            "announcement_count": options.announcement_count,
            "photo_count": options.photo_count,
            "chat_details": options.chat_details,
            "reply_conversations": len(options.reply_conversations),
        },
        "linked_user": bool(entry.data.get(CONF_USER)),
        "session": _session(coordinator.client.tokens),
        "last_update_success": coordinator.last_update_success,
        "data": {
            "children": len(data.children),
            "groups": [
                {
                    "type": group.group_type if _KIND.fullmatch(group.group_type) else None,
                    "is_class": group.is_class,
                    "school_year": group.school_year,
                    "unread": group.unread_count,
                    "linked_children": len(group.child_ids),
                }
                for group in data.groups.values()
            ],
            "announcements": len(data.announcements),
            "announcements_with_photos": sum(1 for item in data.announcements if item.images),
            "attachment_kinds": _kinds(
                attachment.kind for item in data.announcements for attachment in item.attachments
            ),
            "upcoming_events": len(data.events),
            "event_kinds": _kinds(event.kind for event in data.events),
            "photos": len(data.photos),
            "chat_rooms": None if data.chat_rooms is None else len(data.chat_rooms),
            "chat_room_kinds": _kinds(room.room_type for room in data.chat_rooms or []),
            "replies_enabled": sum(1 for room in data.chat_rooms or [] if room.can_reply),
            "unread": {
                "announcements": data.unread.announcements,
                "calendar_items": data.unread.calendar_items,
                "chat_rooms": data.unread.chat_rooms,
                "news": data.unread.news,
            },
        },
    }
