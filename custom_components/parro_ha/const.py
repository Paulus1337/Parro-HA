from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, NamedTuple


class IntOption(NamedTuple):
    key: str
    default: int
    minimum: int
    maximum: int

    def read(self, options: Mapping[str, Any]) -> int:
        value = options.get(self.key)
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            return self.default
        try:
            return min(max(int(value), self.minimum), self.maximum)
        except (ValueError, OverflowError):
            return self.default


DOMAIN = "parro_ha"
LOGGER = logging.getLogger(__package__)
MANUFACTURER = "ParnasSys"
WEB_APP_URL = "https://talk.parro.com"

CONF_TOKEN = "token"
CONF_USER = "user"
CONF_ACCOUNT = "account"
CONF_CHAT_DETAILS = "chat_details"
CONF_REPLY_CONVERSATIONS = "reply_conversations"
UPDATE_INTERVAL = IntOption("update_interval", 10, 5, 120)
ANNOUNCEMENT_COUNT = IntOption("announcement_count", 10, 1, 20)
PHOTO_COUNT = IntOption("photo_count", 0, 0, 12)

ACCOUNT_REFRESH_SECONDS = 12 * 3600
EVENT_CACHE_SECONDS = 120
MAX_PARALLEL_REQUESTS = 3
UPCOMING_EVENT_ROWS = 100
CALENDAR_QUERY_ROW_LIMIT = 500
CHAT_ROOM_LIMIT = 50
UPCOMING_EVENT_ATTRIBUTE_LIMIT = 10
CONVERSATION_ATTRIBUTE_LIMIT = 10
TEXT_ATTRIBUTE_LIMIT = 2000
SUMMARY_TEXT_LIMIT = 500
CHAT_PREVIEW_LIMIT = 200

EVENT_NEW_ANNOUNCEMENT = "new_announcement"
EVENT_NEW_CHAT_MESSAGE = "new_chat_message"
SERVICE_SEND_MESSAGE = "send_message"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_CONVERSATION_ID = "conversation_id"
ATTR_MESSAGE = "message"
