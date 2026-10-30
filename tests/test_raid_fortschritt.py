"""Tests fuer 0.25.0/0.25.1: Raid-Fortschritt der aktuellen Erweiterung (W3)."""

import copy

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character import parsers as p
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    GAME,
    RAIDS,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

RAIDS_URL = f"{API}/encounters/raids"


async def _setup(hass: HomeAssistant, aioclient_mock, override: dict | None = None):
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, override)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _raid(hass: HomeAssistant, key: str = "raid_heroic"):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{UID1}-{key}"
    )
    return hass.states.get(entity_id)


def _mode(kind: str, done: int, total: int, kill: int | None = None) -> dict:
    progress: dict = {"completed_count": done, "total_count": total}
    if kill is not None:
        progress["encounters"] = [{"last_kill_timestamp": kill}]
    return {"difficulty": {"type": kind}, "progress": progress}


def _instance(raid_id: int, name: str, *modes: dict) -> dict:
    return {"instance": {"id": raid_id, "name": name}, "modes": list(modes)}


async def test_old_expansion_counts_as_zero(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Nur Kills einer alten Erweiterung: 0 in der aktuellen statt alter Werte."""
    old_only = {"expansions": RAIDS["expansions"][:1]}
    await _setup(hass, aioclient_mock, {RAIDS_URL: old_only})
    state = _raid(hass)
    assert state.state == "0"
    # Erweiterung und Raidnamen aus dem Journal, ohne Weltbosse
    assert state.attributes["expansion"] == "Neue Erweiterung (Journal)"
    assert state.attributes["raids"] == {
        "Neuer Raid (Journal)": "0/8",
        "Zweiter Raid": "0/4",
    }
    assert state.attributes["total_bosses"] == 12
    assert state.attributes["latest_raid"] is None


async def test_without_raid_history_zero(hass: HomeAssistant, aioclient_mock) -> None:
    """Antwort ohne expansions (nie geraidet): 0 statt unbekannt."""
    await _setup(hass, aioclient_mock, {RAIDS_URL: {"character": {}}})
    assert _raid(hass).state == "0"
    assert _raid(hass).attributes["total_bosses"] == 12
    # Der zweite Raid hat kein LFR.
    assert _raid(hass, "raid_lfr").attributes["total_bosses"] == 8


async def test_raid_in_two_tiers_counts_once(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Derselbe Raid unter "Current Season" und der Erweiterung zaehlt einmal."""
    raids = {
        "expansions": [
            {
                "expansion": {"id": 505, "name": "Current Season"},
                "instances": [
                    _instance(9201, "Neuer Raid", _mode("HEROIC", 5, 8, 2000)),
                    _instance(9202, "Zweiter Raid", _mode("HEROIC", 1, 4, 3000)),
                    # Raid einer anderen Erweiterung in "Current Season"
                    _instance(9101, "Alter Raid", _mode("HEROIC", 7, 9, 4000)),
                ],
            },
            {
                "expansion": {"id": 514, "name": "Neue Erweiterung"},
                "instances": [
                    _instance(9201, "Neuer Raid", _mode("HEROIC", 5, 8, 2000)),
                    _instance(9202, "Zweiter Raid", _mode("HEROIC", 1, 4, 3000)),
                ],
            },
        ]
    }
    await _setup(hass, aioclient_mock, {RAIDS_URL: raids})
    state = _raid(hass)
    assert state.state == "6"
    assert state.attributes["raids"] == {
        "Neuer Raid (Journal)": "5/8",
        "Zweiter Raid": "1/4",
    }
    assert state.attributes["total_bosses"] == 12
    assert state.attributes["latest_raid"] == "Zweiter Raid"
    assert state.attributes["expansion"] == "Neue Erweiterung (Journal)"


async def test_world_bosses_and_missing_difficulty_not_counted(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Kills bei Weltbossen und in Raids ohne LFR zaehlen nicht (seit 0.25.1)."""
    raids = {
        "expansions": [
            {
                "expansion": {"id": 514, "name": "Neue Erweiterung"},
                "instances": [
                    _instance(9201, "Neuer Raid", _mode("NORMAL", 2, 8, 1000)),
                    _instance(9203, "Weltbosse", _mode("NORMAL", 3, 4, 5000)),
                ],
            }
        ]
    }
    await _setup(hass, aioclient_mock, {RAIDS_URL: raids})
    normal = _raid(hass, "raid_normal")
    assert normal.state == "2"
    assert normal.attributes["raids"] == {
        "Neuer Raid (Journal)": "2/8",
        "Zweiter Raid": "0/4",
    }
    assert normal.attributes["latest_raid"] == "Neuer Raid (Journal)"
    assert "Weltbosse" not in normal.attributes["images"]


async def test_current_season_tier_not_newest(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """ "Current Season" (505) gilt nie als neueste Erweiterung."""
    await _setup(
        hass,
        aioclient_mock,
        {
            f"{GAME}/journal-expansion/index": {
                "tiers": [
                    {"id": 503, "name": "Alte Erweiterung"},
                    {"id": 505, "name": "Current Season"},
                ]
            },
            f"{GAME}/journal-expansion/503": {
                "raids": [{"id": 9101, "name": "Alter Raid"}]
            },
            f"{GAME}/journal-instance/9101": {"encounters": [{}] * 9},
            f"{GAME}/media/journal-instance/9101": 404,
        },
    )
    state = _raid(hass)
    assert state.state == "9"
    assert state.attributes["raids"] == {"Alter Raid": "9/9"}
    assert state.attributes["expansion"] == "Alte Erweiterung"


async def test_without_journal_as_before(hass: HomeAssistant, aioclient_mock) -> None:
    """Journal nicht erreichbar: Berechnung wie vor 0.25.0."""
    await _setup(hass, aioclient_mock, {f"{GAME}/journal-expansion/index": 500})
    state = _raid(hass)
    assert state.state == "6"
    assert state.attributes["raids"] == {"Neuer Raid": "6/8"}
    assert state.attributes["total_bosses"] == 8
    assert state.attributes["latest_raid"] == "Neuer Raid"


async def test_boss_count_from_answer_without_journal_instance(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ohne Instanz im Journal zaehlt total_count aus der Antwort.

    Ohne Kategorie und Schwierigkeiten zaehlt der Raid in jeder Schwierigkeit.
    """
    await _setup(hass, aioclient_mock, {f"{GAME}/journal-instance/9201": 404})
    assert _raid(hass).attributes["raids"] == {
        "Neuer Raid (Journal)": "6/8",
        "Zweiter Raid": "0/4",
    }
    assert _raid(hass, "raid_lfr").attributes["raids"] == {
        "Neuer Raid (Journal)": "0/0"
    }


async def test_boss_counts_looked_up_once(hass: HomeAssistant, aioclient_mock) -> None:
    """Die Bosszahl je Raid fragt die Spielwelt nur einmal ab."""
    entry = await _setup(hass, aioclient_mock)
    (world,) = entry.runtime_data.worlds.values()
    world._fetched.clear()
    await world.async_refresh()

    def calls(path: str) -> int:
        return sum(1 for c in aioclient_mock.mock_calls if path in str(c[1]))

    assert calls("/journal-expansion/index") == 2
    assert calls("/data/wow/journal-instance/9201") == 1
    # Kategorie und Schwierigkeiten auch fuer die Diagnose
    assert world.data["raid_journal"] == {
        "id": 514,
        "name": "Neue Erweiterung (Journal)",
        "raids": [
            {
                "id": 9201,
                "name": "Neuer Raid (Journal)",
                "bosses": 8,
                "category": "RAID",
                "modes": ["LFR", "NORMAL", "HEROIC", "MYTHIC"],
            },
            {
                "id": 9202,
                "name": "Zweiter Raid",
                "bosses": 4,
                "category": "RAID",
                "modes": ["NORMAL", "HEROIC", "MYTHIC"],
            },
            {
                "id": 9203,
                "name": "Weltbosse",
                "bosses": 4,
                "category": "WORLD_BOSS",
                "modes": ["NORMAL"],
            },
        ],
    }


@pytest.mark.parametrize("journal", [None, {"id": 514, "raids": [{"id": 1}]}])
def test_no_raid_answer_unknown(journal) -> None:
    """Ohne Antwort des Endpunkts bleibt der Sensor unbekannt."""
    assert p.raid_progress(None, "HEROIC", journal) == (None, {})
    assert p.raid_instances(None, journal) == {}


def test_journal_raid_order_and_names() -> None:
    """Reihenfolge und Namen des Journals; ohne Kategorie zaehlt der Raid mit."""
    raids = copy.deepcopy(RAIDS)
    journal = {
        "id": 514,
        "name": "J",
        "raids": [
            {"id": 9202, "name": "Zweiter Raid", "bosses": 4},
            {"id": 9201, "name": None, "bosses": 8},
        ],
    }
    # Ohne Namen im Journal der Name aus der Antwort des Charakters
    assert list(p.raid_progress(raids, "HEROIC", journal)[1]["raids"]) == [
        "Zweiter Raid",
        "Neuer Raid",
    ]
    assert p.raid_instances(raids, journal) == {
        "Zweiter Raid": 9202,
        "Neuer Raid": 9201,
    }


# Raid-Bilder beim Bildserver pruefen

NEW_IMAGE = "https://render.example/neu.jpg"


def _heads(aioclient_mock, url: str) -> int:
    return sum(
        1
        for c in aioclient_mock.mock_calls
        if c[0].upper() == "HEAD" and str(c[1]) == url
    )


async def _refresh_details(entry) -> None:
    (detail,) = entry.runtime_data.details.values()
    detail._fetched.clear()
    await detail.async_refresh()


@pytest.mark.parametrize("status", [403, 404])
async def test_image_missing_on_server(
    hass: HomeAssistant, aioclient_mock, status: int
) -> None:
    """Liefert der Bildserver nichts, fehlt das Bild; geprueft wird einmal."""
    mock_token(aioclient_mock)
    aioclient_mock.head(NEW_IMAGE, status=status)
    entry = await _setup(hass, aioclient_mock)
    assert _raid(hass).attributes["images"]["Neuer Raid (Journal)"] is None
    await _refresh_details(entry)
    await hass.async_block_till_done()
    assert _heads(aioclient_mock, NEW_IMAGE) == 1
    assert _raid(hass).attributes["images"]["Neuer Raid (Journal)"] is None


async def test_image_check_failure_retried(hass: HomeAssistant, aioclient_mock) -> None:
    """Bildserver nicht erreichbar: Bild fehlt vorerst, naechster Takt prueft neu."""
    aioclient_mock.head(NEW_IMAGE, exc=TimeoutError())
    entry = await _setup(hass, aioclient_mock)
    assert _raid(hass).attributes["images"]["Neuer Raid (Journal)"] is None

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _refresh_details(entry)
    await hass.async_block_till_done()
    assert _raid(hass).attributes["images"]["Neuer Raid (Journal)"] == NEW_IMAGE


async def test_only_raid_images_checked(hass: HomeAssistant, aioclient_mock) -> None:
    """Andere Symbole (z. B. Berufe) prueft die Integration nicht."""
    await _setup(hass, aioclient_mock)
    heads = [c for c in aioclient_mock.mock_calls if c[0].upper() == "HEAD"]
    assert [str(c[1]) for c in heads] == [NEW_IMAGE]
    assert _raid(hass).attributes["images"]["Neuer Raid (Journal)"] == NEW_IMAGE
