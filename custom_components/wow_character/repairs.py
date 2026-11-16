"""Reparaturhinweise mit Dialog: Charakter neu zuordnen oder entfernen.

Fuer "Charakter nicht gefunden", "anderer Charakter" und "nicht mehr gueltig"
(seit 0.24.0). Vorher fuehrte der Weg ueber "Neu konfigurieren" am Charakter.
Schliesst der Dialog ab, loescht Home Assistant den Hinweis selbst.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from . import parsers as p
from .api import BattleNetError, BattleNetNotFound
from .config_flow import (
    character_configured,
    character_data,
    character_input,
    character_schema,
    has_realms,
    suggested_character,
    valid_character,
)
from .const import CONF_GAME_VERSION, CONF_NAMESPACE_SUFFIX, CONF_REGION
from .coordinator import WowConfigEntry


class CharacterRepairFlow(RepairsFlow):
    """Neuen Realm und Namen eintragen oder den Charakter entfernen."""

    def __init__(self, entry_id: str, subentry_id: str) -> None:
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        # Realm-Slug -> Anzeigename
        self._realms: dict[str, str] = {}

    def _character(self) -> tuple[WowConfigEntry | None, ConfigSubentry | None]:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        subentry = entry.subentries.get(self._subentry_id) if entry else None
        return entry, subentry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        _entry, subentry = self._character()
        if subentry is None:
            return self.async_abort(reason="character_removed")
        return self.async_show_menu(
            step_id="init",
            menu_options=["character", "remove"],
            description_placeholders={"character": subentry.title},
        )

    async def async_step_character(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Realm und Name eintragen, wie bei "Neu konfigurieren"."""
        entry, subentry = self._character()
        if entry is None or subentry is None:
            return self.async_abort(reason="character_removed")
        if entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")
        client = entry.runtime_data.client
        data = subentry.data
        region, suffix = data[CONF_REGION], data[CONF_NAMESPACE_SUFFIX]
        with_realms = has_realms(data[CONF_GAME_VERSION])
        if with_realms and not self._realms:
            try:
                realms = await client.get_realms(region, suffix)
            except BattleNetError:
                return self.async_abort(reason="cannot_connect")
            self._realms = {r["slug"]: r["name"] for r in realms}
        errors: dict[str, str] = {}
        if user_input is not None:
            realm, character = character_input(with_realms, user_input)
            if not valid_character(character):
                errors["base"] = "invalid_character"
            elif character_configured(
                entry, region, suffix, realm, character, skip=subentry.subentry_id
            ):
                errors["base"] = "already_configured"
            else:
                try:
                    profile = await client.get_profile(region, realm, character, suffix)
                except BattleNetNotFound:
                    errors["base"] = "character_not_found"
                except BattleNetError:
                    errors["base"] = "cannot_connect"
                else:
                    # Laedt den Eintrag neu (Update-Listener); dabei kommen die
                    # Werte unter dem neuen Namen, Geraet und Entitaeten bleiben.
                    self.hass.config_entries.async_update_subentry(
                        entry,
                        subentry,
                        title=p.character_title(
                            profile, character, self._realms.get(realm, realm)
                        ),
                        data=character_data(subentry, realm, character, profile),
                    )
                    return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="character" if with_realms else "character_no_realm",
            data_schema=self.add_suggested_values_to_schema(
                character_schema(self._realms if with_realms else None),
                user_input or suggested_character(data),
            ),
            errors=errors,
            description_placeholders={"character": subentry.title},
        )

    async def async_step_character_no_realm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Name ohne Realm (Forever); Ablauf wie async_step_character."""
        return await self.async_step_character(user_input)

    async def async_step_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Charakter mit Geraet und Entitaeten entfernen, nach Bestaetigung."""
        entry, subentry = self._character()
        if entry is None or subentry is None:
            return self.async_abort(reason="character_removed")
        if user_input is not None:
            self.hass.config_entries.async_remove_subentry(entry, subentry.subentry_id)
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="remove",
            data_schema=vol.Schema({}),
            description_placeholders={"character": subentry.title},
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Dialog zum Hinweis eines Charakters (siehe WowCoordinator._create_issue)."""
    assert data is not None
    return CharacterRepairFlow(str(data["entry_id"]), str(data["subentry_id"]))
