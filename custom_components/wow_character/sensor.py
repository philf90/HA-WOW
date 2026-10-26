"""Sensoren je Charakter (Profil und Details) und je Spielwelt."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import parsers as p
from .const import EQUIPMENT_SLOTS
from .coordinator import (
    EQUIPMENT_PREFIX,
    PROFESSION_PREFIX,
    WowConfigEntry,
    WowCoordinator,
    WowDetailCoordinator,
    WowWorldCoordinator,
    endpoint_for_key,
)
from .entity import WowCharacterEntity, WowWorldEntity

# Profil-Sensoren (15-Minuten-Takt)


def _mythic(data: dict[str, Any]) -> dict[str, Any]:
    return (data["mythic"] or {}).get("current_mythic_rating") or {}


def _in_current_season(data: dict[str, Any]) -> bool:
    """False, wenn die aktuelle Season bekannt ist und der Charakter sie nicht spielte."""
    season = data.get("season_id")
    if season is None:
        return True
    seasons = (data["mythic"] or {}).get("seasons") or []
    return any(isinstance(s, dict) and s.get("id") == season for s in seasons)


def _mythic_rating(data: dict[str, Any]) -> float | None:
    if not _in_current_season(data):
        return None
    rating = _mythic(data).get("rating")
    return round(rating, 1) if rating is not None else None


def _mythic_attrs(data: dict[str, Any]) -> dict[str, Any]:
    current = _in_current_season(data)
    rating = _mythic(data).get("rating")
    return {
        "season": data.get("season_id"),
        "color": p.color_hex(_mythic(data).get("color")) if current else None,
        # Wert der API ohne Season-Pruefung; so zeigt ihn das Arsenal.
        "api_rating": round(rating, 1) if rating is not None else None,
    }


def _level_attrs(data: dict[str, Any]) -> dict[str, Any]:
    # Klasse, Spezialisierung usw. nur am Level-Sensor, damit sie nicht
    # in jedem Sensor doppelt in der Datenbank landen.
    prof = data["profile"]
    return {
        "class": p.name_of(prof.get("character_class")),
        "spec": p.name_of(prof.get("active_spec")),
        "race": p.name_of(prof.get("race")),
        "faction": p.name_of(prof.get("faction")),
        "guild": p.name_of(prof.get("guild")),
        "realm": p.name_of(prof.get("realm")),
        "title": p.active_title(prof),
    }


@dataclass(frozen=True, kw_only=True)
class WowSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    mythic_plus_only: bool = False


PROFILE_SENSORS: tuple[WowSensorDescription, ...] = (
    WowSensorDescription(
        key="level",
        translation_key="level",
        icon="mdi:star-circle",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("level"),
        attrs_fn=_level_attrs,
    ),
    WowSensorDescription(
        key="item_level",
        translation_key="item_level",
        icon="mdi:shield-sword",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("equipped_item_level"),
    ),
    WowSensorDescription(
        key="item_level_average",
        translation_key="item_level_average",
        icon="mdi:shield-sword-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("average_item_level"),
    ),
    WowSensorDescription(
        key="experience",
        translation_key="experience",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("experience"),
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
        value_fn=lambda d: p.timestamp(d["profile"].get("last_login_timestamp")),
    ),
    WowSensorDescription(
        key="mythic_rating",
        translation_key="mythic_rating",
        icon="mdi:key-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_mythic_rating,
        attrs_fn=_mythic_attrs,
        mythic_plus_only=True,
    ),
)

# Detail-Sensoren (stuendlich bzw. alle 6 Stunden)


def _raid_sensor(key: str) -> WowSensorDescription:
    difficulty = p.RAID_DIFFICULTIES[key]
    return WowSensorDescription(
        key=key,
        translation_key=key,
        icon="mdi:sword-cross",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.raid_progress(d.get("raids"), difficulty)[0],
        attrs_fn=lambda d: p.raid_progress(d.get("raids"), difficulty)[1],
    )


def _stat_sensor(key: str, unit: str | None = None) -> WowSensorDescription:
    attrs = None
    if key == "stat_primary":
        attrs = lambda d: {"stat": p.primary_stat(d.get("statistics") or {})[1]}
    return WowSensorDescription(
        key=key,
        translation_key=key,
        icon="mdi:chart-bar",
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.MEASUREMENT,
        # Selten gebraucht: angelegt, aber standardmaessig deaktiviert.
        entity_registry_enabled_default=False,
        value_fn=lambda d: p.stat(d.get("statistics"), key),
        attrs_fn=attrs,
    )


def _items(d: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Angelegte Items; None, solange die Ausruestung nicht abgefragt ist."""
    equipment = d.get("equipment")
    return p.equipment(equipment) if equipment is not None else None


def _count(items: list[Any] | None) -> int | None:
    return len(items) if items is not None else None


def _set_value(d: dict[str, Any]) -> int | None:
    if (items := _items(d)) is None:
        return None
    sets = p.item_sets(items)
    return sets[0]["equipped"] if sets else 0


def _set_attrs(d: dict[str, Any]) -> dict[str, Any]:
    sets = p.item_sets(_items(d) or {})
    main = sets[0] if sets else {}
    return {
        "name": main.get("name"),
        "total": main.get("total"),
        "items": main.get("items", []),
        "effects": main.get("effects", []),
        # Weitere Sets, falls Teile mehrerer Sets angelegt sind.
        "other_sets": [
            {"name": s["name"], "equipped": s["equipped"], "total": s["total"]}
            for s in sets[1:]
        ],
    }


def _achievements_value(d: dict[str, Any]) -> int | None:
    return (d.get("achievements") or {}).get("total_quantity")


def _titles_attrs(d: dict[str, Any]) -> dict[str, Any]:
    data = d.get("titles") or {}
    active = data.get("active_title")
    return {
        "active": p.name_of(active) if isinstance(active, dict) else None,
        "titles": p.titles(data),
    }


DETAIL_SENSORS: tuple[WowSensorDescription, ...] = (
    *(_raid_sensor(k) for k in p.RAID_DIFFICULTIES),
    WowSensorDescription(
        key="mythic_best_key",
        translation_key="mythic_best_key",
        icon="mdi:key-chain-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.mythic_season(d.get("mythic_season"))["best_key"],
        attrs_fn=lambda d: {
            key: p.mythic_season(d.get("mythic_season"))[key]
            for key in ("best_runs", "runs")
        },
        mythic_plus_only=True,
    ),
    WowSensorDescription(
        key="mythic_runs_timed",
        translation_key="mythic_runs_timed",
        icon="mdi:timer-check-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.mythic_season(d.get("mythic_season"))["runs_timed"],
        mythic_plus_only=True,
    ),
    WowSensorDescription(
        key="honor_level",
        translation_key="honor_level",
        icon="mdi:medal",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("pvp") or {}).get("honor_level"),
    ),
    WowSensorDescription(
        key="honorable_kills",
        translation_key="honorable_kills",
        icon="mdi:sword",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: (d.get("pvp") or {}).get("honorable_kills"),
    ),
    _stat_sensor("stat_health"),
    _stat_sensor("stat_primary"),
    _stat_sensor("stat_crit", PERCENTAGE),
    _stat_sensor("stat_haste", PERCENTAGE),
    _stat_sensor("stat_mastery", PERCENTAGE),
    _stat_sensor("stat_versatility", PERCENTAGE),
    WowSensorDescription(
        key="mounts",
        translation_key="mounts",
        icon="mdi:horse",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.collection_count(d.get("mounts"), "mounts"),
    ),
    WowSensorDescription(
        key="pets",
        translation_key="pets",
        icon="mdi:paw",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.collection_count(d.get("pets"), "pets"),
    ),
    WowSensorDescription(
        key="toys",
        translation_key="toys",
        icon="mdi:teddy-bear",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.collection_count(d.get("toys"), "toys"),
    ),
    WowSensorDescription(
        key="empty_sockets",
        translation_key="empty_sockets",
        icon="mdi:diamond-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(
            p.empty_sockets(items) if (items := _items(d)) is not None else None
        ),
        attrs_fn=lambda d: {"sockets": p.empty_sockets(_items(d) or {})},
    ),
    WowSensorDescription(
        key="enchantments",
        translation_key="enchantments",
        icon="mdi:auto-fix",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(
            p.enchanted_slots(items) if (items := _items(d)) is not None else None
        ),
        attrs_fn=lambda d: {"slots": p.enchanted_slots(_items(d) or {})},
    ),
    WowSensorDescription(
        key="item_set",
        translation_key="item_set",
        icon="mdi:tshirt-crew-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_set_value,
        attrs_fn=_set_attrs,
    ),
    WowSensorDescription(
        key="achievements",
        translation_key="achievements",
        icon="mdi:trophy-variant",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_achievements_value,
        attrs_fn=lambda d: {
            "total_points": (d.get("achievements") or {}).get("total_points"),
            "categories": p.achievement_categories(d.get("achievements")),
        },
    ),
    WowSensorDescription(
        key="specialization",
        translation_key="specialization",
        icon="mdi:account-star",
        value_fn=lambda d: p.specialization(d.get("specializations"))["name"],
        attrs_fn=lambda d: {
            k: v
            for k, v in p.specialization(d.get("specializations")).items()
            if k != "name"
        },
    ),
    WowSensorDescription(
        key="titles",
        translation_key="titles",
        icon="mdi:card-account-details-star",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(
            p.titles(d["titles"]) if d.get("titles") is not None else None
        ),
        attrs_fn=_titles_attrs,
    ),
    WowSensorDescription(
        key="game_statistics",
        translation_key="game_statistics",
        icon="mdi:counter",
        # Grosse Antwort mit mehreren hundert Werten: angelegt, aber aus.
        entity_registry_enabled_default=False,
        value_fn=lambda d: _count(
            p.game_statistics(d["game_statistics"])
            if d.get("game_statistics") is not None
            else None
        ),
        attrs_fn=lambda d: {"statistics": p.game_statistics(d.get("game_statistics"))},
    ),
)


def detail_available(coordinator: WowDetailCoordinator, key: str) -> bool:
    """Fuer Forever nur Entitaeten anlegen, deren Endpunkt Daten liefert."""
    if not coordinator.is_forever:
        return True
    data = coordinator.data or {}
    endpoint = endpoint_for_key(key)
    return endpoint not in data or data[endpoint] is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    for subentry_id, coordinator in runtime.coordinators.items():
        detail = runtime.details[subentry_id]
        entities: list[SensorEntity] = [
            WowSensor(coordinator, d)
            for d in PROFILE_SENSORS
            if coordinator.mythic_plus or not d.mythic_plus_only
        ]
        entities += [
            WowSensor(detail, d)
            for d in DETAIL_SENSORS
            if (detail.mythic_plus or not d.mythic_plus_only)
            and detail_available(detail, d.key)
        ]
        # Berufe: je Beruf ein Sensor, angelegt aus der ersten Antwort.
        for prof_id in _professions(detail):
            entities.append(WowProfessionSensor(detail, prof_id))
        # Ausruestung: alle Plaetze, auch leere, damit Karten feste IDs haben.
        if detail_available(detail, f"{EQUIPMENT_PREFIX}head"):
            entities += [WowEquipmentSensor(detail, slot) for slot in EQUIPMENT_SLOTS]
        if detail_available(detail, "reputation"):
            entities.append(WowReputationSensor(detail))
        async_add_entities(entities, config_subentry_id=subentry_id)

    for world in runtime.worlds.values():
        async_add_entities(_world_sensors(world))


def _world_sensors(world: WowWorldCoordinator) -> list[SensorEntity]:
    data = world.data or {}
    # Retail kennt WoW-Marke und Reset sicher; Forever nur, wenn die API antwortet.
    known = not world.suffix
    entities: list[SensorEntity] = []
    if known or data.get("token") is not None:
        entities.append(WowTokenSensor(world))
    if world.mythic_plus:
        entities.append(WowResetSensor(world))
    for slug, realm in (data.get("realms") or {}).items():
        if known or realm is not None:
            entities.append(WowRealmPopulationSensor(world, slug))
    return entities


class WowSensor(WowCharacterEntity, SensorEntity):
    """Sensor aus dem Profil- oder Detail-Coordinator eines Charakters."""

    entity_description: WowSensorDescription
    # Lange Listen fuer Karten (M+-Laeufe, Titel, Statistik-Fenster); nur
    # die Sensoren mit diesen Attributen sind betroffen.
    _unrecorded_attributes = frozenset({"runs", "titles", "statistics"})

    def __init__(
        self,
        coordinator: WowCoordinator | WowDetailCoordinator,
        description: WowSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs_fn = self.entity_description.attrs_fn
        if attrs_fn is None or self.coordinator.data is None:
            return None
        return attrs_fn(self.coordinator.data)


def _professions(detail: WowDetailCoordinator) -> dict[int, dict[str, Any]]:
    data = detail.data or {}
    return p.professions(
        data.get("professions"), data.get("profession_names"), data.get("tier_names")
    )


class WowProfessionSensor(WowCharacterEntity, SensorEntity):
    """Skill eines Berufs in der neuesten Erweiterungsstufe."""

    _attr_translation_key = "profession"
    _attr_icon = "mdi:hammer-wrench"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: WowDetailCoordinator, prof_id: int) -> None:
        super().__init__(coordinator, f"{PROFESSION_PREFIX}{prof_id}")
        self._prof_id = prof_id
        info = _professions(coordinator)[prof_id]
        self._attr_translation_placeholders = {"profession": info["name"] or "?"}

    def _info(self) -> dict[str, Any]:
        return _professions(self.coordinator).get(self._prof_id, {})

    @property
    def native_value(self) -> int | None:
        return self._info().get("skill")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self._info()
        return {"tier": info.get("tier"), "max_skill": info.get("max_skill")}


class WowEquipmentSensor(WowCharacterEntity, SensorEntity):
    """Item auf einem Ausruestungsplatz: Itemlevel, Symbol als Bild."""

    _attr_icon = "mdi:shield-outline"
    # Tooltip-Zeilen fuer Karten; aendern sich nur mit dem Item und bleiben
    # aus der Datenbank (18 Plaetze je Charakter).
    _unrecorded_attributes = frozenset({"tooltip"})

    def __init__(self, coordinator: WowDetailCoordinator, slot: str) -> None:
        key = f"{EQUIPMENT_PREFIX}{slot.lower()}"
        super().__init__(coordinator, key)
        self._slot = slot
        self._attr_translation_key = key

    def _item(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return p.equipment(data.get("equipment")).get(self._slot, {})

    @property
    def native_value(self) -> int | None:
        return self._item().get("level")

    @property
    def entity_picture(self) -> str | None:
        icons = (self.coordinator.data or {}).get("item_icons") or {}
        return icons.get(self._item().get("media_id"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._item()
        return {
            key: item.get(key)
            for key in (
                "name",
                "item_id",
                "quality",
                "quality_name",
                "enchantments",
                "sockets",
                "set",
                "tooltip",
            )
        }


class WowReputationSensor(WowCharacterEntity, SensorEntity):
    """Anzahl der Fraktionen; Stufe und Fortschritt je Fraktion als Attribut."""

    _attr_translation_key = "reputation"
    _attr_icon = "mdi:handshake"
    # Die Liste kann ueber 100 Fraktionen lang sein; nicht in die Datenbank.
    _unrecorded_attributes = frozenset({"factions"})

    def __init__(self, coordinator: WowDetailCoordinator) -> None:
        super().__init__(coordinator, "reputation")

    def _factions(self) -> list[dict[str, Any]] | None:
        data = (self.coordinator.data or {}).get("reputations")
        return p.reputations(data) if data is not None else None

    @property
    def native_value(self) -> int | None:
        factions = self._factions()
        return len(factions) if factions is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"factions": self._factions() or []}


class WowTokenSensor(WowWorldEntity, SensorEntity):
    _attr_translation_key = "token"
    _attr_icon = "mdi:cash"
    _attr_native_unit_of_measurement = "Gold"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: WowWorldCoordinator) -> None:
        super().__init__(coordinator, "token")

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("token")


class WowResetSensor(WowWorldEntity, SensorEntity):
    _attr_translation_key = "weekly_reset"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: WowWorldCoordinator) -> None:
        super().__init__(coordinator, "weekly_reset")

    @property
    def native_value(self) -> datetime | None:
        return (self.coordinator.data or {}).get("reset")


class WowRealmPopulationSensor(WowWorldEntity, SensorEntity):
    _attr_translation_key = "realm_population"
    _attr_icon = "mdi:account-group"

    def __init__(self, coordinator: WowWorldCoordinator, slug: str) -> None:
        super().__init__(coordinator, f"realm-{slug}-population")
        self._slug = slug
        realm = (coordinator.data or {}).get("realms", {}).get(slug) or {}
        self._attr_translation_placeholders = {"realm": realm.get("name") or slug}

    @property
    def native_value(self) -> str | None:
        realm = (self.coordinator.data or {}).get("realms", {}).get(self._slug)
        return (realm or {}).get("population")
