"""Basisklassen fuer Charakter- und Spielwelt-Entitaeten."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN, GAME_VERSIONS
from .coordinator import WowWorldCoordinator


class EntityAdder:
    """Legt Entitaeten an, sobald ihre Bedingung erfuellt ist, auch nach dem Start.

    Die Plattformen rufen add() beim Start und bei jeder Aktualisierung ihrer
    Coordinators mit allen Entitaeten auf, die es nach den Daten geben soll,
    als (Schluessel, Fabrik). Neu angelegt wird nur, was noch fehlt. Faellt eine
    Bedingung spaeter weg (z. B. Gilde verlassen), bleibt die Entitaet bis zum
    Neuladen und zeigt "unbekannt".
    """

    def __init__(
        self,
        add_entities: Callable[[list[Entity]], None],
        allowed: Callable[[str], bool] | None = None,
    ) -> None:
        self._add_entities = add_entities
        # Schluessel ausgeschalteter Gruppen (Optionen) werden nie angelegt.
        self._allowed = allowed or (lambda _key: True)
        # Schluessel nach der unique_id des Charakters bzw. der Spielwelt
        self.known: set[str] = set()

    @callback
    def add(self, candidates: Iterable[tuple[str, Callable[[], Entity]]]) -> None:
        new = []
        for key, factory in candidates:
            if key not in self.known and self._allowed(key):
                self.known.add(key)
                new.append(factory())
        if new:
            self._add_entities(new)


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
            # z. B. "World of Warcraft" (Retail), "World of Warcraft Classic Era"
            model=f"World of Warcraft{GAME_VERSIONS[coordinator.game_version]['label']}",
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
