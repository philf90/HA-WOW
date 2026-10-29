"""Bilder je Charakter: Avatar und Ganzkoerperbild von Blizzard."""

from __future__ import annotations

from functools import partial

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import parsers as p
from .coordinator import WowConfigEntry, WowDetailCoordinator
from .entity import EntityAdder, WowCharacterEntity
from .sensor import detail_available

# Nur Coordinator-Entitaeten ohne eigene Abfragen: keine Begrenzung noetig.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry_id, detail in entry.runtime_data.details.items():
        adder = EntityAdder(partial(async_add_entities, config_subentry_id=subentry_id))

        @callback
        def update(
            detail: WowDetailCoordinator = detail, adder: EntityAdder = adder
        ) -> None:
            adder.add(
                (key, partial(WowImage, hass, detail, key))
                for key in ("avatar", "full_body")
                if detail_available(detail, key)
            )

        update()
        # Bilder, die erst spaeter kommen, ohne Neuladen anlegen.
        entry.async_on_unload(detail.async_add_listener(update))


class WowImage(WowCharacterEntity, ImageEntity):
    def __init__(
        self, hass: HomeAssistant, coordinator: WowDetailCoordinator, key: str
    ) -> None:
        WowCharacterEntity.__init__(self, coordinator, key)
        ImageEntity.__init__(self, hass)
        self._key = key
        self._attr_translation_key = key
        self._attr_image_url = self._url()
        self._attr_image_last_updated = dt_util.utcnow()

    def _url(self) -> str | None:
        return p.media_url((self.coordinator.data or {}).get("media"), self._key)

    @callback
    def _handle_coordinator_update(self) -> None:
        # Bild nur neu laden, wenn sich die Adresse aendert.
        url = self._url()
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()
