"""Serverstatus und Warteschlange je Realm am Spielwelt-Geraet."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import partial

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WowConfigEntry, WowWorldCoordinator
from .entity import EntityAdder, WowWorldEntity
from .sensor import realm_slugs

# Nur Coordinator-Entitaeten ohne eigene Abfragen: keine Begrenzung noetig.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for world in entry.runtime_data.worlds.values():
        adder = EntityAdder(async_add_entities)

        @callback
        def update(world: WowWorldCoordinator = world, adder: EntityAdder = adder):
            adder.add(_realm_entities(world))

        update()
        # Forever und Classic: Realms, die erst spaeter antworten, ohne Neuladen.
        entry.async_on_unload(world.async_add_listener(update))


def _realm_entities(
    world: WowWorldCoordinator,
) -> Iterator[tuple[str, Callable[[], BinarySensorEntity]]]:
    for slug in realm_slugs(world):
        yield f"realm-{slug}-status", partial(WowRealmStatus, world, slug)
        yield f"realm-{slug}-queue", partial(WowRealmQueue, world, slug)


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
