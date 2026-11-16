"""Tests fuer 0.35.0: WoW-Forever-Charaktere ohne Realm.

Grundlage ist der Live-Aufruf von probe_namespaces am 16.11.2026: Profil im
Namespace profile-forever-{region} unter /profile/wow/character/{kennung},
keine Realm-Liste (dynamic-forever 404), Felder name, surname, name_search und
ruleset. Der Charakter hier ist erfunden.
"""

import pytest
from homeassistant import config_entries
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.wow_character import parsers as p
from custom_components.wow_character.api import BattleNetClient, character_key
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    PROFILE,
    REALMS,
    REALMS_URL,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

CHAR = "https://eu.api.blizzard.com/profile/wow/character"
FOREVER_API = f"{CHAR}/testa-beispiel"
FOREVER_UID = "eu-profile-forever-eu-testa-beispiel"
# Felder wie in der Live-Antwort vom 16.11.2026; ohne realm, guild,
# active_spec und active_title.
FOREVER_PROFILE = {
    key: value
    for key, value in PROFILE.items()
    if key not in ("realm", "guild", "active_spec", "active_title")
} | {
    "id": 4242,
    "name": "Testa",
    "surname": "Beispiel",
    "name_search": "Testa Beispiel",
    "ruleset": {"id": 2, "name": "Normal"},
    "is_remix": False,
}
FOREVER_INPUT = {"region": "eu", "game_version": "forever"}


def forever_subentry(character_id: int | None = None):
    sub = character_subentry(
        FOREVER_UID, "Testa Beispiel – Normal", "", "testa-beispiel"
    )
    sub["data"] = {
        **sub["data"],
        "game_version": "forever",
        "namespace_suffix": "-forever",
    }
    if character_id is not None:
        sub["data"]["character_id"] = character_id
    return sub


def _mock_forever(aioclient_mock, profile: dict | None = None, base=FOREVER_API):
    mock_api(aioclient_mock, {base: profile or FOREVER_PROFILE}, base)
    aioclient_mock.get(f"{base}/status", json={"id": 4242, "is_valid": True})


async def _loaded(hass: HomeAssistant, aioclient_mock, *subentries):
    mock_token(aioclient_mock)
    entry = main_entry(*subentries)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _manual(hass: HomeAssistant, entry):
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "character"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], FOREVER_INPUT
    )


def _calls(aioclient_mock, part: str) -> list[str]:
    return [str(c[1]) for c in aioclient_mock.mock_calls if part in str(c[1])]


def _entity(hass: HomeAssistant, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


# Helfer


def test_character_key() -> None:
    assert character_key(" Testa  Beispiel ") == "testa-beispiel"
    assert character_key("testa-beispiel") == "testa-beispiel"
    assert character_key("Testa-Beispiel") == "testa-beispiel"
    # Umlaute bleiben; wie Blizzard sie schreibt, ist nicht belegt
    assert character_key("Jörg Müller") == "jörg-müller"


def test_path_without_realm() -> None:
    path = BattleNetClient._character_path
    assert path("", "testa-beispiel") == "/profile/wow/character/testa-beispiel"
    assert path("die-aldor", "Testchar") == "/profile/wow/character/die-aldor/testchar"


def test_title() -> None:
    assert p.character_title(FOREVER_PROFILE, "testa-beispiel", None) == (
        "Testa Beispiel – Normal"
    )
    # Ohne Nachname und Regelsatz: name_search, sonst die Kennung
    assert p.character_title({"name_search": "Testa B"}, "x", "") == "Testa B"
    assert p.character_title({}, "testa-beispiel", None) == "testa-beispiel"
    # Mit Realm wie bisher
    assert p.character_title(PROFILE, "Testchar", "Die Aldor") == (
        "Testchar – Die Aldor"
    )


# Hinzufuegen von Hand


@pytest.mark.parametrize("typed", [" Testa  Beispiel ", "testa-beispiel"])
async def test_add_forever_character(
    hass: HomeAssistant, aioclient_mock, typed: str
) -> None:
    """Kein Realm: Name genuegt, Kennung daraus, Titel mit Regelsatz."""
    entry = await _loaded(hass, aioclient_mock)
    _mock_forever(aioclient_mock)

    result = await _manual(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "character_no_realm"
    assert [str(key) for key in result["data_schema"].schema] == ["character"]
    assert not _calls(aioclient_mock, "realm/index")

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"character": typed}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    (subentry,) = entry.subentries.values()
    assert subentry.title == "Testa Beispiel – Normal"
    assert subentry.unique_id == FOREVER_UID
    assert dict(subentry.data) == {
        "region": "eu",
        "game_version": "forever",
        "realm": "",
        "character": "testa-beispiel",
        "namespace_suffix": "-forever",
        "character_id": 4242,
    }
    # Abfragen ohne Realm im Pfad, im Namespace profile-forever-eu
    profile_calls = _calls(aioclient_mock, "/profile/wow/character/")
    assert profile_calls
    assert all(c.startswith(FOREVER_API) for c in profile_calls)
    assert all("namespace=profile-forever-eu" in c for c in profile_calls)
    assert not _calls(aioclient_mock, "realm/index")

    level = _entity(hass, "sensor", f"{FOREVER_UID}-level")
    state = hass.states.get(level)
    assert state.state == "90"
    assert state.attributes["ruleset"] == "Normal"
    assert state.attributes["surname"] == "Beispiel"
    assert state.attributes["realm"] is None
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, FOREVER_UID)})
    assert device.name == "Testa Beispiel – Normal"
    assert device.model == "World of Warcraft Forever"
    # Keine Spielwelt fuer Forever
    assert not [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if "-world-" in e.unique_id
    ]
    assert entry.runtime_data.worlds == {}


@pytest.mark.parametrize(
    ("typed", "answer", "error"),
    [
        ("testa/beispiel", None, "invalid_character"),
        ("Testa Beispiel", 404, "character_not_found"),
        ("Testa Beispiel", 503, "cannot_connect"),
    ],
)
async def test_add_forever_errors(
    hass: HomeAssistant, aioclient_mock, typed, answer, error
) -> None:
    entry = await _loaded(hass, aioclient_mock)
    if answer is not None:
        aioclient_mock.get(FOREVER_API, status=answer)
    result = await _manual(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"character": typed}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "character_no_realm"
    assert result["errors"] == {"base": error}
    if answer is None:
        assert not _calls(aioclient_mock, "/profile/wow/character/")


async def test_add_forever_twice(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_forever(aioclient_mock)
    entry = await _loaded(hass, aioclient_mock, forever_subentry(4242))
    result = await _manual(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"character": "Testa Beispiel"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_retail_and_forever_side_by_side(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Spielwelt nur fuer Retail; die Retail-Pfade behalten den Realm."""
    mock_api(aioclient_mock)
    _mock_forever(aioclient_mock)
    entry = await _loaded(
        hass, aioclient_mock, character_subentry(), forever_subentry(4242)
    )
    assert set(entry.runtime_data.worlds) == {("eu", "")}
    assert _entity(hass, "sensor", f"{UID1}-level")
    assert _entity(hass, "sensor", f"{FOREVER_UID}-level")
    assert _calls(aioclient_mock, f"{CHAR}/die-aldor/testchar")


# Neu konfigurieren und Reparatur


async def test_reconfigure_forever(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_forever(aioclient_mock)
    entry = await _loaded(hass, aioclient_mock, forever_subentry(4242))
    (subentry_id,) = entry.subentries
    level = _entity(hass, "sensor", f"{FOREVER_UID}-level")

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    assert result["step_id"] == "reconfigure_no_realm"
    defaults = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
    }
    assert defaults == {"character": "testa-beispiel"}

    renamed = f"{CHAR}/testa-neuname"
    _mock_forever(
        aioclient_mock, {**FOREVER_PROFILE, "surname": "Neuname"}, base=renamed
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"character": "Testa Neuname"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    subentry = entry.subentries[subentry_id]
    assert subentry.title == "Testa Neuname – Normal"
    assert subentry.data["character"] == "testa-neuname"
    assert subentry.data["realm"] == ""
    # Gleiche Entitaet, kein Abruf der Realm-Liste
    assert _entity(hass, "sensor", f"{FOREVER_UID}-level") == level
    assert not _calls(aioclient_mock, "realm/index")


async def test_repair_forever(hass: HomeAssistant, aioclient_mock) -> None:
    """Anderer Charakter unter der Kennung: Reparatur nur mit dem Namen."""
    assert await async_setup_component(hass, "repairs", {})
    _mock_forever(aioclient_mock, {**FOREVER_PROFILE, "id": 99})
    aioclient_mock.get(REALMS_URL, json=REALMS)
    entry = await _loaded(hass, aioclient_mock, forever_subentry(4242))
    (subentry_id,) = entry.subentries
    issue = f"character_{subentry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue)

    manager = repairs_flow_manager(hass)
    result = await manager.async_init(DOMAIN, data={"issue_id": issue})
    result = await manager.async_configure(
        result["flow_id"], {"next_step_id": "character"}
    )
    assert result["step_id"] == "character_no_realm"
    defaults = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
    }
    assert defaults == {"character": "testa-beispiel"}

    result = await manager.async_configure(result["flow_id"], {"character": "a/b"})
    assert result["errors"] == {"base": "invalid_character"}
    # Derselbe Name uebernimmt den aktuellen Charakter (ID 99)
    result = await manager.async_configure(
        result["flow_id"], {"character": "Testa Beispiel"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    subentry = entry.subentries[subentry_id]
    assert subentry.data["character_id"] == 99
    assert subentry.title == "Testa Beispiel – Normal"
    assert not _calls(aioclient_mock, "realm/index")


# Aktion get_character


async def _lookup(hass: HomeAssistant, **data) -> dict:
    return await hass.services.async_call(
        DOMAIN,
        "get_character",
        {"region": "eu", **data},
        blocking=True,
        return_response=True,
    )


async def test_get_character_forever(hass: HomeAssistant, aioclient_mock) -> None:
    mock_api(aioclient_mock)
    await _loaded(hass, aioclient_mock, character_subentry())
    _mock_forever(aioclient_mock)

    response = await _lookup(hass, game_version="forever", character=" Testa Beispiel ")
    assert response["name"] == "Testa"
    assert response["surname"] == "Beispiel"
    assert response["ruleset"] == "Normal"
    assert response["realm"] is None
    assert response["realm_slug"] is None
    assert response["game_version"] == "forever"
    assert response["mythic_rating"] is None
    assert not _calls(aioclient_mock, "realm/index")

    # Ein Realm wird bei Forever nicht beachtet
    response = await _lookup(
        hass, game_version="forever", realm="Egal", character="testa-beispiel"
    )
    assert response["surname"] == "Beispiel"

    with pytest.raises(ServiceValidationError) as err:
        await _lookup(hass, game_version="forever", character="a/b")
    assert err.value.translation_key == "invalid_character"

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    aioclient_mock.get(FOREVER_API, status=404)
    with pytest.raises(ServiceValidationError) as err:
        await _lookup(hass, game_version="forever", character="Testa Beispiel")
    assert err.value.translation_key == "lookup_not_found"
    assert err.value.translation_placeholders == {"character": "testa-beispiel"}


async def test_get_character_realm_required(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ausser bei Forever bleibt der Realm Pflicht."""
    mock_api(aioclient_mock)
    await _loaded(hass, aioclient_mock, character_subentry())
    with pytest.raises(ServiceValidationError) as err:
        await _lookup(hass, character="Testchar")
    assert err.value.translation_key == "realm_required"
