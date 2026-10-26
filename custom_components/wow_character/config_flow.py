"""Einrichtungsdialoge.

Haupteintrag: Client-ID und Secret eines Battle.net-API-Clients, einmalig.
Untereintrag "Charakter": Region und Spielversion, dann Realm aus der
Realm-Liste und Charaktername. Beliebig viele je Haupteintrag.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    BattleNetAuthError,
    BattleNetClient,
    BattleNetError,
    BattleNetNotFound,
)
from .const import (
    CONF_CHARACTER,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_GAME_VERSION,
    CONF_NAMESPACE_SUFFIX,
    CONF_REALM,
    CONF_REGION,
    DOMAIN,
    GAME_VERSIONS,
    MAIN_TITLE,
    REGIONS,
    SUBENTRY_CHARACTER,
)

SECRET_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): SECRET_SELECTOR,
    }
)
CHARACTER_BASE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default="eu"): SelectSelector(
            SelectSelectorConfig(
                options=list(REGIONS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_REGION,
            )
        ),
        vol.Required(CONF_GAME_VERSION, default="retail"): SelectSelector(
            SelectSelectorConfig(
                options=list(GAME_VERSIONS),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_GAME_VERSION,
            )
        ),
    }
)


async def _validate_credentials(hass, client_id: str, client_secret: str) -> str | None:
    """Fehler-Schluessel zurueckgeben oder None, wenn die Zugangsdaten gelten."""
    client = BattleNetClient(async_get_clientsession(hass), client_id, client_secret)
    try:
        await client.validate()
    except BattleNetAuthError:
        return "invalid_auth"
    except BattleNetError:
        return "cannot_connect"
    return None


class WowCharacterConfigFlow(ConfigFlow, domain=DOMAIN):
    # Version 2: Haupteintrag mit Untereintraegen je Charakter.
    VERSION = 2

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_CHARACTER: CharacterSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()
            await self.async_set_unique_id(client_id)
            self._abort_if_unique_id_configured()
            error = await _validate_credentials(
                self.hass, client_id, user_input[CONF_CLIENT_SECRET]
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=MAIN_TITLE,
                    data={
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_credentials_step(
            "reauth_confirm", self._get_reauth_entry(), user_input
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_credentials_step(
            "reconfigure", self._get_reconfigure_entry(), user_input
        )

    async def _async_credentials_step(
        self, step_id: str, entry: ConfigEntry, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Neue Zugangsdaten fuer einen bestehenden Haupteintrag."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID].strip()
            if client_id != entry.unique_id:
                await self.async_set_unique_id(client_id)
                self._abort_if_unique_id_configured()
            error = await _validate_credentials(
                self.hass, client_id, user_input[CONF_CLIENT_SECRET]
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=client_id,
                    data_updates={
                        CONF_CLIENT_ID: client_id,
                        CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET],
                    },
                )
        suggested = user_input or {CONF_CLIENT_ID: entry.data[CONF_CLIENT_ID]}
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, suggested
            ),
            errors=errors,
        )


class CharacterSubentryFlow(ConfigSubentryFlow):
    """Charakter zu einem Haupteintrag hinzufuegen."""

    def __init__(self) -> None:
        self._base: dict[str, Any] = {}
        self._suffix = ""
        # Slug -> angezeigter Name, z. B. "die-aldor" -> "Die Aldor".
        self._realms: dict[str, str] = {}

    @property
    def _client(self) -> BattleNetClient:
        return self._get_entry().runtime_data.client

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                suffix, realms = await self._load_realms(
                    user_input[CONF_REGION], user_input[CONF_GAME_VERSION]
                )
            except BattleNetNotFound:
                errors["base"] = "realms_not_found"
            except BattleNetError:
                errors["base"] = "cannot_connect"
            else:
                self._base = user_input
                self._suffix = suffix
                self._realms = {r["slug"]: r["name"] for r in realms}
                return await self.async_step_character()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                CHARACTER_BASE_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_character(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        region = self._base[CONF_REGION]
        if user_input is not None:
            realm = user_input[CONF_REALM]
            character = user_input[CONF_CHARACTER].strip()
            unique_id = (
                f"{region}-{BattleNetClient.namespace('profile', self._suffix, region)}-"
                f"{realm}-{character.lower()}"
            )
            if any(
                sub.unique_id == unique_id
                for sub in self._get_entry().subentries.values()
            ):
                return self.async_abort(reason="already_configured")
            try:
                profile = await self._client.get_profile(
                    region, realm, character, self._suffix
                )
            except BattleNetNotFound:
                errors["base"] = "character_not_found"
            except BattleNetError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"{profile.get('name', character)} – {self._realms[realm]}",
                    data={
                        **self._base,
                        CONF_REALM: realm,
                        CONF_CHARACTER: character,
                        CONF_NAMESPACE_SUFFIX: self._suffix,
                    },
                    unique_id=unique_id,
                )

        options = [
            SelectOptionDict(value=slug, label=name)
            for slug, name in sorted(
                self._realms.items(), key=lambda item: item[1].casefold()
            )
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_REALM): SelectSelector(
                    SelectSelectorConfig(
                        options=options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(CONF_CHARACTER): str,
            }
        )
        return self.async_show_form(
            step_id="character",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def _load_realms(
        self, region: str, game_version: str
    ) -> tuple[str, list[dict[str, Any]]]:
        """Namespace-Kandidaten der Reihe nach probieren; erster mit Realms gewinnt."""
        for suffix in GAME_VERSIONS[game_version]["namespaces"]:
            try:
                return suffix, await self._client.get_realms(region, suffix)
            except BattleNetNotFound:
                continue
        raise BattleNetNotFound("kein Namespace-Kandidat liefert eine Realm-Liste")
