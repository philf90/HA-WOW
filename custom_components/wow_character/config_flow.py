"""Einrichtungsdialog in zwei Schritten.

1. Zugangsdaten, Region und Spielversion; dabei wird die Realm-Liste geladen
   und fuer Forever der passende Namespace ermittelt.
2. Realm aus der Liste waehlen und Charakternamen eingeben.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
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
    REGIONS,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
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


class WowCharacterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._client: BattleNetClient | None = None
        self._suffix = ""
        # Slug -> angezeigter Name, z. B. "die-aldor" -> "Die Aldor".
        self._realms: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = BattleNetClient(
                async_get_clientsession(self.hass),
                user_input[CONF_REGION],
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
            )
            try:
                suffix, realms = await self._load_realms(
                    client, user_input[CONF_GAME_VERSION]
                )
            except BattleNetAuthError:
                errors["base"] = "invalid_auth"
            except BattleNetNotFound:
                errors["base"] = "realms_not_found"
            except BattleNetError:
                errors["base"] = "cannot_connect"
            else:
                self._user_input = user_input
                self._client = client
                self._suffix = suffix
                self._realms = {r["slug"]: r["name"] for r in realms}
                return await self.async_step_character()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_character(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            realm = user_input[CONF_REALM]
            character = user_input[CONF_CHARACTER].strip()
            try:
                profile = await self._client.get_profile(realm, character, self._suffix)
            except BattleNetNotFound:
                errors["base"] = "character_not_found"
            except BattleNetError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    f"{self._user_input[CONF_REGION]}-"
                    f"{self._client.namespace('profile', self._suffix)}-"
                    f"{realm}-{character.lower()}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{profile.get('name', character)} – {self._realms[realm]}",
                    data={
                        **self._user_input,
                        CONF_REALM: realm,
                        CONF_CHARACTER: character,
                        CONF_NAMESPACE_SUFFIX: self._suffix,
                    },
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
        self, client: BattleNetClient, game_version: str
    ) -> tuple[str, list[dict[str, Any]]]:
        """Namespace-Kandidaten der Reihe nach probieren; erster mit Realms gewinnt."""
        for suffix in GAME_VERSIONS[game_version]["namespaces"]:
            try:
                return suffix, await client.get_realms(suffix)
            except BattleNetNotFound:
                continue
        raise BattleNetNotFound("kein Namespace-Kandidat liefert eine Realm-Liste")
