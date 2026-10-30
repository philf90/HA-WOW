"""Tests fuer 0.28.0: Dungeon-Fortschritt nur in der Diagnose (Vorbereitung E9)."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.const import DOMAIN
from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    API,
    DUNGEONS,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)


async def _setup(hass: HomeAssistant, aioclient_mock, options: dict | None = None):
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    if options is not None:
        hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _calls(aioclient_mock) -> int:
    return sum(
        1
        for c in aioclient_mock.mock_calls
        if str(c[1]).startswith(f"{API}/encounters/dungeons")
    )


async def test_dungeons_in_diagnostics(hass: HomeAssistant, aioclient_mock) -> None:
    """Die Antwort steht unveraendert in der Diagnose; keine Entitaet dafuer."""
    entry = await _setup(hass, aioclient_mock)
    assert _calls(aioclient_mock) == 1
    diag = await async_get_config_entry_diagnostics(hass, entry)
    character = diag["characters"]["Testchar – Die Aldor"]
    assert character["details"]["dungeons"] == DUNGEONS
    assert "dungeons" in character["needed_endpoints"]
    unique_ids = [
        e.unique_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.platform == DOMAIN
    ]
    assert unique_ids
    assert not [u for u in unique_ids if "dungeon" in u]


@pytest.mark.parametrize(
    ("options", "rare"), [(None, 360), ({"rare_minutes": 720}, 720)]
)
async def test_dungeons_rare_interval(
    hass: HomeAssistant, aioclient_mock, options, rare
) -> None:
    """Ohne Entitaet im seltenen Takt (Vorgabe 6 h), nicht stuendlich."""
    entry = await _setup(hass, aioclient_mock, options)
    (detail,) = entry.runtime_data.details.values()
    assert detail.endpoint_intervals()["dungeons"] == rare

    # Eine Stunde spaeter: Raids wieder abgefragt, Dungeons nicht
    for key in detail._fetched:
        detail._fetched[key] -= 61 * 60
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock) == 1


async def test_dungeons_not_found(hass: HomeAssistant, aioclient_mock) -> None:
    """404 (z. B. Charakter ohne Dungeon-Daten): kein Fehler, Wert leer."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/encounters/dungeons": 404})
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    (detail,) = entry.runtime_data.details.values()
    assert detail.last_update_success
    assert detail.data["dungeons"] is None
