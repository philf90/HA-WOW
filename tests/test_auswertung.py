"""Tests fuer die Werte aus Version 0.6: Auswertungen der Ausruestung und neue Abfragen."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import API, EQUIPMENT, UID1, character_subentry, mock_api, mock_token
from .test_details import _eid, _setup, _state


async def test_equipment_summaries(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, character_subentry())

    sockets = _state(hass, "sensor", "empty_sockets")
    assert sockets.state == "1"
    assert sockets.attributes["sockets"] == [
        {"slot": "HEAD", "slot_name": "Kopf", "type": "PRISMATIC"}
    ]

    enchants = _state(hass, "sensor", "enchantments")
    assert enchants.state == "1"
    assert enchants.attributes["slots"] == [
        {
            "slot": "HEAD",
            "slot_name": "Kopf",
            "enchantments": ["Verzaubert: +16 Intelligenz"],
        }
    ]

    item_set = _state(hass, "sensor", "item_set")
    assert item_set.state == "1"
    assert item_set.attributes["name"] == "Testset"
    assert item_set.attributes["total"] == 2
    assert item_set.attributes["items"][1] == {"name": "Testhose", "equipped": False}
    assert item_set.attributes["effects"] == [
        {"text": "Set: +5 Testwert", "active": False, "required": 2}
    ]
    assert item_set.attributes["other_sets"] == []


async def test_equipment_summaries_without_set(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ohne Set ist der Zustand 0, ohne Ausruestung unbekannt."""
    items = [
        {k: v for k, v in item.items() if k != "set"}
        for item in EQUIPMENT["equipped_items"]
    ]
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/equipment": {"equipped_items": items}})
    await _setup(hass, character_subentry())
    item_set = _state(hass, "sensor", "item_set")
    assert item_set.state == "0"
    assert item_set.attributes["name"] is None


async def test_no_equipment(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/equipment": 404})
    await _setup(hass, character_subentry())
    for key in ("empty_sockets", "enchantments", "item_set"):
        assert _state(hass, "sensor", key).state == "unknown", key


async def test_several_sets(hass: HomeAssistant, aioclient_mock) -> None:
    """Das Set mit den meisten angelegten Teilen steht vorn."""
    head, weapon = EQUIPMENT["equipped_items"]
    weapon = {
        **weapon,
        "set": {
            "item_set": {"name": "Grosses Set"},
            "items": [
                {"item": {"name": "A"}, "is_equipped": True},
                {"item": {"name": "B"}, "is_equipped": True},
                {"item": {"name": "C"}},
            ],
            "effects": [],
        },
    }
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/equipment": {"equipped_items": [head, weapon]}})
    await _setup(hass, character_subentry())
    item_set = _state(hass, "sensor", "item_set")
    assert item_set.state == "2"
    assert item_set.attributes["name"] == "Grosses Set"
    assert item_set.attributes["other_sets"] == [
        {"name": "Testset", "equipped": 1, "total": 2}
    ]


async def test_achievements_specialization_titles(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, character_subentry())

    ach = _state(hass, "sensor", "achievements")
    assert ach.state == "1500"
    assert ach.attributes["total_points"] == 12345
    assert ach.attributes["categories"] == [
        {"category": "Quests", "id": 96, "quantity": 200, "points": 2000},
        {"category": "Dungeons", "id": 168, "quantity": 300, "points": 3500},
    ]

    spec = _state(hass, "sensor", "specialization")
    assert spec.state == "Frost"
    assert spec.attributes["id"] == 64
    assert spec.attributes["hero_talents"] == "Frostfeuer"
    # Aktives Loadout der aktiven Spezialisierung, nicht das einer anderen
    assert spec.attributes["loadout_code"] == "CODE123"
    assert spec.attributes["specializations"] == ["Arkan", "Frost"]

    titles = _state(hass, "sensor", "titles")
    assert titles.state == "2"
    assert titles.attributes["active"] == "Champion"
    assert titles.attributes["titles"] == ["Champion", "Entdecker"]


async def test_mythic_runs(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, character_subentry())
    runs = _state(hass, "sensor", "mythic_best_key").attributes["runs"]
    assert len(runs) == 3
    assert runs[0] == {
        "dungeon": "Dungeon A",
        "dungeon_id": 501,
        "level": 12,
        "timed": True,
        "duration": 1835,
        "completed": "2025-10-20T22:40:00+00:00",
        "rating": 301.5,
        "color": "#ff8000",
        "affixes": ["Tyrannisch", "Xal'ataths Pakt"],
        "members": [
            {
                "name": "Testchar",
                "realm": "Die Aldor",
                "spec": "Frost",
                "item_level": 701,
            }
        ],
    }
    # Fehlende Angaben ergeben None bzw. leere Listen statt eines Fehlers.
    assert runs[2]["duration"] is None
    assert runs[2]["members"] == []
    assert runs[2]["timed"] is False


async def test_game_statistics(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())

    # Standardmaessig aus und dann nicht abgefragt
    ent_reg = er.async_get(hass)
    entity_id = _eid(hass, "sensor", f"{UID1}-game_statistics")
    assert (
        ent_reg.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    )
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    assert "game_statistics" not in detail.needed_endpoints()

    ent_reg.async_update_entity(entity_id, disabled_by=None)
    assert "game_statistics" in detail.needed_endpoints()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    stats = hass.states.get(entity_id)
    assert stats.state == "2"
    assert stats.attributes["statistics"] == [
        {"id": 60, "name": "Tode insgesamt", "category": "Charakter", "quantity": 42},
        {
            "id": 328,
            "name": "Gesamtes Gold erhalten",
            "category": "Charakter / Reichtum",
            "quantity": 1e7,
        },
    ]


def test_long_lists_not_recorded() -> None:
    from custom_components.wow_character.sensor import WowSensor

    assert {"runs", "titles", "statistics"} <= WowSensor._unrecorded_attributes


async def test_diagnostics_new_endpoints(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    details = diag["characters"]["Testchar – Die Aldor"]["details"]
    assert details["achievements"]["category_progress"][0]["points"] == 2000
    frost = details["specializations"]["specializations"][1]
    # Talentlisten nur als Anzahl
    assert frost["loadouts"][1]["selected_class_talents"] == 1
    assert frost["loadouts"][1]["talent_loadout_code"] == "CODE123"
    assert details["titles"]["count"] == 2
    assert details["tier_names"] == {2872: "Neue Schmiedekunst (deutsch)"}


def test_run_seconds() -> None:
    from custom_components.wow_character.parsers import _run_seconds

    # Millisekunden und Sekunden ergeben dieselbe Dauer
    assert _run_seconds(1834567) == 1835
    assert _run_seconds(1835) == 1835
    assert _run_seconds(None) is None
    assert _run_seconds(0) is None
