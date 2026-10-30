"""Tests fuer 0.29.1: M+-Season mit Beginn und Ende in der Diagnose (Vorbereitung E8)."""

from homeassistant.core import HomeAssistant

from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import GAME, character_subentry, main_entry, mock_api, mock_token

SEASON_URL = f"{GAME}/mythic-keystone/season/14"


async def _setup(hass: HomeAssistant, aioclient_mock, override: dict | None = None):
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, override)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _world(entry):
    (world,) = entry.runtime_data.worlds.values()
    return world


async def test_season_info_in_diagnostics(hass: HomeAssistant, aioclient_mock) -> None:
    """Zeitfelder, Name, Periodenzahl und vorhandene Schluessel der Antwort."""
    entry = await _setup(hass, aioclient_mock)
    expected = {
        "keys": ["id", "periods", "season_name", "start_timestamp"],
        "id": 14,
        "season_name": None,
        "start_timestamp": 1760425200000,
        "end_timestamp": None,
        "periods": 2,
        "first_period": 1000,
        "last_period": 1001,
    }
    assert _world(entry).data["season_info"] == expected
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["worlds"]["eu"]["season_info"] == expected


async def test_season_with_end(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(
        hass,
        aioclient_mock,
        {
            SEASON_URL: {
                "id": 14,
                "start_timestamp": 1,
                "end_timestamp": 2,
                "season_name": "Season 14",
                "periods": [],
            }
        },
    )
    info = _world(entry).data["season_info"]
    assert (info["end_timestamp"], info["season_name"], info["periods"]) == (
        2,
        "Season 14",
        0,
    )
    assert info["first_period"] is None


async def test_season_info_error_keeps_rest(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Scheitert nur die Season-Abfrage, laufen die anderen Teile weiter."""
    entry = await _setup(hass, aioclient_mock, {SEASON_URL: 500})
    world = _world(entry)
    assert world.last_update_success
    assert world.data["season_id"] == 14
    assert "season_info" not in world.data


async def test_no_season_id_no_query(hass: HomeAssistant, aioclient_mock) -> None:
    """Ohne Season-ID fragt die Spielwelt keine Season ab."""
    entry = await _setup(
        hass, aioclient_mock, {f"{GAME}/mythic-keystone/season/index": {}}
    )
    assert _world(entry).data["season_id"] is None
    assert not [
        c for c in aioclient_mock.mock_calls if str(c[1]).startswith(SEASON_URL)
    ]
