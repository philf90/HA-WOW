"""Tests fuer den Haupteintrag (API-Client) und den Untereintrag Charakter."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    BASE_INPUT,
    CHARACTER_INPUT,
    CREDENTIALS,
    MYTHIC,
    PROFILE,
    REALMS,
    REALMS_URL,
    UID1,
    character_subentry,
    main_entry,
    mock_token,
)


def _ns(namespace: str) -> dict:
    return {"namespace": namespace, "locale": "de_DE"}


def _realm_options(result) -> list:
    for key, selector in result["data_schema"].schema.items():
        if key == "realm":
            return selector.config["options"]
    raise AssertionError("kein Realm-Feld")


async def _start_main(hass: HomeAssistant, data: dict):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def _without_login(hass: HomeAssistant, result):
    """Menue nach gueltigen Zugangsdaten: ohne Battle.net-Login weiter."""
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "method"
    assert result["menu_options"] == ["login", "without_login"]
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "without_login"}
    )


async def _loaded_entry(hass: HomeAssistant, *subentries):
    entry = main_entry(*subentries)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _start_character(hass: HomeAssistant, entry, data: dict):
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "character"),
        context={"source": config_entries.SOURCE_USER},
    )
    if result["type"] is not FlowResultType.FORM:
        return result
    return await hass.config_entries.subentries.async_configure(result["flow_id"], data)


# Haupteintrag


async def test_main_entry_created(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    result = await _start_main(hass, {"client_id": " id ", "client_secret": "secret"})
    result = await _without_login(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Battle.net API"
    assert result["data"] == CREDENTIALS
    assert result["result"].unique_id == "id"
    assert result["result"].subentries == {}


async def test_main_entry_errors(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock, status=401)
    result = await _start_main(hass, CREDENTIALS)
    assert result["errors"] == {"base": "invalid_auth"}

    # Zweiter Versuch im selben Dialog, wie nach einer Fehlermeldung in der Oberflaeche.
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock, status=503)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    result = await _without_login(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_main_entry_duplicate(hass: HomeAssistant, aioclient_mock) -> None:
    main_entry().add_to_hass(hass)
    result = await _start_main(hass, CREDENTIALS)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _loaded_entry(hass)
    mock_token(aioclient_mock)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"client_id": "id", "client_secret": "neu"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["client_secret"] == "neu"


async def test_reconfigure_keeps_characters(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    entry = await _loaded_entry(hass, character_subentry())
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["sync", "credentials"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "credentials"}
    )
    assert result["step_id"] == "credentials"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"client_id": "id2", "client_secret": "neu"}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.unique_id == "id2"
    assert entry.data == {"client_id": "id2", "client_secret": "neu"}
    assert len(entry.subentries) == 1
    assert hass.states.get("sensor.testchar_die_aldor_level").state == "90"


# Untereintrag Charakter


async def test_character_retail(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, params=_ns("dynamic-eu"), json=REALMS)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    entry = await _loaded_entry(hass)

    result = await _start_character(hass, entry, BASE_INPUT)
    assert result["step_id"] == "character"
    # Alphabetisch nach Anzeigename, Wert ist der Slug der API.
    assert _realm_options(result) == [
        {"value": "aegwynn", "label": "Aegwynn"},
        {"value": "die-aldor", "label": "Die Aldor"},
        {"value": "kult-der-verdammten", "label": "Kult der Verdammten"},
    ]
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Testchar – Die Aldor"
    assert result["unique_id"] == UID1
    await hass.async_block_till_done()

    (subentry,) = entry.subentries.values()
    assert subentry.data["realm"] == "die-aldor"
    assert subentry.data["namespace_suffix"] == ""
    # Der Eintrag laedt neu und legt die Sensoren des Charakters an.
    assert hass.states.get("sensor.testchar_die_aldor_level").state == "90"
    assert hass.states.get("sensor.testchar_die_aldor_mythic_rating").state == "2512.3"


async def test_character_forever_probes_namespaces(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, params=_ns("dynamic-forever-eu"), status=404)
    aioclient_mock.get(REALMS_URL, params=_ns("dynamic-camelot-eu"), json=REALMS)
    aioclient_mock.get(API, params=_ns("profile-camelot-eu"), json=PROFILE)
    entry = await _loaded_entry(hass)

    result = await _start_character(
        hass, entry, {**BASE_INPUT, "game_version": "forever"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    (subentry,) = entry.subentries.values()
    assert subentry.data["namespace_suffix"] == "-camelot"
    # Kein Mythic+ bei Forever: Sensor wird gar nicht angelegt, kein Abruf.
    assert hass.states.get("sensor.testchar_die_aldor_mythic_rating") is None
    assert not any("mythic" in str(call[1]) for call in aioclient_mock.mock_calls)


async def test_character_errors(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    entry = await _loaded_entry(hass)

    aioclient_mock.get(REALMS_URL, json={"realms": []})
    result = await _start_character(hass, entry, BASE_INPUT)
    assert result["errors"] == {"base": "realms_not_found"}

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, status=503)
    result = await _start_character(hass, entry, BASE_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, json=REALMS)
    aioclient_mock.get(API, status=404)
    result = await _start_character(hass, entry, BASE_INPUT)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["step_id"] == "character"
    assert result["errors"] == {"base": "character_not_found"}
    # Realm-Liste bleibt fuer den naechsten Versuch erhalten.
    assert len(_realm_options(result)) == 3


async def test_character_duplicate(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, json=REALMS)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    entry = await _loaded_entry(hass, character_subentry())

    result = await _start_character(hass, entry, BASE_INPUT)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**CHARACTER_INPUT, "character": "TESTCHAR"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_character_entry_not_loaded(hass: HomeAssistant) -> None:
    entry = main_entry()
    entry.add_to_hass(hass)
    result = await _start_character(hass, entry, BASE_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"
