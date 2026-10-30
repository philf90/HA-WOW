"""Tests fuer 0.22.0: Diagnose ohne andere Spieler (W6), Texte ohne feste Sprache (W5)."""

import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.const import DOMAIN
from custom_components.wow_character.diagnostics import (
    _without_players,
    async_get_config_entry_diagnostics,
)

from .conftest import (
    API,
    GAME,
    MYTHIC,
    PROFILE,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

GUILD = "https://eu.api.blizzard.com/data/wow/guild/die-aldor/testgilde"
# Verweise wie in echten Antworten: key.href enthaelt Realm und Name.
OTHER = {
    "key": {"href": "https://eu.api.blizzard.com/profile/wow/character/x/fremder"},
    "name": "Fremder",
    "id": 4242,
    "realm": {"name": "Die Aldor", "slug": "die-aldor"},
}
GUILD_ANSWERS = {
    API: {
        **PROFILE,
        "guild": {"key": {"href": f"{GUILD}?namespace=profile-eu"}, "name": "Gilde"},
    },
    GUILD: {"name": "Testgilde", "member_count": 2},
    f"{GUILD}/activity": {
        "activities": [
            {
                "activity": {"type": "CHARACTER_ACHIEVEMENT"},
                "character_achievement": {
                    "character": OTHER,
                    "achievement": {"name": "Ein Erfolg"},
                },
                "timestamp": 1761000000000,
            }
        ]
    },
    f"{GUILD}/roster": {
        "members": [
            {
                "character": {**OTHER, "level": 80, "playable_class": {"id": 8}},
                "rank": 2,
            }
        ]
    },
    f"{GAME}/playable-class/8": {"id": 8, "name": "Magier"},
    # Mythic+-Profil mit Laeufen der laufenden Woche samt Gruppe
    f"{API}/mythic-keystone-profile": {
        **MYTHIC,
        "current_period": {
            "best_runs": [
                {
                    "keystone_level": 9,
                    "members": [
                        {"character": OTHER, "specialization": {"name": "Heilig"}}
                    ],
                }
            ]
        },
    },
    f"{API}/mythic-keystone-profile/season/14": {
        "best_runs": [
            {
                "dungeon": {"name": "Dungeon A"},
                "keystone_level": 12,
                "is_completed_within_time": True,
                "members": [
                    {
                        "character": OTHER,
                        "specialization": {"name": "Heilig"},
                        "equipped_item_level": 700,
                    }
                ],
            },
            {
                "dungeon": {"name": "Dungeon B"},
                "keystone_level": 10,
                "is_completed_within_time": False,
            },
        ]
    },
}


async def _setup(hass: HomeAssistant, subentry=None):
    entry = main_entry(subentry or character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{UID1}-{key}"
    )
    return hass.states.get(entity_id)


# W6: Diagnose


async def test_diagnostics_without_other_players(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, GUILD_ANSWERS)
    entry = await _setup(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    character = diag["characters"]["Testchar – Die Aldor"]
    text = json.dumps(character, ensure_ascii=False)
    # Weder Name noch ID noch Verweis des fremden Spielers
    for value in ("Fremder", "fremder", "4242"):
        assert value not in text, value

    details = character["details"]
    member = details["mythic_season"]["best_runs"][0]["members"][0]
    # Was zum Pruefen der Feldnamen noetig ist, bleibt.
    assert member == {
        "character": {"realm": {"name": "Die Aldor", "slug": "die-aldor"}},
        "specialization": {"name": "Heilig"},
        "equipped_item_level": 700,
    }
    roster = details["guild_roster"]
    assert roster["count"] == 1
    assert roster["first"][0]["character"] == {
        "realm": {"name": "Die Aldor", "slug": "die-aldor"},
        "level": 80,
        "playable_class": {"id": 8},
    }
    activity = details["guild_activity"]["first"][0]["character_achievement"]
    assert activity["achievement"] == {"name": "Ein Erfolg"}
    period = character["profile"]["mythic"]["current_period"]["best_runs"][0]
    assert period["members"][0]["character"] == {
        "realm": {"name": "Die Aldor", "slug": "die-aldor"}
    }
    # Der eigene Charakter bleibt erkennbar (Profil ohne Schluessel "character").
    assert character["profile"]["profile"]["name"] == "Testchar"


def test_without_players_leaves_other_data() -> None:
    data = {
        "name": "Eigene Gilde",
        "items": [{"character": {"name": "X", "level": 3}, "name": "Gegenstand"}],
        "character": "kein Objekt",
    }
    assert _without_players(data) == {
        "name": "Eigene Gilde",
        "items": [{"character": {"level": 3}, "name": "Gegenstand"}],
        "character": "kein Objekt",
    }


# W5: Texte und Zustaende


async def test_best_runs_without_fixed_text(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """best_runs ohne deutsches "in Zeit"; ob in Zeit, steht in runs."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, GUILD_ANSWERS)
    await _setup(hass)
    attrs = _state(hass, "mythic_best_key").attributes
    assert attrs["best_runs"] == {"Dungeon A": "+12", "Dungeon B": "+10"}
    assert [r["timed"] for r in attrs["runs"]] == [True, False]


@pytest.mark.parametrize(
    ("population", "state"),
    [
        ({"name": "Voll", "type": "FULL"}, "full"),
        ({"name": "Empfohlen", "type": "RECOMMENDED"}, "recommended"),
        # Unbekannter Wert: unbekannt statt Fehler
        ({"name": "Neu", "type": "NEW_PLAYERS"}, "unknown"),
        ({"name": "Hoch"}, "unknown"),
    ],
)
async def test_population_state(
    hass: HomeAssistant, aioclient_mock, caplog, population, state
) -> None:
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{GAME}/connected-realm/1234": {
                "status": {"type": "UP"},
                "population": population,
                "has_queue": False,
            }
        },
    )
    entry = await _setup(hass)
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.unique_id}-world-eu-realm-die-aldor-population"
    )
    assert hass.states.get(entity_id).state == state
    assert "not in the list of options" not in caplog.text


@pytest.mark.parametrize(
    ("version", "suffix", "model"),
    [
        ("retail", "", "World of Warcraft"),
        ("classic_era", "-classic1x", "World of Warcraft Classic Era"),
    ],
)
async def test_device_model(
    hass: HomeAssistant, aioclient_mock, version, suffix, model
) -> None:
    """Gerätemodell mit lesbarer Spielversion statt internem Schlüssel."""
    sub = character_subentry()
    sub["data"] = {**sub["data"], "game_version": version, "namespace_suffix": suffix}
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, sub)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, UID1)})
    assert device.model == model
