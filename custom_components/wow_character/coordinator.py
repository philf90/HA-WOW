"""Coordinator: fragt das Profil eines Charakters regelmaessig ab."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BattleNetClient, BattleNetError, BattleNetNotFound
from .const import (
    CONF_CHARACTER,
    CONF_GAME_VERSION,
    CONF_NAMESPACE_SUFFIX,
    CONF_REALM,
    DOMAIN,
    GAME_VERSIONS,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type WowConfigEntry = ConfigEntry[WowCoordinator]


class WowCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Liefert {"profile": {...}, "mythic": {...} oder None}."""

    config_entry: WowConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: WowConfigEntry, client: BattleNetClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.realm: str = entry.data[CONF_REALM]
        self.character: str = entry.data[CONF_CHARACTER]
        self.suffix: str = entry.data[CONF_NAMESPACE_SUFFIX]
        self.game_version: str = entry.data[CONF_GAME_VERSION]

    @property
    def mythic_plus(self) -> bool:
        return GAME_VERSIONS[self.game_version]["mythic_plus"]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            profile = await self.client.get_profile(
                self.realm, self.character, self.suffix
            )
        except BattleNetError as err:
            raise UpdateFailed(str(err)) from err

        mythic = None
        if self.mythic_plus:
            try:
                mythic = await self.client.get_mythic_profile(
                    self.realm, self.character, self.suffix
                )
            except BattleNetNotFound:
                # Charakter ohne Mythic+-Lauf in dieser Season.
                mythic = {}
            except BattleNetError as err:
                raise UpdateFailed(str(err)) from err

        return {"profile": profile, "mythic": mythic}
