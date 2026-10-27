"""Ereignisse je Charakter: Boss besiegt, neuer Erfolg, neu gesammelt, Level."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import parsers as p
from .coordinator import WowConfigEntry, WowCoordinator, WowDetailCoordinator
from .entity import WowCharacterEntity
from .sensor import detail_available

# Nur Coordinator-Entitaeten ohne eigene Abfragen: keine Begrenzung noetig.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    for subentry_id, detail in runtime.details.items():
        entities: list[EventEntity] = [
            WowEvent(detail, key, event_type, endpoint, fn)
            for key, event_type, endpoint, fn in (
                ("boss_killed", "boss_killed", "raids", p.boss_kills),
                (
                    "new_achievement",
                    "achievement",
                    "achievements",
                    p.recent_achievements,
                ),
            )
            if detail_available(detail, key)
        ]
        if detail_available(detail, "new_collectible"):
            entities.append(WowCollectibleEvent(detail))
        entities.append(WowLevelEvent(runtime.coordinators[subentry_id]))
        async_add_entities(entities, config_subentry_id=subentry_id)


class WowEvent(WowCharacterEntity, EventEntity):
    """Loest fuer jeden Eintrag aus, der neuer ist als der zuletzt gesehene.

    Beim Start wird nur der neueste Zeitpunkt gemerkt, damit alte Kills und
    Erfolge nach einem Neustart nicht erneut ausloesen.
    """

    def __init__(
        self,
        coordinator: WowDetailCoordinator,
        key: str,
        event_type: str,
        endpoint: str,
        items_fn: Callable[[dict[str, Any] | None], list[dict[str, Any]]],
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._attr_event_types = [event_type]
        self._event_type = event_type
        self._endpoint = endpoint
        self._items_fn = items_fn
        self._last: int | None = None

    def _items(self) -> list[dict[str, Any]] | None:
        data = self.coordinator.data or {}
        if self._endpoint not in data:
            return None
        return self._items_fn(data[self._endpoint])

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        items = self._items()
        if items is not None:
            self._last = max((i["timestamp"] for i in items), default=0)

    @callback
    def _handle_coordinator_update(self) -> None:
        items = self._items()
        if items is not None:
            if self._last is None:
                self._last = max((i["timestamp"] for i in items), default=0)
            else:
                for item in items:
                    if item["timestamp"] > self._last:
                        self._trigger_event(
                            self._event_type,
                            {
                                **item,
                                "timestamp": p.timestamp(item["timestamp"]).isoformat(),
                                **self._extra(item),
                            },
                        )
                        # Je Ereignis schreiben, sonst bliebe bei mehreren
                        # neuen Eintraegen in einer Abfrage nur der letzte.
                        self.async_write_ha_state()
                        self._last = item["timestamp"]
        super()._handle_coordinator_update()

    def _extra(self, item: dict[str, Any]) -> dict[str, Any]:
        """Symbol des Erfolgs, falls nachgeschlagen."""
        if self._endpoint != "achievements":
            return {}
        media = (self.coordinator.data or {}).get("media_urls") or {}
        return {"icon": media.get(f"achievement/{item.get('id')}")}


# Endpunkt der Sammlung -> event_type
COLLECTIBLE_TYPES = {"mounts": "mount", "pets": "pet", "toys": "toy", "titles": "title"}


class WowCollectibleEvent(WowCharacterEntity, EventEntity):
    """Neues Reittier, Haustier, Spielzeug oder neuer Titel.

    Vergleicht die Sammlungen zwischen zwei Abfragen (alle 6 Stunden). Was beim
    Start schon da ist, loest nicht aus. Reittiere und Spielzeuge gelten fuer
    den ganzen Account; mehrere Charaktere melden sie daher je einmal.
    """

    _attr_translation_key = "new_collectible"

    def __init__(self, coordinator: WowDetailCoordinator) -> None:
        super().__init__(coordinator, "new_collectible")
        self._attr_event_types = list(COLLECTIBLE_TYPES.values())
        self._known: dict[str, set[int]] = {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._compare()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._compare()
        super()._handle_coordinator_update()

    def _compare(self) -> None:
        data = self.coordinator.data or {}
        for endpoint, event_type in COLLECTIBLE_TYPES.items():
            if data.get(endpoint) is None:
                continue
            current = p.collectibles(endpoint, data[endpoint])
            known = self._known.get(endpoint)
            # Beim ersten Stand (Start) nur merken, nichts ausloesen.
            if known is not None:
                for uid in sorted(current.keys() - known):
                    self._trigger_event(event_type, current[uid])
                    self.async_write_ha_state()
            self._known[endpoint] = set(current)


class WowLevelEvent(WowCharacterEntity, EventEntity):
    """Level gestiegen; prueft bei jeder Profilabfrage (15 Minuten)."""

    _attr_translation_key = "level_up"

    def __init__(self, coordinator: WowCoordinator) -> None:
        super().__init__(coordinator, "level_up")
        self._attr_event_types = ["level_up"]
        self._level: int | None = None

    def _current(self) -> int | None:
        level = ((self.coordinator.data or {}).get("profile") or {}).get("level")
        return level if isinstance(level, int) else None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._level = self._current()

    @callback
    def _handle_coordinator_update(self) -> None:
        level = self._current()
        if level is not None:
            if self._level is not None and level > self._level:
                self._trigger_event(
                    "level_up", {"level": level, "previous": self._level}
                )
            self._level = level
        super()._handle_coordinator_update()
