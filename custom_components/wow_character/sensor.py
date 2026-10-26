"""Sensoren fuer Level, Itemlevel, Erfolgspunkte, Mythic+-Wertung und letzten Login."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WowConfigEntry, WowCoordinator


def _name(obj: dict[str, Any] | None) -> str | None:
    return (obj or {}).get("name")


def _last_login(data: dict[str, Any]) -> datetime | None:
    # Die API liefert Millisekunden seit 1970.
    ts = data["profile"].get("last_login_timestamp")
    return datetime.fromtimestamp(ts / 1000, tz=UTC) if ts else None


def _mythic_rating(data: dict[str, Any]) -> float | None:
    rating = ((data["mythic"] or {}).get("current_mythic_rating") or {}).get("rating")
    return round(rating, 1) if rating is not None else None


@dataclass(frozen=True, kw_only=True)
class WowSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    mythic_plus_only: bool = False


SENSORS: tuple[WowSensorDescription, ...] = (
    WowSensorDescription(
        key="level",
        translation_key="level",
        icon="mdi:star-circle",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("level"),
    ),
    WowSensorDescription(
        key="item_level",
        translation_key="item_level",
        icon="mdi:shield-sword",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("equipped_item_level"),
    ),
    WowSensorDescription(
        key="achievement_points",
        translation_key="achievement_points",
        icon="mdi:trophy",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("achievement_points"),
    ),
    WowSensorDescription(
        key="last_login",
        translation_key="last_login",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_login,
    ),
    WowSensorDescription(
        key="mythic_rating",
        translation_key="mythic_rating",
        icon="mdi:key-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_mythic_rating,
        mythic_plus_only=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        WowSensor(coordinator, description)
        for description in SENSORS
        if coordinator.mythic_plus or not description.mythic_plus_only
    )


class WowSensor(CoordinatorEntity[WowCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: WowSensorDescription

    def __init__(
        self, coordinator: WowCoordinator, description: WowSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="Blizzard Entertainment",
            model=f"World of Warcraft ({coordinator.game_version})",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        # Klasse, Spezialisierung usw. nur am Level-Sensor, damit sie nicht
        # in jedem Sensor doppelt in der Datenbank landen.
        if self.entity_description.key != "level":
            return None
        p = self.coordinator.data["profile"]
        return {
            "class": _name(p.get("character_class")),
            "spec": _name(p.get("active_spec")),
            "race": _name(p.get("race")),
            "faction": _name(p.get("faction")),
            "guild": _name(p.get("guild")),
            "realm": _name(p.get("realm")),
        }
