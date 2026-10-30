"""Ereignisse je Charakter: Boss besiegt, neuer Erfolg, neu gesammelt, Level."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from . import parsers as p
from .coordinator import WowConfigEntry, WowCoordinator, WowDetailCoordinator
from .entity import EntityAdder, WowCharacterEntity
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
        coordinator = runtime.coordinators[subentry_id]
        adder = EntityAdder(
            partial(async_add_entities, config_subentry_id=subentry_id),
            detail.key_allowed,
        )

        @callback
        def update(
            detail: WowDetailCoordinator = detail,
            coordinator: WowCoordinator = coordinator,
            adder: EntityAdder = adder,
        ) -> None:
            adder.add(_events(detail, coordinator))

        update()
        # Z. B. erste Erfolge in Classic: Ereignis ohne Neuladen anlegen.
        entry.async_on_unload(detail.async_add_listener(update))


# Stand der Ereignisse ueber Neustart und Neuladen (seit 0.23.0): Was in der
# Zwischenzeit dazukam, loest danach aus, wenn der gespeicherte Stand hoechstens
# so alt ist; Bosskills und Erfolge zudem nur, wenn sie selbst hoechstens so alt
# sind. Sonst gilt wie vor 0.23.0 der Stand beim Start als bekannt. Eine
# Meldung, die mehr als einen Tag zu spaet kommt, hilft selten, und nach
# laengerer Pause kaeme sonst eine Flut.
CATCH_UP_MAX_AGE = timedelta(hours=24)
# Eigener Stand in den gespeicherten Daten der Ereignis-Entitaet, neben
# last_event_type und last_event_attributes von Home Assistant.
_STORE_KEY = "wow_character"


@dataclass
class _StoredEventData(ExtraStoredData):
    """Daten von EventEntity und eigener Stand unter _STORE_KEY."""

    base: ExtraStoredData
    seen: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {**self.base.as_dict(), _STORE_KEY: self.seen}


class _CatchUpEvent(WowCharacterEntity, EventEntity):
    """Ereignis, das seinen Stand speichert und Verpasstes nachholt.

    Verglichen wird erst, wenn Home Assistant gestartet ist: Vorher sind
    Automationen, die auf das Ereignis warten, womoeglich noch nicht bereit.
    """

    def __init__(self, coordinator: Any, key: str) -> None:
        super().__init__(coordinator, key)
        self._ready = False
        # True bis zum ersten Vergleich nach einem wiederhergestellten Stand
        self._catch_up = False

    def _seen(self) -> dict[str, Any] | None:
        """Stand zum Speichern; None, solange keiner bekannt ist."""
        raise NotImplementedError

    def _restore(self, seen: dict[str, Any]) -> None:
        raise NotImplementedError

    def _compare(self) -> None:
        """Neues ausloesen; ohne Stand nur den aktuellen merken."""
        raise NotImplementedError

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        base = super().extra_restore_state_data
        if (seen := self._seen()) is None:
            return base
        return _StoredEventData(base, {**seen, "saved": dt_util.utcnow().isoformat()})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        extra = await self.async_get_last_extra_data()
        seen = extra.as_dict().get(_STORE_KEY) if extra else None
        if not isinstance(seen, dict):
            seen = None
        saved = dt_util.parse_datetime(str(seen.get("saved"))) if seen else None
        if saved is not None and dt_util.utcnow() - saved <= CATCH_UP_MAX_AGE:
            try:
                self._restore(seen)
            except (AttributeError, KeyError, TypeError, ValueError):
                # Unbrauchbarer Stand: wie ohne gespeicherten Stand
                pass
            else:
                self._catch_up = True
        self.async_on_remove(async_at_started(self.hass, self._started))

    @callback
    def _started(self, hass: HomeAssistant) -> None:
        self._ready = True
        self._compare()

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._ready:
            self._compare()
        super()._handle_coordinator_update()


# Schluessel, event_type, Endpunkt, Auswertung
EVENTS = (
    ("boss_killed", "boss_killed", "raids", p.boss_kills),
    ("new_achievement", "achievement", "achievements", p.recent_achievements),
)


def _events(
    detail: WowDetailCoordinator, coordinator: WowCoordinator
) -> Iterator[tuple[str, Callable[[], EventEntity]]]:
    for key, event_type, endpoint, fn in EVENTS:
        if detail_available(detail, key):
            yield key, partial(WowEvent, detail, key, event_type, endpoint, fn)
    if detail_available(detail, "new_collectible"):
        yield "new_collectible", partial(WowCollectibleEvent, detail)
    yield "level_up", partial(WowLevelEvent, coordinator)


class WowEvent(_CatchUpEvent):
    """Loest fuer jeden Eintrag aus, der neuer ist als der zuletzt gesehene.

    Ohne gespeicherten Stand wird beim Start nur der neueste Zeitpunkt
    gemerkt, damit alte Kills und Erfolge nicht erneut ausloesen.
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

    def _seen(self) -> dict[str, Any] | None:
        return None if self._last is None else {"last": self._last}

    def _restore(self, seen: dict[str, Any]) -> None:
        self._last = int(seen["last"])

    def _compare(self) -> None:
        items = self._items()
        if items is None:
            return
        if self._last is None:
            self._last = max((i["timestamp"] for i in items), default=0)
            return
        # Nach einem Neustart nur Eintraege der letzten CATCH_UP_MAX_AGE
        oldest = 0
        if self._catch_up:
            oldest = (dt_util.utcnow() - CATCH_UP_MAX_AGE).timestamp() * 1000
            self._catch_up = False
        for item in items:
            if item["timestamp"] <= self._last:
                continue
            if item["timestamp"] >= oldest:
                self._trigger_event(
                    self._event_type,
                    {
                        **item,
                        "timestamp": p.timestamp(item["timestamp"]).isoformat(),
                        **self._extra(item),
                    },
                )
                # Je Ereignis schreiben, sonst bliebe bei mehreren neuen
                # Eintraegen in einer Abfrage nur der letzte.
                self.async_write_ha_state()
            self._last = item["timestamp"]

    def _extra(self, item: dict[str, Any]) -> dict[str, Any]:
        """Symbol des Erfolgs, falls nachgeschlagen."""
        if self._endpoint != "achievements":
            return {}
        media = (self.coordinator.data or {}).get("media_urls") or {}
        return {"icon": media.get(f"achievement/{item.get('id')}")}


# Endpunkt der Sammlung -> event_type
COLLECTIBLE_TYPES = {"mounts": "mount", "pets": "pet", "toys": "toy", "titles": "title"}


class WowCollectibleEvent(_CatchUpEvent):
    """Neues Reittier, Haustier, Spielzeug oder neuer Titel.

    Vergleicht die Sammlungen zwischen zwei Abfragen (alle 6 Stunden). Was beim
    Start schon da ist, loest nur aus, wenn es im gespeicherten Stand fehlt.
    Reittiere und Spielzeuge gelten fuer den ganzen Account; mehrere
    Charaktere melden sie daher je einmal.
    """

    _attr_translation_key = "new_collectible"

    def __init__(self, coordinator: WowDetailCoordinator) -> None:
        super().__init__(coordinator, "new_collectible")
        self._attr_event_types = list(COLLECTIBLE_TYPES.values())
        self._known: dict[str, set[int]] = {}

    def _seen(self) -> dict[str, Any] | None:
        if not self._known:
            return None
        return {"known": {e: sorted(ids) for e, ids in self._known.items()}}

    def _restore(self, seen: dict[str, Any]) -> None:
        # Erst vollstaendig lesen: Ein Fehler laesst keinen halben Stand zurueck.
        self._known = {
            endpoint: {int(i) for i in ids}
            for endpoint, ids in seen["known"].items()
            if endpoint in COLLECTIBLE_TYPES
        }

    def _compare(self) -> None:
        self._catch_up = False
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


class WowLevelEvent(_CatchUpEvent):
    """Level gestiegen; prueft bei jeder Profilabfrage (15 Minuten)."""

    _attr_translation_key = "level_up"

    def __init__(self, coordinator: WowCoordinator) -> None:
        super().__init__(coordinator, "level_up")
        self._attr_event_types = ["level_up"]
        self._level: int | None = None

    def _current(self) -> int | None:
        level = ((self.coordinator.data or {}).get("profile") or {}).get("level")
        return level if isinstance(level, int) else None

    def _seen(self) -> dict[str, Any] | None:
        return None if self._level is None else {"level": self._level}

    def _restore(self, seen: dict[str, Any]) -> None:
        self._level = int(seen["level"])

    def _compare(self) -> None:
        self._catch_up = False
        level = self._current()
        if level is not None:
            if self._level is not None and level > self._level:
                self._trigger_event(
                    "level_up", {"level": level, "previous": self._level}
                )
                self.async_write_ha_state()
            self._level = level
