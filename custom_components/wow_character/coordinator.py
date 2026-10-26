"""Coordinator: fragt das Profil eines Charakters regelmaessig ab."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BattleNetAuthError, BattleNetClient, BattleNetError, BattleNetNotFound
from .const import (
    CONF_CHARACTER,
    CONF_GAME_VERSION,
    CONF_NAMESPACE_SUFFIX,
    CONF_REALM,
    CONF_REGION,
    DOMAIN,
    GAME_VERSIONS,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class WowRuntimeData:
    """Gemeinsamer API-Client und ein Coordinator je Charakter-Untereintrag."""

    client: BattleNetClient
    coordinators: dict[str, WowCoordinator] = field(default_factory=dict)


type WowConfigEntry = ConfigEntry[WowRuntimeData]


class WowCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Liefert {"profile": {...}, "mythic": {...} oder None}."""

    config_entry: WowConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WowConfigEntry,
        client: BattleNetClient,
        subentry: ConfigSubentry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.subentry = subentry
        data = subentry.data
        self.region: str = data[CONF_REGION]
        self.realm: str = data[CONF_REALM]
        self.character: str = data[CONF_CHARACTER]
        self.suffix: str = data[CONF_NAMESPACE_SUFFIX]
        self.game_version: str = data[CONF_GAME_VERSION]

    @property
    def mythic_plus(self) -> bool:
        return GAME_VERSIONS[self.game_version]["mythic_plus"]

    async def _async_update_data(self) -> dict[str, Any]:
        args = (self.region, self.realm, self.character, self.suffix)
        try:
            profile = await self.client.get_profile(*args)
        except BattleNetAuthError as err:
            # Startet den Dialog zum erneuten Anmelden am Haupteintrag.
            raise ConfigEntryAuthFailed(str(err)) from err
        except BattleNetError as err:
            raise UpdateFailed(str(err)) from err

        mythic = None
        if self.mythic_plus:
            try:
                mythic = await self.client.get_mythic_profile(*args)
            except BattleNetNotFound:
                # Charakter ohne Mythic+-Lauf in dieser Season.
                mythic = {}
            except BattleNetAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except BattleNetError as err:
                raise UpdateFailed(str(err)) from err

        return {"profile": profile, "mythic": mythic}
