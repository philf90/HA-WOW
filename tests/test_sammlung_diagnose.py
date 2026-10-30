"""Tests fuer 0.30.1: Erbstuecke und Transmog-Vorlagen nur in der Diagnose (E9)."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.const import DOMAIN
from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    API,
    HEIRLOOMS,
    TRANSMOGS,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

HEIRLOOMS_URL = f"{API}/collections/heirlooms"
TRANSMOGS_URL = f"{API}/collections/transmogs"


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


def _calls(aioclient_mock, url: str) -> int:
    return sum(1 for c in aioclient_mock.mock_calls if str(c[1]).startswith(url))


async def _details(hass: HomeAssistant, entry) -> dict:
    diag = await async_get_config_entry_diagnostics(hass, entry)
    return diag["characters"]["Testchar – Die Aldor"]["details"]


async def test_in_diagnostics_shortened(hass: HomeAssistant, aioclient_mock) -> None:
    """Beide Antworten gekuerzt in der Diagnose; keine Entitaet dafuer."""
    entry = await _setup(hass, aioclient_mock)
    assert _calls(aioclient_mock, HEIRLOOMS_URL) == 1
    assert _calls(aioclient_mock, TRANSMOGS_URL) == 1
    details = await _details(hass, entry)
    assert details["heirlooms"] == {
        "keys": ["heirlooms"],
        "count": 4,
        "upgrade_levels": {"0": 1, "2": 1, "6": 2},
        "first": HEIRLOOMS["heirlooms"][:3],
    }
    assert details["transmogs"] == {
        "keys": ["appearance_sets", "slots"],
        "appearance_sets": 5,
        "first_sets": TRANSMOGS["appearance_sets"][:3],
        "slots": [
            {"slot": {"type": "HEAD", "name": "Kopf"}, "appearances": 7},
            {"slot": {"type": "BACK", "name": "Ruecken"}, "appearances": 1},
        ],
        "first_appearances": [{"id": 1}, {"id": 2}],
    }
    unique_ids = [
        e.unique_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.platform == DOMAIN
    ]
    assert unique_ids
    assert not [u for u in unique_ids if "heirloom" in u or "transmog" in u]


async def test_unexpected_answer(hass: HomeAssistant, aioclient_mock) -> None:
    """Fehlende Listen und fremde Eintraege brechen die Diagnose nicht."""
    entry = await _setup(
        hass,
        aioclient_mock,
        {
            HEIRLOOMS_URL: {"heirlooms": [{"heirloom": {"id": 9}}, "kaputt"]},
            TRANSMOGS_URL: {"slots": [{"slot": {"type": "HEAD"}}, None]},
        },
    )
    details = await _details(hass, entry)
    assert details["heirlooms"]["count"] == 1
    assert details["heirlooms"]["upgrade_levels"] == {"None": 1}
    assert details["transmogs"]["appearance_sets"] == 0
    assert details["transmogs"]["slots"] == [
        {"slot": {"type": "HEAD"}, "appearances": 0}
    ]
    assert details["transmogs"]["first_appearances"] == []


@pytest.mark.parametrize(
    ("options", "rare"), [(None, 360), ({"rare_minutes": 720}, 720)]
)
async def test_rare_interval(
    hass: HomeAssistant, aioclient_mock, options, rare
) -> None:
    """Ohne Entitaet im seltenen Takt (Vorgabe 6 h), nicht stuendlich."""
    entry = await _setup(hass, aioclient_mock, options=options)
    (detail,) = entry.runtime_data.details.values()
    intervals = detail.endpoint_intervals()
    assert intervals["heirlooms"] == intervals["transmogs"] == rare

    # Eine Stunde spaeter: Raids wieder abgefragt, diese beiden nicht
    for key in detail._fetched:
        detail._fetched[key] -= 61 * 60
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, HEIRLOOMS_URL) == 1
    assert _calls(aioclient_mock, TRANSMOGS_URL) == 1


async def test_group_collections_off(hass: HomeAssistant, aioclient_mock) -> None:
    """Gruppe "Sammlungen" ausgeschaltet: keine Abfrage."""
    await _setup(hass, aioclient_mock, options={"disabled_groups": ["collections"]})
    assert _calls(aioclient_mock, HEIRLOOMS_URL) == 0
    assert _calls(aioclient_mock, TRANSMOGS_URL) == 0


async def test_not_found(hass: HomeAssistant, aioclient_mock) -> None:
    """404: kein Fehler, Wert leer."""
    entry = await _setup(hass, aioclient_mock, {HEIRLOOMS_URL: 404, TRANSMOGS_URL: 404})
    (detail,) = entry.runtime_data.details.values()
    assert detail.last_update_success
    assert detail.data["heirlooms"] is None
    assert detail.data["transmogs"] is None
