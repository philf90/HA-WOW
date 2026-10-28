"""Tests fuer die Werte aus Version 0.6: Auswertungen der Ausruestung und neue Abfragen."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    API,
    EQUIPMENT,
    GAME,
    SPECIALIZATIONS,
    UID1,
    character_subentry,
    mock_api,
    mock_token,
)
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
    # Nur Hauptkategorien, Namen aus den statischen Spieldaten; Heldentaten
    # fehlen in der Antwort des Charakters und bleiben weg.
    assert ach.attributes["categories"] == [
        {"category": "Quests", "id": 96, "quantity": 200, "points": 2000},
        {
            "category": "Dungeons & Schlachtzüge",
            "id": 168,
            "quantity": 300,
            "points": 3500,
        },
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
    # Talentlisten ohne Tooltip-Texte, mit IDs und Rang
    assert frost["loadouts"][1]["selected_class_talents"] == [
        {
            "id": 1,
            "rank": 1,
            "default_points": None,
            "talent_id": None,
            "spell_id": None,
        }
    ]
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


async def test_achievement_categories_without_index(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ohne Hauptkategorien bleiben alle Kategorien der Antwort."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/achievement-category/index": 404})
    await _setup(hass, character_subentry())
    cats = _state(hass, "sensor", "achievements").attributes["categories"]
    assert [c["id"] for c in cats] == [96, 168, 14922]
    assert cats[1]["category"] == "Dungeons"


async def test_achievement_index_once(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    aioclient_mock.mock_calls.clear()
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._fetched.clear()
    await detail.async_refresh()
    urls = [str(call[1]) for call in aioclient_mock.mock_calls]
    assert any("/achievements" in u for u in urls)
    assert not any("achievement-category" in u for u in urls)


# Aufbau laut Typdefinitionen von @blizzard-api/wow 4.1.4 (Loadout,
# TalentTreeResponse); IDs und Namen erfunden.
TREE_PATH = "talent-tree/790/playable-specialization/64"
TREE = {
    "id": 790,
    "name": "Magier",
    "class_talent_nodes": [
        {
            "id": 100,
            "display_row": 1,
            "display_col": 5,
            "node_type": {"id": 0, "type": "ACTIVE"},
            "ranks": [
                {
                    "rank": 1,
                    "default_points": 1,
                    "tooltip": {
                        "talent": {"id": 200},
                        "spell_tooltip": {
                            "spell": {"id": 300, "name": "Talent A"},
                            "description": "Lange Beschreibung",
                        },
                    },
                }
            ],
            "unlocks": [101],
        },
        {
            "id": 101,
            "display_row": 2,
            "display_col": 5,
            "node_type": {"id": 2, "type": "CHOICE"},
            "ranks": [
                {
                    "rank": 1,
                    "choice_of_tooltips": [
                        {
                            "talent": {"id": 201},
                            "spell_tooltip": {"spell": {"id": 301, "name": "Wahl 1"}},
                        },
                        {
                            "talent": {"id": 202},
                            "spell_tooltip": {"spell": {"id": 302, "name": "Wahl 2"}},
                        },
                    ],
                }
            ],
            "locked_by": [100],
        },
    ],
    "spec_talent_nodes": [],
    "hero_talent_trees": [
        {
            "id": 39,
            "name": "Frostfeuer",
            "hero_talent_nodes": [
                {
                    "id": 110,
                    "display_row": 1,
                    "display_col": 1,
                    "node_type": {"id": 0, "type": "PASSIVE"},
                    "ranks": [{"rank": 1}, {"rank": 2}],
                }
            ],
        }
    ],
    "restriction_lines": [
        {"required_points": 8, "restricted_row": 5, "is_for_class": True}
    ],
}


def _with_tree_link() -> dict:
    specs = {
        **SPECIALIZATIONS,
        "specializations": list(SPECIALIZATIONS["specializations"]),
    }
    frost = specs["specializations"][1]
    active = {
        **frost["loadouts"][1],
        # Verweise wie in der echten Antwort vom 28.10.2026
        "selected_class_talent_tree": {
            "key": {"href": f"{GAME}/talent-tree/790?namespace=static-11.2.5_63660-eu"},
            "name": "Magier",
        },
        "selected_spec_talent_tree": {
            "key": {"href": f"{GAME}/{TREE_PATH}?namespace=static-11.2.5_63660-eu"},
            "name": "Frost",
        },
        "selected_class_talents": [
            {
                "id": 100,
                "rank": 1,
                "default_points": 1,
                "tooltip": {
                    "talent": {"id": 200},
                    "spell_tooltip": {
                        "spell": {"id": 300, "name": "Talent A"},
                        "description": "Lange Beschreibung",
                    },
                },
            }
        ],
    }
    specs["specializations"][1] = {**frost, "loadouts": [frost["loadouts"][0], active]}
    return specs


async def test_diagnostics_talent_tree(hass: HomeAssistant, aioclient_mock) -> None:
    """Diagnose laedt den Talentbaum des aktiven Loadouts, ohne Tooltip-Texte."""
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {f"{API}/specializations": _with_tree_link(), f"{GAME}/{TREE_PATH}": TREE},
    )
    entry = await _setup(hass, character_subentry())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    char = diag["characters"]["Testchar – Die Aldor"]

    frost = char["details"]["specializations"]["specializations"][1]
    assert frost["loadouts"][1]["selected_class_talents"] == [
        {"id": 100, "rank": 1, "default_points": 1, "talent_id": 200, "spell_id": 300}
    ]
    tree = char["talent_tree"]
    assert tree["path"] == TREE_PATH
    first, choice = tree["class_talent_nodes"]
    assert first == {
        "id": 100,
        "row": 1,
        "col": 5,
        "type": "ACTIVE",
        "ranks": 1,
        "default_points": 1,
        "talents": [{"talent_id": 200, "spell_id": 300, "name": "Talent A"}],
        "unlocks": [101],
        "locked_by": None,
    }
    assert [t["talent_id"] for t in choice["talents"]] == [201, 202]
    assert choice["locked_by"] == [100]
    hero = tree["hero_talent_trees"][0]
    assert (hero["name"], hero["nodes"][0]["ranks"]) == ("Frostfeuer", 2)
    assert tree["restriction_lines"][0]["required_points"] == 8
    assert "Lange Beschreibung" not in str(char)


async def test_diagnostics_talent_tree_error(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Scheitert die Abfrage, steht der Fehler in der Diagnose; sie bricht nicht ab."""
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {f"{API}/specializations": _with_tree_link(), f"{GAME}/{TREE_PATH}": 500},
    )
    entry = await _setup(hass, character_subentry())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    tree = diag["characters"]["Testchar – Die Aldor"]["talent_tree"]
    assert tree["path"] == TREE_PATH
    assert "error" in tree


async def test_diagnostics_without_tree_link(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ohne Verweis im Loadout (z. B. Classic) keine Abfrage."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["characters"]["Testchar – Die Aldor"]["talent_tree"] is None
    assert not any(
        "/talent-tree/" in str(call[1]) for call in aioclient_mock.mock_calls
    )


async def test_diagnostics_talent_tree_nodes_endpoint(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Verweis ohne Spezialisierung: Endpunkt "Talent Tree Nodes" mit talent_nodes."""
    mock_token(aioclient_mock)
    specs = _with_tree_link()
    # Ohne Verweis auf den Baum der Spezialisierung: Klassenbaum
    del specs["specializations"][1]["loadouts"][1]["selected_spec_talent_tree"]
    nodes = {"id": 790, "talent_nodes": TREE["class_talent_nodes"]}
    mock_api(
        aioclient_mock,
        {f"{API}/specializations": specs, f"{GAME}/talent-tree/790": nodes},
    )
    entry = await _setup(hass, character_subentry())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    tree = diag["characters"]["Testchar – Die Aldor"]["talent_tree"]
    assert tree["path"] == "talent-tree/790"
    assert [n["id"] for n in tree["talent_nodes"]] == [100, 101]
