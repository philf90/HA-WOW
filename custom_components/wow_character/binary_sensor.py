"""Serverstatus und Warteschlange je Realm am Spielwelt-Geraet."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WowConfigEntry, WowWorldCoordinator
from .entity import WowWorldEntity

# Nur Coordinator-Entitaeten ohne eigene Abfragen: keine Begrenzung noetig.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for world in entry.runtime_data.worlds.values():
        for slug, realm in ((world.data or {}).get("realms") or {}).items():
            # Forever: nur Realms, fuer die die API antwortet.
            if world.suffix and realm is None:
                continue
            async_add_entities(
                [WowRealmStatus(world, slug), WowRealmQueue(world, slug)]
            )


class _RealmEntity(WowWorldEntity, BinarySensorEntity):
    def __init__(self, coordinator: WowWorldCoordinator, slug: str, key: str) -> None:
        super().__init__(coordinator, f"realm-{slug}-{key}")
        self._slug = slug
        realm = (coordinator.data or {}).get("realms", {}).get(slug) or {}
        self._attr_translation_placeholders = {"realm": realm.get("name") or slug}

    @property
    def _realm(self) -> dict | None:
        return (self.coordinator.data or {}).get("realms", {}).get(self._slug)


class WowRealmStatus(_RealmEntity):
    _attr_translation_key = "realm_status"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: WowWorldCoordinator, slug: str) -> None:
        super().__init__(coordinator, slug, "status")

    @property
    def is_on(self) -> bool | None:
        status = (self._realm or {}).get("status")
        return None if status is None else status == "UP"


class WowRealmQueue(_RealmEntity):
    _attr_translation_key = "realm_queue"

    def __init__(self, coordinator: WowWorldCoordinator, slug: str) -> None:
        super().__init__(coordinator, slug, "queue")

    @property
    def is_on(self) -> bool | None:
        realm = self._realm
        return None if realm is None else realm.get("queue")
