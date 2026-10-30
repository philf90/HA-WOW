"""Sensoren je Charakter (Profil und Details) und je Spielwelt."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import parsers as p
from .const import EQUIPMENT_SLOTS, PVP_BRACKETS, REALM_POPULATIONS
from .coordinator import (
    EQUIPMENT_PREFIX,
    PROFESSION_PREFIX,
    PVP_BRACKET_PREFIX,
    WowConfigEntry,
    WowCoordinator,
    WowDetailCoordinator,
    WowWorldCoordinator,
    endpoint_for_key,
)
from .entity import EntityAdder, WowCharacterEntity, WowWorldEntity

# Nur Coordinator-Entitaeten ohne eigene Abfragen: keine Begrenzung noetig.
PARALLEL_UPDATES = 0

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


def _talents_attrs(data: dict[str, Any]) -> dict[str, Any]:
    talents = p.talents(data.get("specializations")) or {}
    return {
        "total_points": talents.get("total_points"),
        "trees": talents.get("trees") or [],
    }


def _level_attrs(data: dict[str, Any]) -> dict[str, Any]:
    # Klasse, Spezialisierung usw. nur am Level-Sensor, damit sie nicht
    # in jedem Sensor doppelt in der Datenbank landen.
    prof = data["profile"]
    media = data.get("media_urls") or {}
    return {
        "class": p.name_of(prof.get("character_class")),
        "spec": p.name_of(prof.get("active_spec")),
        "race": p.name_of(prof.get("race")),
        "faction": p.name_of(prof.get("faction")),
        "guild": p.name_of(prof.get("guild")),
        "realm": p.name_of(prof.get("realm")),
        "title": p.active_title(prof),
        # Symbole aus den statischen Spieldaten, fuer Karten
        "class_icon": media.get(
            f"playable-class/{(prof.get('character_class') or {}).get('id')}"
        ),
        "spec_icon": media.get(
            f"playable-specialization/{(prof.get('active_spec') or {}).get('id')}"
        ),
    }


@dataclass(frozen=True, kw_only=True)
class WowSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    mythic_plus_only: bool = False
    # Nur ausserhalb von Retail, wo die Antwort das Feld laut Typen nicht hat.
    non_retail_only: bool = False


PROFILE_SENSORS: tuple[WowSensorDescription, ...] = (
    WowSensorDescription(
        key="level",
        translation_key="level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("level"),
        attrs_fn=_level_attrs,
    ),
    WowSensorDescription(
        key="item_level",
        translation_key="item_level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("equipped_item_level"),
    ),
    WowSensorDescription(
        key="item_level_average",
        translation_key="item_level_average",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("average_item_level"),
    ),
    WowSensorDescription(
        key="experience",
        translation_key="experience",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d["profile"].get("experience"),
    ),
    WowSensorDescription(
        key="achievement_points",
        translation_key="achievement_points",
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
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_mythic_rating,
        attrs_fn=_mythic_attrs,
        mythic_plus_only=True,
    ),
)

# Detail-Sensoren (stuendlich bzw. alle 6 Stunden)


def _raid_attrs(d: dict[str, Any], difficulty: str) -> dict[str, Any]:
    journal = d.get("raid_journal")
    attrs = p.raid_progress(d.get("raids"), difficulty, journal)[1]
    media = d.get("media_urls") or {}
    # Bild je Raid aus dem Dungeonkompendium, fuer Karten
    attrs["images"] = {
        name: media.get(f"journal-instance/{instance_id}")
        for name, instance_id in p.raid_instances(d.get("raids"), journal).items()
        if name in attrs.get("raids", {})
    }
    return attrs


def _raid_sensor(key: str) -> WowSensorDescription:
    difficulty = p.RAID_DIFFICULTIES[key]
    return WowSensorDescription(
        key=key,
        translation_key=key,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.raid_progress(
            d.get("raids"), difficulty, d.get("raid_journal")
        )[0],
        attrs_fn=lambda d: _raid_attrs(d, difficulty),
    )


def _stat_sensor(key: str, unit: str | None = None) -> WowSensorDescription:
    attrs = None
    if key == "stat_primary":
        attrs = lambda d: {"stat": p.primary_stat(d.get("statistics") or {})[1]}
    return WowSensorDescription(
        key=key,
        translation_key=key,
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
        key="dungeons",
        translation_key="dungeons",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.dungeon_progress(d.get("dungeons"), d.get("raid_journal"))[
            0
        ],
        attrs_fn=lambda d: p.dungeon_progress(d.get("dungeons"), d.get("raid_journal"))[
            1
        ],
    ),
    WowSensorDescription(
        key="mythic_best_key",
        translation_key="mythic_best_key",
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
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.mythic_season(d.get("mythic_season"))["runs_timed"],
        mythic_plus_only=True,
    ),
    WowSensorDescription(
        key="honor_level",
        translation_key="honor_level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("pvp") or {}).get("honor_level"),
    ),
    WowSensorDescription(
        key="honorable_kills",
        translation_key="honorable_kills",
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
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.collection_count(d.get("mounts"), "mounts"),
    ),
    WowSensorDescription(
        key="pets",
        translation_key="pets",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.collection_count(d.get("pets"), "pets"),
    ),
    WowSensorDescription(
        key="toys",
        translation_key="toys",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: p.collection_count(d.get("toys"), "toys"),
    ),
    WowSensorDescription(
        key="empty_sockets",
        translation_key="empty_sockets",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(
            p.empty_sockets(items) if (items := _items(d)) is not None else None
        ),
        attrs_fn=lambda d: {"sockets": p.empty_sockets(_items(d) or {})},
    ),
    WowSensorDescription(
        key="enchantments",
        translation_key="enchantments",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(
            p.enchanted_slots(items) if (items := _items(d)) is not None else None
        ),
        attrs_fn=lambda d: {"slots": p.enchanted_slots(_items(d) or {})},
    ),
    WowSensorDescription(
        key="item_set",
        translation_key="item_set",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_set_value,
        attrs_fn=_set_attrs,
    ),
    WowSensorDescription(
        key="achievements",
        translation_key="achievements",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_achievements_value,
        attrs_fn=lambda d: {
            "total_points": (d.get("achievements") or {}).get("total_points"),
            "categories": p.achievement_categories(
                d.get("achievements"), d.get("achievement_roots")
            ),
        },
    ),
    WowSensorDescription(
        key="specialization",
        translation_key="specialization",
        value_fn=lambda d: p.specialization(d.get("specializations"))["name"],
        attrs_fn=lambda d: {
            k: v
            for k, v in p.specialization(d.get("specializations")).items()
            if k != "name"
        },
    ),
    WowSensorDescription(
        key="talent_tree",
        translation_key="talent_tree",
        # Fuer die Karte "WoW Talentbaum"; Retail (talent-tree in den Spieldaten).
        value_fn=lambda d: (d.get("talent_tree") or {}).get("name"),
        attrs_fn=lambda d: {
            k: v for k, v in (d.get("talent_tree") or {}).items() if k != "name"
        },
    ),
    WowSensorDescription(
        key="talents",
        translation_key="talents",
        # Talentpunkte je Baum gibt es nur in Classic (specialization_groups).
        non_retail_only=True,
        value_fn=lambda d: (p.talents(d.get("specializations")) or {}).get("name"),
        attrs_fn=_talents_attrs,
    ),
    WowSensorDescription(
        key="titles",
        translation_key="titles",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(
            p.titles(d["titles"]) if d.get("titles") is not None else None
        ),
        attrs_fn=_titles_attrs,
    ),
    WowSensorDescription(
        key="game_statistics",
        translation_key="game_statistics",
        # Grosse Antwort mit mehreren hundert Werten: angelegt, aber aus.
        entity_registry_enabled_default=False,
        value_fn=lambda d: _count(
            p.game_statistics(d["game_statistics"])
            if d.get("game_statistics") is not None
            else None
        ),
        attrs_fn=lambda d: {"statistics": p.game_statistics(d.get("game_statistics"))},
    ),
    WowSensorDescription(
        key="quests_completed",
        translation_key="quests_completed",
        state_class=SensorStateClass.MEASUREMENT,
        # Nur die Anzahl: Die Liste umfasst tausende Quests.
        value_fn=lambda d: (
            _count((d.get("quests") or {}).get("quests"))
            if d.get("quests") is not None
            else None
        ),
    ),
)


def detail_available(coordinator: WowDetailCoordinator, key: str) -> bool:
    """Entitaet anlegen? Nie fuer Endpunkte, die die Spielversion nicht kennt.

    Ausserhalb von Retail (Forever, Classic) nur, wenn der Endpunkt Daten
    liefert oder noch nicht abgefragt werden konnte.
    """
    endpoint = endpoint_for_key(key)
    if endpoint is not None and not coordinator.supports_endpoint(endpoint):
        return False
    if coordinator.is_retail:
        return True
    data = coordinator.data or {}
    return endpoint not in data or data[endpoint] is not None


def has_value(
    coordinator: WowCoordinator | WowDetailCoordinator,
    description: WowSensorDescription,
) -> bool:
    """Ausserhalb von Retail nur Sensoren anlegen, die einen Wert haben.

    Blizzard dokumentiert keine Antwortfelder; fuer Forever und Classic ist
    nicht belegt, welche Felder von Retail es dort gibt. Ohne Antwort (Abfrage
    gescheitert oder Endpunkt noch nicht abgefragt) wird der Sensor angelegt.
    """
    data = coordinator.data
    if coordinator.is_retail or data is None:
        return True
    endpoint = endpoint_for_key(description.key)
    if endpoint is not None and endpoint not in data:
        return True
    return description.value_fn(data) is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WowConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    runtime = entry.runtime_data
    for subentry_id, coordinator in runtime.coordinators.items():
        detail = runtime.details[subentry_id]
        adder = EntityAdder(
            partial(async_add_entities, config_subentry_id=subentry_id),
            detail.key_allowed,
        )

        @callback
        def update(
            coordinator: WowCoordinator = coordinator,
            detail: WowDetailCoordinator = detail,
            adder: EntityAdder = adder,
        ) -> None:
            adder.add(_character_sensors(coordinator, detail))
            # Brackets mit Sensor fragt der Detail-Coordinator stuendlich ab.
            detail.pvp_bracket_sensors = {
                bracket
                for bracket in PVP_BRACKETS
                if f"{PVP_BRACKET_PREFIX}{bracket.lower()}" in adder.known
            }

        update()
        # Neue Berufe, Gilde, Brackets usw. ohne Neuladen anlegen.
        entry.async_on_unload(coordinator.async_add_listener(update))
        entry.async_on_unload(detail.async_add_listener(update))

    for world in runtime.worlds.values():
        adder = EntityAdder(async_add_entities)

        @callback
        def update_world(
            world: WowWorldCoordinator = world, adder: EntityAdder = adder
        ) -> None:
            adder.add(_world_sensors(world))
            # Ohne Sensor fragt die Spielwelt die WoW-Marke nur selten ab.
            world.token_sensor = "token" in adder.known

        update_world()
        entry.async_on_unload(world.async_add_listener(update_world))


Candidates = Iterator[tuple[str, Callable[[], SensorEntity]]]


def _character_sensors(
    coordinator: WowCoordinator, detail: WowDetailCoordinator
) -> Candidates:
    """Sensoren eines Charakters, die es nach den aktuellen Daten geben soll."""
    for d in PROFILE_SENSORS:
        if (coordinator.mythic_plus or not d.mythic_plus_only) and has_value(
            coordinator, d
        ):
            if d.key == "level":
                yield d.key, partial(WowLevelSensor, coordinator, d, detail)
            else:
                yield d.key, partial(WowSensor, coordinator, d)
    for d in DETAIL_SENSORS:
        if (
            (detail.mythic_plus or not d.mythic_plus_only)
            and not (d.non_retail_only and detail.is_retail)
            and detail_available(detail, d.key)
            and has_value(detail, d)
        ):
            yield d.key, partial(WowSensor, detail, d)
    # Berufe: je Beruf ein Sensor, auch fuer spaeter gelernte.
    for prof_id in _professions(detail):
        yield (
            f"{PROFESSION_PREFIX}{prof_id}",
            partial(WowProfessionSensor, detail, prof_id),
        )
    # Ausruestung: alle Plaetze, auch leere, damit Karten feste IDs haben.
    # Ausserhalb von Retail bekommen weitere Plaetze aus der Antwort einen
    # eigenen Sensor mit dem Namen des Platzes aus der API; welche Plaetze
    # Classic liefert, ist nicht dokumentiert.
    if detail_available(detail, f"{EQUIPMENT_PREFIX}head"):
        items = _items(detail.data or {}) or {}
        extra = [] if detail.is_retail else sorted(items.keys() - {*EQUIPMENT_SLOTS})
        for slot in (*EQUIPMENT_SLOTS, *extra):
            yield (
                f"{EQUIPMENT_PREFIX}{slot.lower()}",
                partial(WowEquipmentSensor, detail, slot),
            )
    if detail_available(detail, "reputation"):
        yield "reputation", partial(WowReputationSensor, detail)
    # Gilde: nur fuer Charaktere in einer Gilde, auch nach spaeterem Beitritt.
    if p.guild_path((coordinator.data or {}).get("profile")):
        yield "guild", partial(WowGuildSensor, detail)
    # Jaegerbegleiter: nur wenn die API Begleiter liefert; fuer andere
    # Klassen meldet sie 404.
    if (
        detail_available(detail, "hunter_pets")
        and (detail.data or {}).get("hunter_pets") is not None
    ):
        yield "hunter_pets", partial(WowHunterPetsSensor, detail)
    # PvP-Brackets: je Bracket mit Daten ein Sensor.
    if detail_available(detail, f"{PVP_BRACKET_PREFIX}3v3"):
        brackets = (detail.data or {}).get("pvp_brackets") or {}
        for bracket in sorted(b for b, value in brackets.items() if value is not None):
            yield (
                f"{PVP_BRACKET_PREFIX}{bracket.lower()}",
                partial(WowPvpBracketSensor, detail, bracket),
            )


def _world_sensors(world: WowWorldCoordinator) -> Candidates:
    data = world.data or {}
    # Retail kennt die WoW-Marke sicher; sonst erst, wenn die API einen Preis
    # liefert, z. B. nie in Classic-Regionen ohne WoW-Marke.
    if not world.suffix or data.get("token") is not None:
        yield "token", partial(WowTokenSensor, world)
    if world.mythic_plus:
        yield "weekly_reset", partial(WowResetSensor, world)
    for slug in realm_slugs(world):
        yield f"realm-{slug}-population", partial(WowRealmPopulationSensor, world, slug)


def realm_slugs(world: WowWorldCoordinator) -> list[str]:
    """Realms mit Entitaeten.

    Retail: alle Realms der Charaktere, auch wenn die erste Abfrage scheiterte.
    Forever und Classic: nur Realms, fuer die die API geantwortet hat.
    """
    if not world.suffix:
        return sorted(world.realms)
    realms = (world.data or {}).get("realms") or {}
    return sorted(slug for slug, realm in realms.items() if realm is not None)


class WowSensor(WowCharacterEntity, SensorEntity):
    """Sensor aus dem Profil- oder Detail-Coordinator eines Charakters."""

    entity_description: WowSensorDescription
    # Lange Listen fuer Karten (M+-Laeufe, Titel, Statistik-Fenster, Talente,
    # Talentbaum); nur die Sensoren mit diesen Attributen sind betroffen.
    _unrecorded_attributes = frozenset(
        {
            "runs",
            "titles",
            "statistics",
            "trees",
            "class_nodes",
            "spec_nodes",
            "hero_nodes",
            "gates",
        }
    )

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


class WowLevelSensor(WowSensor):
    """Level mit Profil-Attributen; Geschlecht und Transmog aus dem Aussehen.

    Das Aussehen fragt der Detail-Coordinator ab (alle 6 Stunden); der Sensor
    hoert deshalb auch auf ihn.
    """

    _unrecorded_attributes = WowSensor._unrecorded_attributes | {"transmog"}

    def __init__(
        self,
        coordinator: WowCoordinator,
        description: WowSensorDescription,
        detail: WowDetailCoordinator,
    ) -> None:
        super().__init__(coordinator, description)
        self._detail = detail

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._detail.async_add_listener(self._handle_coordinator_update)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs = super().extra_state_attributes
        if attrs is None:
            return None
        detail = self._detail.data or {}
        return {
            **attrs,
            **p.appearance(detail.get("appearance"), detail.get("transmog_names")),
        }


def _professions(detail: WowDetailCoordinator) -> dict[int, dict[str, Any]]:
    data = detail.data or {}
    return p.professions(
        data.get("professions"), data.get("profession_names"), data.get("tier_names")
    )


class WowProfessionSensor(WowCharacterEntity, SensorEntity):
    """Skill eines Berufs in der neuesten Erweiterungsstufe."""

    _attr_translation_key = "profession"
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
    def entity_picture(self) -> str | None:
        media = (self.coordinator.data or {}).get("media_urls") or {}
        return media.get(f"profession/{self._prof_id}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self._info()
        return {"tier": info.get("tier"), "max_skill": info.get("max_skill")}


class WowEquipmentSensor(WowCharacterEntity, SensorEntity):
    """Item auf einem Ausruestungsplatz: Itemlevel, Symbol als Bild.

    Classic Era nennt je Item kein Itemlevel; ausserhalb von Retail zeigt der
    Sensor dann den Namen des Items.
    """

    # Tooltip-Zeilen fuer Karten; aendern sich nur mit dem Item und bleiben
    # aus der Datenbank (18 Plaetze je Charakter).
    _unrecorded_attributes = frozenset({"tooltip"})

    def __init__(self, coordinator: WowDetailCoordinator, slot: str) -> None:
        key = f"{EQUIPMENT_PREFIX}{slot.lower()}"
        super().__init__(coordinator, key)
        self._slot = slot
        if slot in EQUIPMENT_SLOTS:
            self._attr_translation_key = key
        else:
            self._attr_translation_key = "equipment_other"
            self._attr_translation_placeholders = {
                "slot": self._item().get("slot_name") or slot
            }

    def _item(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return p.equipment(data.get("equipment")).get(self._slot, {})

    @property
    def native_value(self) -> int | str | None:
        item = self._item()
        level = item.get("level")
        if level is None and not self.coordinator.is_retail:
            return item.get("name")
        return level

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


class WowHunterPetsSensor(WowCharacterEntity, SensorEntity):
    """Anzahl der Begleiter eines Jaegers; Liste und aktive Begleiter als Attribute."""

    _attr_translation_key = "hunter_pets"
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Der Stall kann viele Begleiter fassen; die Liste nicht in die Datenbank.
    _unrecorded_attributes = frozenset({"pets"})

    def __init__(self, coordinator: WowDetailCoordinator) -> None:
        super().__init__(coordinator, "hunter_pets")

    def _pets(self) -> list[dict[str, Any]] | None:
        data = (self.coordinator.data or {}).get("hunter_pets")
        return p.hunter_pets(data) if data is not None else None

    @property
    def native_value(self) -> int | None:
        return _count(self._pets())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        pets = self._pets() or []
        summoned = next((pet["name"] for pet in pets if pet["summoned"]), None)
        return {
            "summoned": summoned,
            "active": [pet["name"] for pet in pets if pet["active"]],
            "pets": pets,
        }


class WowPvpBracketSensor(WowCharacterEntity, SensorEntity):
    """Wertung in einem PvP-Bracket; Spiele je Saison und Woche als Attribute."""

    _attr_translation_key = "pvp_bracket"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: WowDetailCoordinator, bracket: str) -> None:
        super().__init__(coordinator, f"{PVP_BRACKET_PREFIX}{bracket.lower()}")
        self._bracket = bracket
        self._attr_translation_placeholders = {"bracket": bracket.upper()}

    def _info(self) -> dict[str, Any]:
        brackets = (self.coordinator.data or {}).get("pvp_brackets") or {}
        return p.pvp_bracket(brackets.get(self._bracket))

    @property
    def native_value(self) -> int | None:
        return self._info()["rating"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {k: v for k, v in self._info().items() if k != "rating"}


class WowGuildSensor(WowCharacterEntity, SensorEntity):
    """Mitglieder der Gilde; Name, Erfolgspunkte und Aktivitaeten als Attribute."""

    _attr_translation_key = "guild"
    _attr_state_class = SensorStateClass.MEASUREMENT
    # Aktivitaeten wechseln oft, die Mitgliederliste ist lang; beide sind fuer
    # Karten gedacht.
    _unrecorded_attributes = frozenset({"activities", "members"})

    def __init__(self, coordinator: WowDetailCoordinator) -> None:
        super().__init__(coordinator, "guild")

    def _guild(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("guild")

    @property
    def native_value(self) -> int | None:
        return (self._guild() or {}).get("member_count")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        guild = self._guild() or {}
        created = p.timestamp(guild.get("created_timestamp"))
        return {
            "name": guild.get("name"),
            "realm": p.name_of(guild.get("realm")),
            "faction": p.name_of(guild.get("faction")),
            "achievement_points": guild.get("achievement_points"),
            "created": created.isoformat() if created else None,
            "activities": p.guild_activities(
                (self.coordinator.data or {}).get("guild_activity")
            ),
            "members": p.guild_members(
                (self.coordinator.data or {}).get("guild_roster"),
                (self.coordinator.data or {}).get("class_names"),
            ),
        }


class WowTokenSensor(WowWorldEntity, SensorEntity):
    _attr_translation_key = "token"
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
    """Bevoelkerung als uebersetzbarer Zustand (seit 0.22.0, vorher Text der API)."""

    _attr_translation_key = "realm_population"
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: WowWorldCoordinator, slug: str) -> None:
        super().__init__(coordinator, f"realm-{slug}-population")
        self._attr_options = list(REALM_POPULATIONS)
        self._slug = slug
        realm = (coordinator.data or {}).get("realms", {}).get(slug) or {}
        self._attr_translation_placeholders = {"realm": realm.get("name") or slug}

    @property
    def native_value(self) -> str | None:
        realm = (self.coordinator.data or {}).get("realms", {}).get(self._slug)
        value = str((realm or {}).get("population_type") or "").lower()
        return value if value in REALM_POPULATIONS else None
