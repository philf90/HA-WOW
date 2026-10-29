"""Tests fuer 0.21.0: Aktionen refresh und get_character."""

import json
from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wow_character import services
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    CREDENTIALS,
    MEDIA,
    MYTHIC,
    PROFILE,
    REALMS,
    REALMS_URL,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

BASE = Path(__file__).parents[1] / "custom_components" / "wow_character"
# Zweiter Charakter auf demselben Realm, damit die Spielwelt-Mocks passen.
API_B = "https://eu.api.blizzard.com/profile/wow/character/die-aldor/zweitchar"
UID_B = "eu-profile-eu-die-aldor-zweitchar"
# Nicht eingerichteter Charakter fuer get_character
FRIEND = (
    "https://eu.api.blizzard.com/profile/wow/character/kult-der-verdammten/freundin"
)
FRIEND_PROFILE = {
    **PROFILE,
    "id": 4711,
    "name": "Freundin",
    "level": 80,
    "realm": {"name": "Kult der Verdammten"},
    "guild": None,
}


def _calls(aioclient_mock, part: str) -> int:
    return sum(1 for call in aioclient_mock.mock_calls if part in str(call[1]))


def _mock_all(aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(f"{API_B}/status", json={"id": 2, "is_valid": True})
    mock_api(aioclient_mock)
    mock_api(aioclient_mock, base=API_B)


async def _setup(hass: HomeAssistant, *subentries):
    entry = main_entry(*(subentries or (character_subentry(),)))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _device(hass: HomeAssistant, ident: str) -> str:
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, ident)})
    assert device is not None, ident
    return device.id


async def _refresh(hass: HomeAssistant, data: dict | None = None) -> None:
    await hass.services.async_call(DOMAIN, "refresh", data or {}, blocking=True)
    await hass.async_block_till_done()


# refresh


@pytest.mark.parametrize("data", [{}, {"device_id": []}])
async def test_refresh_all_queries_everything_now(
    hass: HomeAssistant, aioclient_mock, data
) -> None:
    """Ohne Geraet: alle Charaktere, auch Endpunkte im seltenen Takt."""
    _mock_all(aioclient_mock)
    await _setup(
        hass,
        character_subentry(),
        character_subentry(UID_B, "Zweitchar – Die Aldor", character="Zweitchar"),
    )
    aioclient_mock.clear_requests()
    _mock_all(aioclient_mock)
    await _refresh(hass, data)
    for base in (API, API_B):
        assert _calls(aioclient_mock, f"{base}?") == 1  # Profil
        assert _calls(aioclient_mock, f"{base}/encounters/raids") == 1  # 60 min
        assert _calls(aioclient_mock, f"{base}/professions") == 1  # 6 h
        assert _calls(aioclient_mock, f"{base}/pvp-bracket/2v2") == 1  # ohne Sensor
    # Die Spielwelt nur auf Wunsch
    assert _calls(aioclient_mock, "/token/index") == 0


async def test_refresh_selected_character_only(
    hass: HomeAssistant, aioclient_mock
) -> None:
    _mock_all(aioclient_mock)
    await _setup(
        hass,
        character_subentry(),
        character_subentry(UID_B, "Zweitchar – Die Aldor", character="Zweitchar"),
    )
    aioclient_mock.clear_requests()
    _mock_all(aioclient_mock)
    await _refresh(hass, {"device_id": _device(hass, UID_B)})
    assert _calls(aioclient_mock, f"{API_B}/professions") == 1
    assert _calls(aioclient_mock, API + "?") == 0
    assert _calls(aioclient_mock, f"{API}/") == 0


async def test_refresh_world_device(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_all(aioclient_mock)
    entry = await _setup(hass)
    aioclient_mock.clear_requests()
    _mock_all(aioclient_mock)
    await _refresh(hass, {"device_id": [_device(hass, f"{entry.entry_id}-world-eu")]})
    assert _calls(aioclient_mock, "/token/index") == 1
    assert _calls(aioclient_mock, "/mythic-keystone/season/index") == 1
    assert _calls(aioclient_mock, API) == 0


async def test_refresh_unknown_device(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_all(aioclient_mock)
    await _setup(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _refresh(hass, {"device_id": "gibt-es-nicht"})
    assert err.value.translation_key == "device_not_found"


async def test_refresh_reports_failure(hass: HomeAssistant, aioclient_mock) -> None:
    """Scheitert die Abfrage, meldet die Aktion den Charakter als Fehler."""
    _mock_all(aioclient_mock)
    await _setup(hass)
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: 500})
    with pytest.raises(HomeAssistantError) as err:
        await _refresh(hass)
    assert err.value.translation_key == "refresh_failed"
    assert err.value.translation_placeholders == {"names": "Testchar – Die Aldor"}


async def test_refresh_entry_not_loaded(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_all(aioclient_mock)
    entry = await _setup(hass)
    device_id = _device(hass, UID1)
    await hass.config_entries.async_unload(entry.entry_id)
    for data in ({}, {"device_id": device_id}):
        with pytest.raises(ServiceValidationError) as err:
            await _refresh(hass, data)
        assert err.value.translation_key == "not_loaded"


# get_character


def _mock_friend(aioclient_mock, mythic=MYTHIC) -> None:
    aioclient_mock.get(REALMS_URL, json=REALMS)
    aioclient_mock.get(FRIEND, json=FRIEND_PROFILE)
    if isinstance(mythic, int):
        aioclient_mock.get(f"{FRIEND}/mythic-keystone-profile", status=mythic)
    else:
        aioclient_mock.get(f"{FRIEND}/mythic-keystone-profile", json=mythic)
    aioclient_mock.get(f"{FRIEND}/character-media", json=MEDIA)


async def _lookup(hass: HomeAssistant, **data) -> dict:
    return await hass.services.async_call(
        DOMAIN,
        "get_character",
        {"region": "eu", "realm": "Kult der Verdammten", "character": "Freundin"}
        | data,
        blocking=True,
        return_response=True,
    )


async def test_get_character(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_all(aioclient_mock)
    _mock_friend(aioclient_mock)
    entry = await _setup(hass)
    response = await _lookup(hass)
    assert response == {
        "name": "Freundin",
        "id": 4711,
        "realm": "Kult der Verdammten",
        "realm_slug": "kult-der-verdammten",
        "region": "eu",
        "game_version": "retail",
        "level": 80,
        "class": "Magier",
        "spec": "Frost",
        "race": "Mensch",
        "faction": "Allianz",
        "guild": None,
        "title": "Freundin der Champion",
        "achievement_points": 12345,
        "equipped_item_level": 701,
        "average_item_level": 703,
        "last_login": "2025-10-25T13:46:40+00:00",
        "mythic_rating": 2512.3,
        "avatar": "https://render.example/avatar.jpg",
    }
    # Nicht eingerichtet: kein neuer Charakter, kein Geraet
    assert len(entry.subentries) == 1
    assert (
        dr.async_get(hass).async_get_device(
            identifiers={(DOMAIN, "eu-profile-eu-kult-der-verdammten-freundin")}
        )
        is None
    )
    # Antwort muss sich als JSON speichern lassen (response_variable)
    json.dumps(response)


async def test_get_character_realm_by_slug_and_cached(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Slug in beliebiger Schreibweise; die Realm-Liste kommt nur einmal."""
    _mock_all(aioclient_mock)
    _mock_friend(aioclient_mock)
    await _setup(hass)
    await _lookup(hass, realm="KULT-der-verdammten")
    await _lookup(hass, realm="kult der verdammten")
    assert _calls(aioclient_mock, "/realm/index") == 1


async def test_get_character_without_mythic_run(
    hass: HomeAssistant, aioclient_mock
) -> None:
    _mock_all(aioclient_mock)
    _mock_friend(aioclient_mock, mythic=404)
    await _setup(hass)
    assert (await _lookup(hass))["mythic_rating"] is None


async def test_get_character_classic_skips_mythic(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Gleiche Adressen wie Retail, aber Namespace classic1x und ohne Mythic+."""
    _mock_all(aioclient_mock)
    await _setup(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(REALMS_URL, json=REALMS)
    aioclient_mock.get(FRIEND, json=FRIEND_PROFILE)
    aioclient_mock.get(f"{FRIEND}/character-media", status=404)
    response = await _lookup(hass, game_version="classic_era")
    assert response["mythic_rating"] is None
    assert response["avatar"] is None
    assert _calls(aioclient_mock, "mythic-keystone") == 0
    namespaces = {call[1].query.get("namespace") for call in aioclient_mock.mock_calls}
    assert namespaces == {"dynamic-classic1x-eu", "profile-classic1x-eu"}


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"realm": "Gibt es nicht"}, "realm_not_found"),
        ({"character": "Niemand"}, "lookup_not_found"),
    ],
)
async def test_get_character_not_found(
    hass: HomeAssistant, aioclient_mock, data, key
) -> None:
    _mock_all(aioclient_mock)
    _mock_friend(aioclient_mock)
    aioclient_mock.get(
        "https://eu.api.blizzard.com/profile/wow/character/kult-der-verdammten/niemand",
        status=404,
    )
    await _setup(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _lookup(hass, **data)
    assert err.value.translation_key == key


async def test_get_character_api_error(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_all(aioclient_mock)
    aioclient_mock.get(REALMS_URL, json=REALMS)
    aioclient_mock.get(FRIEND, status=500)
    await _setup(hass)
    with pytest.raises(HomeAssistantError) as err:
        await _lookup(hass)
    assert err.value.translation_key == "update_failed"


async def test_get_character_choose_entry(hass: HomeAssistant, aioclient_mock) -> None:
    """Mit mehreren Eintraegen muss der API-Client gewaehlt werden."""
    _mock_all(aioclient_mock)
    _mock_friend(aioclient_mock)
    first = await _setup(hass)
    second = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Battle.net API",
        unique_id="id2",
        data={**CREDENTIALS, "client_id": "id2"},
    )
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await _lookup(hass)
    assert err.value.translation_key == "entry_required"
    assert (await _lookup(hass, config_entry_id=first.entry_id))["level"] == 80
    with pytest.raises(ServiceValidationError) as err:
        await _lookup(hass, config_entry_id="gibt-es-nicht")
    assert err.value.translation_key == "entry_not_found"


# Beschreibung der Aktionen


@pytest.mark.parametrize("path", ["strings.json", "translations/de.json"])
def test_services_described_and_translated(path: str) -> None:
    """services.yaml, Schemas und Uebersetzungen nennen dieselben Felder."""
    described = yaml.safe_load((BASE / "services.yaml").read_text())
    strings = json.loads((BASE / path).read_text(encoding="utf-8"))
    schemas = {
        "refresh": services.REFRESH_SCHEMA,
        "get_character": services.GET_CHARACTER_SCHEMA,
    }
    assert set(described) == set(schemas) == set(strings["services"])
    for name, schema in schemas.items():
        fields = {str(key) for key in schema.schema}
        assert set(described[name]["fields"]) == fields, name
        assert set(strings["services"][name]["fields"]) == fields, name
    # Auswahllisten mit denselben Optionen wie die Schemas
    get = described["get_character"]["fields"]
    for field in ("region", "game_version"):
        options = get[field]["selector"]["select"]["options"]
        assert options == list(schemas["get_character"].schema[field].container)
    for key in ("not_loaded", "device_not_found", "refresh_failed", "realm_not_found"):
        assert key in strings["exceptions"]
