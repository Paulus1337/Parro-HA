from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import logging
import math
import re
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .models import (
    ParroAccount,
    ParroAnnouncement,
    ParroChatRoom,
    ParroChild,
    ParroEvent,
    ParroGroup,
    ParroUnreadCounts,
    events_from_rows,
    parse_datetime,
    parse_items,
)

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://rest-v2.parro.com/rest/v2/"
IDP_HOST = "inloggen.parnassys.net"
IDP_BASE_URL = f"https://{IDP_HOST}"
AUTHORIZE_URL = f"{IDP_BASE_URL}/idp/oauth2/authorize"
TOKEN_URL = f"{IDP_BASE_URL}/idp/oauth2/token"
REVOKE_URL = f"{IDP_BASE_URL}/idp/oauth2/revoke"
CLIENT_ID = "W52dbSBQuFp-LF4Xch1r"
REDIRECT_URI = "parro://oauth2"
MEDIA_TYPE = "application/vnd.topicus.geon+json;version=224"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
TOKEN_REFRESH_MARGIN = 120
DEFAULT_TOKEN_LIFETIME = 3600
PAGE_SIZE = 50
ANNOUNCEMENT_DTYPE = "event.RAnnouncementEventPrimer"
CALENDAR_DTYPE = "event.RCalendarItemEventPrimer"
HOME_GROUP_DTYPE = "identity.RHomeGroup"
CHAT_MESSAGE_DTYPE = "chat.RChatTextMessage"
_CONTENT_RANGE = re.compile(r"items\s+\d{1,9}-(\d{1,9})/")
REQUEST_ERRORS = (aiohttp.ClientError, TimeoutError, ValueError)
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,63}|[a-z][a-z_]{2,39}")


class ParroError(Exception): ...


class ParroConnectionError(ParroError): ...


class ParroAuthenticationError(ParroError): ...


class ParroResponseError(ParroError): ...


class ParroForbiddenError(ParroResponseError): ...


class ParroRefusedError(ParroResponseError): ...


class ParroUncertainError(ParroConnectionError): ...


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _decode(body: bytes, *, strict: bool = False) -> Any:
    try:
        return json.loads(body) if body else None
    except (ValueError, RecursionError):
        if strict:
            raise ParroResponseError("Parro sent a response that is not JSON") from None
        return None


def _detail(status: int, data: Any) -> str:
    fields = data if isinstance(data, Mapping) else {}
    codes = (fields.get(key) for key in ("applicationError", "message", "error"))
    code = next((code for code in codes if isinstance(code, str) and _ERROR_CODE.fullmatch(code)), None)
    return f"HTTP {status}, {code}" if code else f"HTTP {status}"


def _items(data: Any) -> list[dict[str, Any]]:
    items = data.get("items") if isinstance(data, Mapping) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def token_claims(token: str | None) -> dict[str, Any]:
    parts = (token or "").split(".")
    if len(parts) != 3:
        return {}
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, RecursionError):
        return {}
    return claims if isinstance(claims, dict) else {}


async def read_body(response: aiohttp.ClientResponse, limit: int = MAX_RESPONSE_BYTES, *, strict: bool = True) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.content.iter_chunked(64 * 1024):
        size += len(chunk)
        if size > limit:
            if strict:
                raise ParroResponseError("Parro sent a response that is too large")
            break
        chunks.append(chunk)
    return b"".join(chunks)


@dataclass(frozen=True, slots=True)
class TokenSet:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    expires_at: float

    @classmethod
    def from_token_response(cls, data: Mapping[str, Any]) -> TokenSet:
        access_token, refresh_token = data.get("access_token"), data.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise ParroResponseError("The Parro sign-in service returned no access token")
        now = time.time()
        lifetime = finite_number(data.get("expires_in"))
        expires_at = finite_number(token_claims(access_token).get("exp"))
        if lifetime is not None and lifetime > 0:
            expires_at = now + lifetime
        elif expires_at is None or expires_at <= now:
            expires_at = now + DEFAULT_TOKEN_LIFETIME
        return cls(
            access_token, refresh_token if isinstance(refresh_token, str) and refresh_token else None, expires_at
        )

    @classmethod
    def from_dict(cls, data: Any) -> TokenSet:
        fields = data if isinstance(data, Mapping) else {}
        access_token, refresh_token = fields.get("access_token"), fields.get("refresh_token")
        expires_at = finite_number(fields.get("expires_at"))
        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(refresh_token, str | None)
            or expires_at is None
        ):
            raise ParroAuthenticationError("The stored Parro session is not usable")
        return cls(access_token, refresh_token or None, expires_at)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def expires_within(self, seconds: float) -> bool:
        return time.time() + seconds >= self.expires_at


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    url: str = field(repr=False)
    state: str = field(repr=False)
    code_verifier: str = field(repr=False)

    @classmethod
    def create(cls) -> AuthorizationRequest:
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode()).digest()
        state = secrets.token_urlsafe(32)
        query = urlencode(
            {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": "openid",
                "state": state,
                "code_challenge": base64.urlsafe_b64encode(digest).rstrip(b"=").decode(),
                "code_challenge_method": "S256",
            }
        )
        return cls(f"{AUTHORIZE_URL}?{query}", state, code_verifier)


class ParroAuth:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def async_exchange_code(self, code: str, code_verifier: str) -> TokenSet:
        tokens = await self._async_token_request(
            "authorization_code", code=code, redirect_uri=REDIRECT_URI, code_verifier=code_verifier
        )
        if tokens.refresh_token is None:
            raise ParroResponseError("The Parro sign-in service returned no renewable session")
        return tokens

    async def async_refresh(self, refresh_token: str) -> TokenSet:
        tokens = await self._async_token_request("refresh_token", refresh_token=refresh_token)
        return tokens if tokens.refresh_token else TokenSet(tokens.access_token, refresh_token, tokens.expires_at)

    async def async_revoke(self, tokens: TokenSet) -> None:
        for hint, token in (("refresh_token", tokens.refresh_token), ("access_token", tokens.access_token)):
            if token is None:
                continue
            form = {"token": token, "token_type_hint": hint, "client_id": CLIENT_ID}
            try:
                async with self._session.post(
                    REVOKE_URL, data=form, timeout=REQUEST_TIMEOUT, allow_redirects=False
                ) as response:
                    _LOGGER.debug("Parro answered the sign-out request with HTTP %s", response.status)
            except REQUEST_ERRORS:
                return

    async def _async_token_request(self, grant_type: str, **fields: str) -> TokenSet:
        form = {"grant_type": grant_type, "client_id": CLIENT_ID, **fields}
        try:
            async with self._session.post(
                TOKEN_URL,
                data=form,
                headers={"Accept": "application/json"},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            ) as response:
                status, data = response.status, _decode(await read_body(response))
        except REQUEST_ERRORS as err:
            raise ParroConnectionError(f"Could not reach the Parro sign-in service ({type(err).__name__})") from None
        if status == 200 and isinstance(data, Mapping):
            return TokenSet.from_token_response(data)
        detail = _detail(status, data)
        if status in (400, 401, 403):
            raise ParroAuthenticationError(f"The Parro sign-in service refused the session ({detail})")
        if status == 429 or status >= 500:
            raise ParroConnectionError(f"The Parro sign-in service is not available ({detail})")
        raise ParroResponseError(f"Unexpected answer from the Parro sign-in service ({detail})")


class ParroClient:
    def __init__(
        self, session: aiohttp.ClientSession, tokens: TokenSet, on_tokens: Callable[[TokenSet], None] | None = None
    ) -> None:
        self._session = session
        self._auth = ParroAuth(session)
        self._tokens = tokens
        self._on_tokens = on_tokens
        self._token_lock = asyncio.Lock()
        self._renewals: set[asyncio.Future[None]] = set()
        self._guardian_id: int | None = None

    @property
    def tokens(self) -> TokenSet:
        return self._tokens

    async def async_ensure_token(self, rejected: str | None = None) -> None:
        if rejected is None and not self._token_lock.locked() and not self._tokens.expires_within(TOKEN_REFRESH_MARGIN):
            return
        renewal = asyncio.ensure_future(self._async_renew(rejected))
        self._renewals.add(renewal)
        renewal.add_done_callback(self._renewal_done)
        await asyncio.wait((renewal,))
        renewal.result()

    def _renewal_done(self, renewal: asyncio.Future[None]) -> None:
        self._renewals.discard(renewal)
        if not renewal.cancelled():
            renewal.exception()

    async def async_settle(self) -> None:
        async with self._token_lock:
            return

    async def _async_renew(self, rejected: str | None) -> None:
        async with self._token_lock:
            tokens = self._tokens
            stale = tokens.expires_within(TOKEN_REFRESH_MARGIN) if rejected is None else rejected == tokens.access_token
            if not stale:
                return
            if tokens.refresh_token is None:
                raise ParroAuthenticationError("The Parro session has ended")
            self._tokens = await self._auth.async_refresh(tokens.refresh_token)
            _LOGGER.debug("Renewed the Parro session for %d seconds", self._tokens.expires_at - time.time())
            if self._on_tokens is not None:
                self._on_tokens(self._tokens)

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        role: bool = True,
    ) -> tuple[int, bytes, str | None]:
        await self.async_ensure_token()
        for retry in (True, False):
            token = self._tokens.access_token
            sent = {"Accept": MEDIA_TYPE, "Authorization": f"Bearer {token}", **(headers or {})}
            if role and self._guardian_id is not None:
                sent["Parro-Authorization-Role"] = f"GUARDIAN:{self._guardian_id}"
            try:
                async with self._session.request(
                    method,
                    f"{API_BASE_URL}{path}",
                    params=params,
                    headers=sent,
                    data=body,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                ) as response:
                    status, content_range = response.status, response.headers.get("Content-Range")
                    received = await read_body(response, strict=method == "GET")
            except REQUEST_ERRORS as err:
                error = ParroConnectionError if method == "GET" else ParroUncertainError
                raise error(f"Could not reach Parro ({type(err).__name__})") from None
            if status != 401 or not retry:
                break
            await self.async_ensure_token(token)
        if status == 401:
            raise ParroResponseError("Parro refused a renewed session")
        return status, received, content_range

    async def _async_get(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        item_range: tuple[int, int] | None = None,
        role: bool = True,
    ) -> tuple[Any, str | None]:
        headers = {"Range": f"items={item_range[0]}-{item_range[1]}"} if item_range else None
        status, body, content_range = await self._async_request("GET", path, params=params, headers=headers, role=role)
        if status in (200, 206):
            return _decode(body, strict=True), content_range
        if status in (204, 416):
            return None, None
        detail = _detail(status, _decode(body))
        if status == 403:
            raise ParroForbiddenError(f"Parro refused access ({detail})")
        if status == 429 or status >= 500:
            raise ParroConnectionError(f"Parro is not available ({detail})")
        raise ParroResponseError(f"Unexpected answer from Parro ({detail})")

    async def _async_get_items(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        limit: int = PAGE_SIZE,
        stop: Callable[[list[dict[str, Any]]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        start = 0
        while len(items) < limit:
            end = start + min(PAGE_SIZE, limit - len(items)) - 1
            data, content_range = await self._async_get(path, params=params, item_range=(start, end))
            page = _items(data)
            items.extend(page)
            match = _CONTENT_RANGE.match(content_range or "")
            last = int(match.group(1)) if match else (end if len(page) == end - start + 1 else -1)
            if not page or last < end or (stop is not None and stop(page)):
                break
            start = last + 1
        return items[:limit]

    async def async_get_account(self) -> ParroAccount:
        data, _ = await self._async_get("account/me", role=False)
        account = ParroAccount.from_api(data) if isinstance(data, Mapping) else None
        if account is None:
            raise ParroResponseError("Parro returned no account details")
        self._guardian_id = account.guardian_id
        return account

    async def async_get_children(self) -> dict[int, ParroChild]:
        children = parse_items(await self._async_get_items("child"), ParroChild.from_api)
        return {child.child_id: child for child in children}

    async def async_get_groups(self) -> dict[int, ParroGroup]:
        rows = await self._async_get_items("group", params={"dtype": HOME_GROUP_DTYPE})
        return {group.group_id: group for group in parse_items(rows, ParroGroup.from_api)}

    async def async_get_unread_counts(self) -> ParroUnreadCounts:
        return ParroUnreadCounts.from_api(await self._async_get_items("identity/unreadcounts"), self._guardian_id)

    async def async_get_announcements(self, group: ParroGroup, limit: int) -> list[ParroAnnouncement]:
        params = {"dtype": ANNOUNCEMENT_DTYPE, "group": str(group.group_id)}
        rows = await self._async_get_items("event", params=params, limit=limit)
        return parse_items(rows, lambda row: ParroAnnouncement.from_api(row, group))

    async def async_get_events(self, since: datetime, *, limit: int, until: datetime | None = None) -> list[ParroEvent]:
        def reached_until(page: list[dict[str, Any]]) -> bool:
            last = parse_datetime(page[-1].get("sortDate"))
            return until is not None and last is not None and last >= until

        params = {
            "dtype": CALENDAR_DTYPE,
            "sort": "desc-stream",
            "sortDateSince": since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        }
        return events_from_rows(await self._async_get_items("event", params=params, limit=limit, stop=reached_until))

    async def async_get_chat_rooms(self, limit: int = PAGE_SIZE) -> list[ParroChatRoom]:
        return parse_items(await self._async_get_items("chatroom", limit=limit), ParroChatRoom.from_api)

    async def async_send_chat_message(self, room_id: int, text: str) -> None:
        message = {"dtype": CHAT_MESSAGE_DTYPE, "links": [], "deleted": False, "text": text, "allRead": False}
        payload = json.dumps({"items": [message]}, ensure_ascii=False, separators=(",", ":")).encode()
        status, body, _ = await self._async_request(
            "POST", f"chatroom/{int(room_id)}/chatmessage", headers={"Content-Type": MEDIA_TYPE}, body=payload
        )
        if 200 <= status < 300:
            return
        detail = _detail(status, _decode(body))
        if status in (403, 429):
            raise ParroRefusedError(f"Parro refused the message ({detail})")
        if 400 <= status < 500:
            raise ParroResponseError(f"Parro did not take the message ({detail})")
        raise ParroUncertainError(f"Parro did not confirm the message ({detail})")
