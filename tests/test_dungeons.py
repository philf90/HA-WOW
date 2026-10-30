"""Tests fuer 0.29.0: Sensor "Dungeons" (E9, Variante B)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character import parsers as p
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    GAME,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

DUNGEONS_URL = f"{API}/encounters/dungeons"


async def _setup(
    hass: HomeAssistant,
    aioclient_mock,
    override: dict | None = None,
    options: dict | None = None,
):
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, override)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    if options is not None:
        hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{UID1}-dungeons")


def _mode(kind: str | None, name: str | None, status: str = "COMPLETE") -> dict:
    return {
        "difficulty": {"type": kind, "name": name} if kind else {},
        "status": {"type": status},
        "progress": {"completed_count": 1, "total_count": 1},
    }


def _instance(dungeon_id: int, name: str, *modes: dict) -> dict:
    return {"instance": {"id": dungeon_id, "name": name}, "modes": list(modes)}


async def test_dungeon_sensor(hass: HomeAssistant, aioclient_mock) -> None:
    """Abgeschlossene Dungeons der Erweiterung, hoechste Schwierigkeit je Dungeon."""
    await _setup(hass, aioclient_mock)
    state = hass.states.get(_entity_id(hass))
    assert state.state == "1"
    assert state.attributes["expansion"] == "Neue Erweiterung (Journal)"
    assert state.attributes["total_dungeons"] == 2
    # Leere Schwierigkeit {} zaehlt nicht; Namen und Zahl aus dem Journal
    assert state.attributes["dungeons"] == {
        "Erster Dungeon (Journal)": "Mythisch",
        "Zweiter Dungeon": None,
    }


async def test_never_completed_zero(hass: HomeAssistant, aioclient_mock) -> None:
    """Antwort ohne expansions (live z. B. bei niedrigen Stufen): 0 statt unbekannt."""
    await _setup(hass, aioclient_mock, {DUNGEONS_URL: {"_links": {}}})
    state = hass.states.get(_entity_id(hass))
    assert state.state == "0"
    assert state.attributes["total_dungeons"] == 2


async def test_no_answer_unknown(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass, aioclient_mock, {DUNGEONS_URL: 404})
    assert hass.states.get(_entity_id(hass)).state == "unknown"


async def test_without_journal(hass: HomeAssistant, aioclient_mock) -> None:
    """Journal nicht erreichbar: neueste Erweiterung der Antwort, Gesamtzahl unbekannt."""
    await _setup(hass, aioclient_mock, {f"{GAME}/journal-expansion/index": 500})
    state = hass.states.get(_entity_id(hass))
    assert state.state == "1"
    assert state.attributes["expansion"] == "Neue Erweiterung"
    assert state.attributes["total_dungeons"] is None
    assert state.attributes["dungeons"] == {"Erster Dungeon": "Mythisch"}


async def test_hourly_and_group(hass: HomeAssistant, aioclient_mock) -> None:
    """Mit Sensor im Takt "Details"; ausgeschaltete Gruppe: keine Abfrage."""
    entry = await _setup(hass, aioclient_mock)
    (detail,) = entry.runtime_data.details.values()
    assert detail.endpoint_intervals()["dungeons"] == 60
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "disabled_groups": ["dungeons"]}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not [
        c for c in aioclient_mock.mock_calls if str(c[1]).startswith(DUNGEONS_URL)
    ]


def test_best_difficulty_and_status() -> None:
    """Hoechste abgeschlossene Schwierigkeit; IN_PROGRESS und {} zaehlen nicht."""
    dungeons = {
        "expansions": [
            {
                "expansion": {"id": 514},
                "instances": [
                    _instance(
                        1,
                        "Eins",
                        _mode("HEROIC", "Heroisch"),
                        _mode("MYTHIC_KEYSTONE", "Mythisch+"),
                        _mode("NORMAL", "Normal"),
                    ),
                    _instance(2, "Zwei", _mode("MYTHIC", "Mythisch", "IN_PROGRESS")),
                    _instance(3, "Drei", _mode(None, None)),
                ],
            }
        ]
    }
    journal = {
        "id": 514,
        "name": "J",
        "dungeons": [{"id": 1, "name": "Eins"}, {"id": 2}, {"id": 3, "name": "Drei"}],
    }
    state, attrs = p.dungeon_progress(dungeons, journal)
    assert state == 1
    # Ohne Namen im Journal der Name aus der Antwort
    assert attrs["dungeons"] == {"Eins": "Mythisch+", "Zwei": None, "Drei": None}


def test_fallback_ignores_current_season() -> None:
    """Ohne Journal: "Current Season" (505) gilt nicht als neueste Erweiterung."""
    dungeons = {
        "expansions": [
            {
                "expansion": {"id": 503, "name": "Alt"},
                "instances": [_instance(1, "Alter Dungeon", _mode("NORMAL", "Normal"))],
            },
            {
                "expansion": {"id": 505, "name": "Current Season"},
                "instances": [_instance(2, "Saison", _mode("HEROIC", "Heroisch"))],
            },
        ]
    }
    state, attrs = p.dungeon_progress(dungeons)
    assert state == 1
    assert attrs["expansion"] == "Alt"
    assert attrs["dungeons"] == {"Alter Dungeon": "Normal"}
    # Nur "Current Season": keine Erweiterung bekannt
    only_season = {"expansions": dungeons["expansions"][1:]}
    assert p.dungeon_progress(only_season) == (None, {})
