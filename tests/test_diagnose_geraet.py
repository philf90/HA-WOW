"""Tests fuer 0.27.0: Diagnose je Geraet (E11)."""

import json

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.wow_character.const import DOMAIN
from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)

from .conftest import (
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

SECOND = "https://eu.api.blizzard.com/profile/wow/character/die-aldor/nebenchar"
UID_SECOND = "eu-profile-eu-die-aldor-nebenchar"


async def _setup(hass: HomeAssistant, aioclient_mock):
    """Zwei Charaktere auf demselben Realm, eine Spielwelt."""
    mock_token(aioclient_mock)
    aioclient_mock.get(f"{SECOND}/status", json={"id": 1, "is_valid": True})
    mock_api(aioclient_mock, {SECOND: {"name": "Nebenchar", "level": 70}})
    mock_api(aioclient_mock, base=SECOND)
    entry = main_entry(
        character_subentry(),
        character_subentry(
            UID_SECOND, "Nebenchar – Die Aldor", "die-aldor", "Nebenchar"
        ),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _device(hass: HomeAssistant, ident: str) -> dr.DeviceEntry:
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, ident)})


def _text(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


async def test_character_device(hass: HomeAssistant, aioclient_mock) -> None:
    """Nur dieser Charakter und seine Spielwelt, gekuerzt wie beim Eintrag."""
    entry = await _setup(hass, aioclient_mock)
    full = await async_get_config_entry_diagnostics(hass, entry)
    diag = await async_get_device_diagnostics(hass, entry, _device(hass, UID1))

    assert set(diag) == {"options", "character", "world"}
    character = dict(diag["character"])
    assert character.pop("title") == "Testchar – Die Aldor"
    assert character == full["characters"]["Testchar – Die Aldor"]
    assert diag["world"] == {
        "world": "eu",
        "locale": "de_DE",
        "data": full["worlds"]["eu"],
    }
    assert diag["options"] == dict(entry.options)
    text = _text(diag)
    # Der andere Charakter fehlt, ebenso die Zugangsdaten.
    assert "Nebenchar" not in text
    assert "client_secret" not in text
    assert "secret" not in text
    assert diag["character"]["profile"]["profile"]["name"] == "Testchar"


async def test_second_character_device(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    diag = await async_get_device_diagnostics(hass, entry, _device(hass, UID_SECOND))
    assert diag["character"]["title"] == "Nebenchar – Die Aldor"
    assert diag["character"]["profile"]["profile"]["level"] == 70
    assert "Testchar" not in _text(diag)


async def test_world_device(hass: HomeAssistant, aioclient_mock) -> None:
    """Nur die Spielwelt, kein Charakter."""
    entry = await _setup(hass, aioclient_mock)
    full = await async_get_config_entry_diagnostics(hass, entry)
    diag = await async_get_device_diagnostics(
        hass, entry, _device(hass, f"{entry.entry_id}-world-eu")
    )
    assert diag == {
        "options": dict(entry.options),
        "world": {"world": "eu", "locale": "de_DE", "data": full["worlds"]["eu"]},
    }
    text = _text(diag)
    assert "Testchar" not in text
    assert "Nebenchar" not in text


async def test_unknown_device(hass: HomeAssistant, aioclient_mock) -> None:
    """Geraet ohne Daten (z. B. Charakter gerade entfernt): nur die Optionen."""
    entry = await _setup(hass, aioclient_mock)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "unbekannt")}
    )
    assert await async_get_device_diagnostics(hass, entry, device) == {
        "options": dict(entry.options)
    }
