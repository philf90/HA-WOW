"""Ereignisse je Charakter: Boss besiegt, neuer Erfolg."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import parsers as p
from .coordinator import WowConfigEntry, WowDetailCoordinator
from .entity import WowCharacterEntity
from .sensor import detail_available

# Nur Coordinator-Entitaeten ohne eigene Abfragen: keine Begrenzung noetig.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry_id, detail in entry.runtime_data.details.items():
        entities = [
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
                            },
                        )
                        self._last = item["timestamp"]
        super()._handle_coordinator_update()
