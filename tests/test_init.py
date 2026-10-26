"""Tests fuer Einrichtungsdialog und Sensoren."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    CHARACTER_INPUT,
    MYTHIC,
    PROFILE,
    REALMS,
    REALMS_URL,
    USER_INPUT,
    mock_token,
)


def _ns(namespace: str) -> dict:
    return {"namespace": namespace, "locale": "de_DE"}


async def _start(hass: HomeAssistant, data: dict):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


def _realm_options(result) -> list:
    for key, selector in result["data_schema"].schema.items():
        if key == "realm":
            return selector.config["options"]
    raise AssertionError("kein Realm-Feld")


async def test_flow_retail(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, params=_ns("dynamic-eu"), json=REALMS)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)

    result = await _start(hass, USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "character"
    # Alphabetisch nach Anzeigename, Wert ist der Slug der API.
    assert _realm_options(result) == [
        {"value": "aegwynn", "label": "Aegwynn"},
        {"value": "die-aldor", "label": "Die Aldor"},
        {"value": "kult-der-verdammten", "label": "Kult der Verdammten"},
    ]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Testchar – Die Aldor"
    assert result["data"]["realm"] == "die-aldor"
    assert result["data"]["namespace_suffix"] == ""
    # Profilabruf mit Namespace und Sprache.
    _, url, _, _ = aioclient_mock.mock_calls[2]
    assert url.path == "/profile/wow/character/die-aldor/testchar"
    assert url.query["namespace"] == "profile-eu"
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testchar_die_aldor_level").state == "90"
    assert hass.states.get("sensor.testchar_die_aldor_item_level").state == "701"
    assert hass.states.get("sensor.testchar_die_aldor_mythic_rating").state == "2512.3"
    assert (
        hass.states.get("sensor.testchar_die_aldor_last_login").state
        == "2025-10-25T13:46:40+00:00"
    )
    attrs = hass.states.get("sensor.testchar_die_aldor_level").attributes
    assert attrs["class"] == "Magier"
    assert attrs["guild"] == "Testgilde"


async def test_flow_forever_probes_namespaces(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    # Erster Kandidat ohne Realm-Liste, zweiter liefert sie.
    aioclient_mock.get(REALMS_URL, params=_ns("dynamic-forever-eu"), status=404)
    aioclient_mock.get(REALMS_URL, params=_ns("dynamic-camelot-eu"), json=REALMS)
    aioclient_mock.get(API, params=_ns("profile-camelot-eu"), json=PROFILE)

    result = await _start(hass, {**USER_INPUT, "game_version": "forever"})
    assert result["step_id"] == "character"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["namespace_suffix"] == "-camelot"
    await hass.async_block_till_done()

    # Kein Mythic+ bei Forever: Sensor wird gar nicht angelegt, kein Abruf.
    assert hass.states.get("sensor.testchar_die_aldor_mythic_rating") is None
    assert not any("mythic" in str(call[1]) for call in aioclient_mock.mock_calls)
    assert hass.states.get("sensor.testchar_die_aldor_level").state == "90"


async def test_flow_errors_step_user(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock, status=401)
    result = await _start(hass, USER_INPUT)
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, status=503)
    result = await _start(hass, USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, json={"realms": []})
    result = await _start(hass, USER_INPUT)
    assert result["errors"] == {"base": "realms_not_found"}

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, status=404)
    result = await _start(hass, {**USER_INPUT, "game_version": "forever"})
    assert result["errors"] == {"base": "realms_not_found"}


async def test_flow_character_not_found(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, json=REALMS)
    aioclient_mock.get(API, status=404)

    result = await _start(hass, USER_INPUT)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "character"
    assert result["errors"] == {"base": "character_not_found"}
    # Realm-Liste bleibt fuer den naechsten Versuch erhalten.
    assert len(_realm_options(result)) == 3


async def test_no_mythic_runs_and_duplicate(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, json=REALMS)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", status=404)

    result = await _start(hass, USER_INPUT)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    # Ohne M+-Lauf: Sensor existiert, Wert unbekannt statt Fehler.
    assert hass.states.get("sensor.testchar_die_aldor_mythic_rating").state == "unknown"

    result = await _start(hass, USER_INPUT)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CHARACTER_INPUT, "character": "TESTCHAR"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_update_failure_marks_unavailable(
    hass: HomeAssistant, aioclient_mock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="eu-profile-eu-die-aldor-testchar",
        title="Testchar – Die Aldor",
        data={**USER_INPUT, **CHARACTER_INPUT, "namespace_suffix": ""},
    )
    entry.add_to_hass(hass)
    mock_token(aioclient_mock)
    aioclient_mock.get(API, status=500)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY
