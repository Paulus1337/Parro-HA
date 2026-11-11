from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
import secrets
from urllib.parse import parse_qs, urljoin, urlsplit

import aiohttp

from .api import (
    IDP_HOST,
    REQUEST_ERRORS,
    REQUEST_TIMEOUT,
    AuthorizationRequest,
    ParroAuth,
    ParroConnectionError,
    ParroError,
    ParroResponseError,
    TokenSet,
    read_body,
)

MAX_REQUESTS = 40
MAX_PAGE_BYTES = 512 * 1024
_AJAX_ACCEPT = "application/xml, text/xml, */*; q=0.01"
_FINAL_REASONS = frozenset({"account_locked", "account_rejected", "two_factor"})
_ATTEMPTS = re.compile(r"\b(\d{1,3})\s+(?:attempts?|poging(?:en)?)\b", re.IGNORECASE)
_LOCKED = re.compile(r"geblokkeerd|blocked|locked", re.IGNORECASE)
_REQUIRED = re.compile(r"verplicht|required", re.IGNORECASE)
_ONE_TIME_CODE = re.compile(r"totp|otp|verificatie|authenticator", re.IGNORECASE)
_FEEDBACK = re.compile(r'<(\w+)[^>]*class="[^"]*feedbackPanelERROR[^"]*"[^>]*>(.*?)</\1>', re.IGNORECASE | re.DOTALL)
_CHOOSER_LINK = re.compile(r'"u":"([^"]*accountKeuze-accounts-account-\d+)","c":"([^"]+)"')
_ACCOUNT_PART = re.compile(r'<span[^>]*class="[^"]*account-list__(name|role)[^"]*"[^>]*>')
_AJAX_BASE = re.compile(r'Wicket\.Ajax\.baseUrl="([^"]*)"')
_AJAX_REDIRECT = re.compile(r"<redirect><!\[CDATA\[(.*?)\]\]></redirect>", re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")


class ParroLoginError(ParroError):
    def __init__(self, reason: str, attempts_left: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.attempts_left = attempts_left


@dataclass(frozen=True, slots=True, repr=False)
class _Page:
    url: str
    status: int
    location: str | None
    html: str


@dataclass(frozen=True, slots=True, repr=False)
class _Account:
    label: str
    url: str
    focus_id: str


@dataclass(frozen=True, slots=True, repr=False)
class _LoginForm:
    action: str
    hidden: dict[str, str]
    username_field: str
    password_field: str


@dataclass(slots=True, repr=False)
class _Form:
    action: str
    inputs: list[dict[str, str]] = field(default_factory=list)

    def named(self, *types: str) -> list[dict[str, str]]:
        return [item for item in self.inputs if item.get("name") and item.get("type", "text").lower() in types]


class _FormParser(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[_Form] = []
        self._open = False
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if tag == "form":
            self.forms.append(_Form(attributes.get("action", "")))
            self._open = True
        elif tag == "input" and self._open:
            self.forms[-1].inputs.append(attributes)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._open = False


def _join(base: str, url: str) -> str:
    try:
        return urljoin(base, url)
    except ValueError:
        return ""


def _on_sign_in_host(url: str) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname == IDP_HOST
        and port in (None, 443)
        and parts.username is None
        and parts.password is None
    )


def _callback(location: str) -> dict[str, list[str]]:
    try:
        parts = urlsplit(location)
        port = parts.port
    except ValueError:
        return {}
    valid = (
        parts.scheme == "parro"
        and parts.hostname == "oauth2"
        and port in (None, 443)
        and parts.path in ("", "/")
        and parts.username is None
        and parts.password is None
        and not parts.fragment
    )
    return parse_qs(parts.query, keep_blank_values=True) if valid else {}


def _text(html: str) -> str:
    return " ".join(unescape(_TAGS.sub(" ", html)).split())


def _login_form(page: _Page) -> _LoginForm | None:
    forms = [
        form
        for form in _FormParser(page.html).forms
        if "signInForm" in form.action and len(form.named("password")) == 1 and form.named("text", "email")
    ]
    action = _join(page.url, forms[0].action) if len(forms) == 1 else ""
    if not _on_sign_in_host(action):
        return None
    users = forms[0].named("text", "email")
    user = next((item for item in users if item.get("autocomplete") == "username"), users[0])
    hidden = {item["name"]: item.get("value", "") for item in forms[0].named("hidden")}
    return _LoginForm(action, hidden, user["name"], forms[0].named("password")[0]["name"])


def _asks_one_time_code(html: str) -> bool:
    inputs = [item for form in _FormParser(html).forms for item in form.inputs]
    return any(
        item.get("autocomplete") == "one-time-code" or _ONE_TIME_CODE.search(item.get("name", "")) for item in inputs
    )


def _rejection(html: str) -> ParroLoginError:
    message = " ".join(_text(body) for _, body in _FEEDBACK.findall(html))
    attempts = int(match.group(1)) if (match := _ATTEMPTS.search(message)) else None
    if not message:
        return ParroLoginError("sign_in_uncertain")
    if _REQUIRED.search(message):
        return ParroLoginError("login_changed")
    if attempts == 0 or (attempts is None and _LOCKED.search(message)):
        return ParroLoginError("account_locked")
    return ParroLoginError("invalid_auth" if attempts is None else "invalid_auth_attempts", attempts)


def _accounts(page: _Page) -> list[_Account]:
    accounts: list[_Account] = []
    for url, focus_id in dict.fromkeys(_CHOOSER_LINK.findall(page.html)):
        item = re.search(rf'<li[^>]*id="{re.escape(focus_id)}"[^>]*>(.*?)</li>', page.html, re.DOTALL)
        parts = _ACCOUNT_PART.split(item.group(1)) if item else []
        fields = dict(zip(parts[1::2], map(_text, parts[2::2]), strict=False))
        name, role = fields.get("name", ""), fields.get("role", "")
        accounts.append(_Account(f"{name} ({role})" if name and role else name, _join(page.url, url), focus_id))
    return accounts


class ParroLogin:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._request = AuthorizationRequest.create()
        self._accounts: list[_Account] = []
        self._ajax_base = ""
        self._requests = 0

    async def async_sign_in(self, username: str, password: str) -> TokenSet | list[str]:
        page = await self._async_redirects(await self._async_fetch(self._request.url))
        form = _login_form(page) if page.status == 200 and page.location is None else None
        if form is None:
            raise ParroLoginError("login_changed")
        data = {**form.hidden, form.username_field: username, form.password_field: password, "aanmelden": "x"}
        try:
            page = await self._async_redirects(await self._async_fetch(form.action, data=data))
        except (ParroConnectionError, ParroResponseError):
            raise ParroLoginError("sign_in_uncertain") from None
        return await self._async_result(page)

    async def async_choose(self, index: int) -> TokenSet:
        if not 0 <= index < len(self._accounts):
            raise ParroLoginError("choice_expired")
        account = self._accounts[index]
        headers = {
            "Accept": _AJAX_ACCEPT,
            "Wicket-Ajax": "true",
            "Wicket-Ajax-BaseURL": self._ajax_base,
            "Wicket-FocusedElementId": account.focus_id,
            "X-Requested-With": "XMLHttpRequest",
        }
        page = await self._async_fetch(account.url, headers=headers)
        if page.location is None and (match := _AJAX_REDIRECT.search(page.html)):
            page = _Page(page.url, page.status, _join(page.url, match.group(1).strip()), "")
        try:
            result = await self._async_result(await self._async_redirects(page))
        except ParroLoginError as err:
            if err.reason in _FINAL_REASONS:
                raise
            result = None
        if not isinstance(result, TokenSet):
            raise ParroLoginError("choice_expired")
        return result

    async def _async_redirects(self, page: _Page) -> _Page:
        while page.location is not None and not page.location.lower().startswith("parro:"):
            page = await self._async_fetch(page.location)
        return page

    async def _async_result(self, page: _Page) -> TokenSet | list[str]:
        if page.location is not None:
            return await self._async_exchange(page.location)
        if page.status != 200:
            raise ParroLoginError("login_changed")
        if accounts := _accounts(page):
            labels = [account.label for account in accounts]
            urls_valid = all(_on_sign_in_host(account.url) for account in accounts)
            if not all(labels) or len(set(labels)) != len(labels) or not urls_valid:
                raise ParroLoginError("login_changed")
            base = _AJAX_BASE.search(page.html)
            self._accounts = accounts
            self._ajax_base = base.group(1) if base else urlsplit(page.url).path
            return labels
        if _login_form(page) is not None:
            raise _rejection(page.html)
        raise ParroLoginError("two_factor" if _asks_one_time_code(page.html) else "login_changed")

    async def _async_exchange(self, location: str) -> TokenSet:
        params = _callback(location)
        state, code, issuer = (params.get(key, []) for key in ("state", "code", "iss"))
        state_valid = len(state) == 1 and secrets.compare_digest(state[0].encode(), self._request.state.encode())
        if not state_valid or len(issuer) > 1 or not all(map(_on_sign_in_host, issuer)):
            raise ParroLoginError("login_changed")
        if "error" in params:
            raise ParroLoginError("account_rejected")
        if len(code) != 1 or not code[0]:
            raise ParroLoginError("login_changed")
        return await ParroAuth(self._session).async_exchange_code(code[0], self._request.code_verifier)

    async def _async_fetch(
        self, url: str, *, data: dict[str, str] | None = None, headers: dict[str, str] | None = None
    ) -> _Page:
        self._requests += 1
        if self._requests > MAX_REQUESTS or not _on_sign_in_host(url):
            raise ParroLoginError("login_changed")
        try:
            async with self._session.request(
                "GET" if data is None else "POST",
                url,
                data=data,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
            ) as response:
                status = response.status
                location = response.headers.get("Location") or response.headers.get("Ajax-Location")
                html = (await read_body(response, MAX_PAGE_BYTES)).decode(errors="replace")
        except REQUEST_ERRORS as err:
            raise ParroConnectionError(f"Could not reach the Parro sign-in page ({type(err).__name__})") from None
        if status == 429 or status >= 500:
            raise ParroConnectionError(f"The Parro sign-in page returned HTTP {status}")
        return _Page(url, status, _join(url, location.strip()) if location else None, html)
