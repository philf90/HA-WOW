"""Tests fuer den Sensor Jaegerbegleiter (Endpunkt hunter-pets).

Endpunkt laut Blizzard-Doku fuer Retail und Classic; fuer Nicht-Jaeger meldet
er 404. Felder wie in den Typdefinitionen von @blizzard-api/wow 4.1.4 und
@blizzard-api/classic-wow 4.2.0; Werte erfunden.
"""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.const import DOMAIN
from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    API,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

HUNTER_PETS = {
    "hunter_pets": [
        {
            "name": "Fang",
            "level": 80,
            "creature": {"name": "Wolf", "id": 1001},
            "creature_display": {"id": 2001},
            "slot": 0,
            "is_active": True,
            "is_summoned": True,
        },
        {
            "name": "Kralle",
            "level": 80,
            "creature": {"name": "Katze", "id": 1002},
            "creature_display": {"id": 2002},
            "slot": 1,
            "is_active": True,
        },
        # Ohne die optionalen Felder und ohne Kreaturnamen (laut Classic-Typen
        # darf er fehlen): gilt als nicht aktiv und nicht beschworen.
        {
            "name": "Stallbewohner",
            "level": 60,
            "creature": {"id": 1003},
            "creature_display": {"id": 2003},
            "slot": 5,
        },
    ]
}


def _eid(hass: HomeAssistant, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, unique_id)


async def _setup(hass: HomeAssistant, subentry):
    entry = main_entry(subentry)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _subentry(version: str, suffix: str):
    sub = character_subentry()
    sub["data"] = {**sub["data"], "game_version": version, "namespace_suffix": suffix}
    return sub


async def test_hunter_pets_retail(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/hunter-pets": HUNTER_PETS})
    entry = await _setup(hass, character_subentry())

    state = hass.states.get(_eid(hass, f"{UID1}-hunter_pets"))
    assert state.state == "3"
    assert state.attributes["friendly_name"].endswith("Hunter pets")
    assert state.attributes["summoned"] == "Fang"
    assert state.attributes["active"] == ["Fang", "Kralle"]
    assert state.attributes["pets"] == [
        {
            "name": "Fang",
            "level": 80,
            "creature": "Wolf",
            "creature_id": 1001,
            "slot": 0,
            "active": True,
            "summoned": True,
        },
        {
            "name": "Kralle",
            "level": 80,
            "creature": "Katze",
            "creature_id": 1002,
            "slot": 1,
            "active": True,
            "summoned": False,
        },
        {
            "name": "Stallbewohner",
            "level": 60,
            "creature": None,
            "creature_id": 1003,
            "slot": 5,
            "active": False,
            "summoned": False,
        },
    ]
    diag = await async_get_config_entry_diagnostics(hass, entry)
    (character,) = diag["characters"].values()
    assert character["details"]["hunter_pets"]["count"] == 3


async def test_no_sensor_for_non_hunter(hass: HomeAssistant, aioclient_mock) -> None:
    """Testchar ist Magier: Die API meldet 404 (Standard in mock_api)."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, character_subentry())

    assert _eid(hass, f"{UID1}-hunter_pets") is None
    assert _eid(hass, f"{UID1}-level")


async def test_no_sensor_when_first_query_fails(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ohne Antwort ist nicht bekannt, ob es ein Jaeger ist: kein Sensor."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/hunter-pets": 500})
    await _setup(hass, character_subentry())

    assert _eid(hass, f"{UID1}-hunter_pets") is None


@pytest.mark.parametrize(
    ("version", "suffix"),
    [
        ("classic_era", "-classic1x"),
        ("classic_progression", "-classic"),
        ("classic_anniversary", "-classicann"),
        ("forever", "-forever"),
    ],
)
async def test_hunter_pets_other_versions(
    hass: HomeAssistant, aioclient_mock, version: str, suffix: str
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/hunter-pets": HUNTER_PETS})
    await _setup(hass, _subentry(version, suffix))

    state = hass.states.get(_eid(hass, f"{UID1}-hunter_pets"))
    assert state.state == "3"
    urls = [str(call[1]) for call in aioclient_mock.mock_calls]
    assert any(
        u.startswith(f"{API}/hunter-pets?") and f"profile{suffix}-eu" in u for u in urls
    )


async def test_disabled_sensor_skips_endpoint(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/hunter-pets": HUNTER_PETS})
    entry = await _setup(hass, character_subentry())
    ent_reg = er.async_get(hass)
    ent_reg.async_update_entity(
        _eid(hass, f"{UID1}-hunter_pets"),
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    assert "hunter_pets" not in detail.needed_endpoints()
