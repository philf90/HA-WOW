"""Basisklassen fuer Charakter- und Spielwelt-Entitaeten."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN, GAME_VERSIONS
from .coordinator import WowWorldCoordinator


class WowCharacterEntity(CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]):
    """Entitaet am Geraet eines Charakters (Profil- oder Detail-Coordinator)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Any, key: str) -> None:
        super().__init__(coordinator)
        # Gleiche IDs wie in Version 0.1 (dort die unique_id des Eintrags),
        # damit Entitaets-IDs und Verlauf erhalten bleiben.
        subentry = coordinator.subentry
        self._attr_unique_id = f"{subentry.unique_id}-{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.unique_id)},
            name=subentry.title,
            manufacturer="Blizzard Entertainment",
            model=f"World of Warcraft ({coordinator.game_version})",
            entry_type=DeviceEntryType.SERVICE,
        )


class WowWorldEntity(CoordinatorEntity[WowWorldCoordinator]):
    """Entitaet am Spielwelt-Geraet einer Region."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WowWorldCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        scope = f"world-{coordinator.region}{coordinator.suffix}"
        self._attr_unique_id = f"{entry.unique_id}-{scope}-{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}-{scope}")},
            translation_key="world",
            translation_placeholders={
                "region": coordinator.region.upper(),
                # z. B. "" (Retail), " Forever" oder " Classic Era"
                "version": GAME_VERSIONS[coordinator.game_version]["label"],
            },
            manufacturer="Blizzard Entertainment",
            model="World of Warcraft",
            entry_type=DeviceEntryType.SERVICE,
        )
