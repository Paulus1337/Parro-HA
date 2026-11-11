from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
from homeassistant.components.http import KEY_HASS_USER
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession, async_get_clientsession
from homeassistant.helpers.http import current_request
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import ParroAuthenticationError, ParroClient, ParroConnectionError, ParroError, ParroForbiddenError, TokenSet
from .const import (
    ANNOUNCEMENT_COUNT,
    CONF_ACCOUNT,
    CONF_CHAT_DETAILS,
    CONF_REPLY_CONVERSATIONS,
    CONF_TOKEN,
    CONF_USER,
    DOMAIN,
    LOGGER,
    PHOTO_COUNT,
    UPDATE_INTERVAL,
    IntOption,
)
from .coordinator import ParroConfigEntry, ParroOptions
from .login import ParroLogin, ParroLoginError


def _text(kind: TextSelectorType, autocomplete: str) -> TextSelector:
    return TextSelector(TextSelectorConfig(type=kind, autocomplete=autocomplete))


def _number(option: IntOption, unit: str | None = None) -> dict[vol.Marker, vol.All]:
    config = NumberSelectorConfig(min=option.minimum, max=option.maximum, step=1, mode=NumberSelectorMode.BOX)
    if unit is not None:
        config["unit_of_measurement"] = unit
    return {vol.Required(option.key, default=option.default): vol.All(NumberSelector(config), vol.Coerce(int))}


def _choice(
    options: list[SelectOptionDict], *, multiple: bool = False, mode: SelectSelectorMode = SelectSelectorMode.LIST
) -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(options=options, multiple=multiple, mode=mode))


def _error(err: ParroError) -> tuple[str, dict[str, str]]:
    if isinstance(err, ParroLoginError):
        return err.reason, {} if err.attempts_left is None else {"attempts": str(err.attempts_left)}
    if isinstance(err, ParroConnectionError):
        return "cannot_connect", {}
    LOGGER.warning("Signing in to Parro did not work: %s", err)
    return "login_changed", {}


SIGN_IN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): _text(TextSelectorType.TEXT, "username"),
        vol.Required(CONF_PASSWORD): _text(TextSelectorType.PASSWORD, "current-password"),
    }
)
OPTIONS_SCHEMA = vol.Schema(
    {
        **_number(UPDATE_INTERVAL, "min"),
        **_number(ANNOUNCEMENT_COUNT),
        **_number(PHOTO_COUNT),
        vol.Required(CONF_CHAT_DETAILS, default=False): BooleanSelector(),
    }
)


class ParroConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._login: ParroLogin | None = None
        self._accounts: list[str] = []
        self._step = "user"
        self._running = False
        self._interrupted = False
        self._schema = SIGN_IN_SCHEMA
        self._user: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ParroConfigEntry) -> ParroOptionsFlow:
        return ParroOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None and not self._running:
            self._user = user_input[CONF_USER]
        users = {
            user.id: user.name or user.id
            for user in await self.hass.auth.async_get_users()
            if user.is_active and not user.system_generated
        }
        request = current_request.get()
        current = request.get(KEY_HASS_USER) if request is not None else None
        default = self._user or (current.id if current is not None and current.id in users else vol.UNDEFINED)
        options = [SelectOptionDict(value=user_id, label=name) for user_id, name in users.items()]
        choice = _choice(options, mode=SelectSelectorMode.DROPDOWN)
        self._schema = SIGN_IN_SCHEMA.extend({vol.Required(CONF_USER, default=default): choice})
        return await self._async_step_sign_in("user", user_input)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._user = entry_data.get(CONF_USER)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_step_sign_in("reauth_confirm", user_input)

    async def _async_step_sign_in(self, step_id: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        self._step = step_id
        if user_input is None:
            return self._show_sign_in()
        username = user_input[CONF_USERNAME].strip()
        if self._running or self._interrupted:
            self._interrupted = False
            return self._show_sign_in({"base": "sign_in_uncertain"}, None, username)
        if not username or not user_input[CONF_PASSWORD]:
            return self._fail("missing_credentials", username=username)
        self._running = True
        try:
            return await self._async_sign_in(username, user_input[CONF_PASSWORD])
        except BaseException:
            self._interrupted = True
            raise
        finally:
            self._running = False

    async def _async_sign_in(self, username: str, password: str) -> ConfigFlowResult:
        self._close_session()
        self._session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar())
        self._login = ParroLogin(self._session)
        try:
            result = await self._login.async_sign_in(username, password)
        except ParroError as err:
            return self._fail(*_error(err), username)
        if isinstance(result, TokenSet):
            return await self._async_finish(result)
        self._accounts = result
        return await self.async_step_account()

    async def async_step_account(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None or self._login is None:
            options = [SelectOptionDict(value=str(index), label=label) for index, label in enumerate(self._accounts)]
            return self.async_show_form(
                step_id="account", data_schema=vol.Schema({vol.Required(CONF_ACCOUNT): _choice(options)})
            )
        try:
            tokens = await self._login.async_choose(int(user_input[CONF_ACCOUNT]))
        except ParroError as err:
            return self._fail(*_error(err))
        return await self._async_finish(tokens)

    async def _async_finish(self, tokens: TokenSet) -> ConfigFlowResult:
        self._close_session()
        client = ParroClient(async_get_clientsession(self.hass), tokens)
        try:
            account = await client.async_get_account()
        except (ParroAuthenticationError, ParroForbiddenError):
            return self._fail("account_rejected")
        except ParroConnectionError:
            return self._fail("cannot_connect")
        except ParroError as err:
            LOGGER.warning("Reading the Parro account did not work: %s", err)
            return self._fail("unknown")
        if account.guardian_id is None:
            return self._fail("not_a_parent")
        data = {CONF_TOKEN: client.tokens.as_dict()}
        if self._user:
            data[CONF_USER] = self._user
        if self.source == SOURCE_REAUTH:
            if str(account.account_id) != (entry := self._get_reauth_entry()).unique_id:
                return self._fail("wrong_account")
            return self.async_update_reload_and_abort(entry, data=data)
        await self.async_set_unique_id(str(account.account_id))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Parro", data=data)

    def _fail(
        self, error: str, placeholders: dict[str, str] | None = None, username: str | None = None
    ) -> ConfigFlowResult:
        self._close_session()
        return self._show_sign_in({"base": error}, placeholders, username)

    def _show_sign_in(
        self,
        errors: dict[str, str] | None = None,
        placeholders: dict[str, str] | None = None,
        username: str | None = None,
    ) -> ConfigFlowResult:
        suggested = {CONF_USERNAME: username} if username else None
        return self.async_show_form(
            step_id=self._step,
            data_schema=self.add_suggested_values_to_schema(self._schema, suggested),
            errors=errors,
            description_placeholders=placeholders,
        )

    def _close_session(self) -> None:
        session, self._session, self._login = self._session, None, None
        if session is not None:
            session.detach()

    @callback
    def async_remove(self) -> None:
        self._close_session()


class ParroOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        options = dict(self.config_entry.options)
        allowed = sorted(map(str, ParroOptions.from_mapping(options).reply_conversations))
        if user_input is not None:
            return self.async_create_entry(data={CONF_REPLY_CONVERSATIONS: allowed, **user_input})
        schema = OPTIONS_SCHEMA
        if (conversations := await self._async_conversations()) is not None and (conversations or allowed):
            listed = {option["value"] for option in conversations}
            options[CONF_REPLY_CONVERSATIONS] = [room_id for room_id in allowed if room_id in listed]
            choice = _choice(conversations, multiple=True)
            schema = schema.extend({vol.Required(CONF_REPLY_CONVERSATIONS, default=[]): choice})
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(schema, options))

    async def _async_conversations(self) -> list[SelectOptionDict] | None:
        entry = self.config_entry
        if entry.state is not ConfigEntryState.LOADED:
            return None
        try:
            rooms = await entry.runtime_data.async_get_chat_rooms()
        except ParroError:
            return None
        return [
            SelectOptionDict(value=str(room.room_id), label=room.name or str(room.room_id))
            for room in rooms
            if room.can_reply
        ]
