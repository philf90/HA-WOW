"""Tests fuer 0.17.2: Start ohne Netz, Mythic+-Ausfall, Client-ID-Wechsel, Forever."""

from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import (
    API,
    BASE_INPUT,
    CHARACTER_INPUT,
    GAME,
    PROFILE,
    REALMS,
    REALMS_URL,
    TOKEN_URL,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

LEVEL = "sensor.testchar_die_aldor_level"
RATING = "sensor.testchar_die_aldor_mythic_rating"
# Entitaeten, die nur aus der ersten Antwort entstehen, und die Realm-Entitaeten.
FROM_FIRST_ANSWER = (
    ("sensor", f"{UID1}-profession-164"),
    ("sensor", f"{UID1}-pvp_bracket_3v3"),
    ("binary_sensor", "id-world-eu-realm-die-aldor-status"),
    ("binary_sensor", "id-world-eu-realm-die-aldor-queue"),
    ("sensor", "id-world-eu-realm-die-aldor-population"),
)


async def _setup(hass: HomeAssistant, *subentries):
    entry = main_entry(*subentries)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, "wow_character", unique_id)


async def test_start_without_network_retries(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Kein Token beim Start: Home Assistant wiederholt den Start, danach
    entstehen auch die Entitaeten, die nur aus der ersten Antwort kommen."""
    aioclient_mock.post(TOKEN_URL, status=503)
    entry = await _setup(hass, character_subentry())
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10))
    # Der erneute Start laeuft als Hintergrundaufgabe.
    await hass.async_block_till_done(wait_background_tasks=True)

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert hass.states.get(LEVEL).state == "90"
    for platform, unique_id in FROM_FIRST_ANSWER:
        assert _entity_id(hass, platform, unique_id), unique_id


async def test_retail_realm_without_first_answer(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Retail: Realm-Entitaeten entstehen auch, wenn der Realm beim Start fehlt."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/realm/die-aldor": 500})
    await _setup(hass, character_subentry())

    for platform, unique_id in FROM_FIRST_ANSWER[2:]:
        entity_id = _entity_id(hass, platform, unique_id)
        assert entity_id, unique_id
        assert hass.states.get(entity_id).state == "unknown"


async def test_mythic_error_keeps_profile(hass: HomeAssistant, aioclient_mock) -> None:
    """Scheitert nur das Mythic+-Profil, bleiben die Profil-Sensoren verfuegbar."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/mythic-keystone-profile": 500})
    await _setup(hass, character_subentry())

    assert hass.states.get(LEVEL).state == "90"
    assert hass.states.get(RATING).state == "unknown"


async def test_mythic_error_keeps_last_rating(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Spaeterer Mythic+-Fehler: Wertung behaelt den letzten Stand."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    assert hass.states.get(RATING).state == "2512.3"

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/mythic-keystone-profile": 500})
    (coordinator,) = entry.runtime_data.coordinators.values()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success
    assert hass.states.get(LEVEL).state == "90"
    assert hass.states.get(RATING).state == "2512.3"


@pytest.mark.parametrize("source", ["reconfigure", "reauth"])
async def test_new_client_id_keeps_world_entities(
    hass: HomeAssistant, aioclient_mock, source: str
) -> None:
    """Neue Client-ID: Spielwelt-Entitaeten behalten ihre IDs, kein "_2"."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    ent_reg = er.async_get(hass)

    def world() -> dict[str, str]:
        return {
            e.entity_id: e.unique_id
            for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
            if "-world-" in e.unique_id
        }

    before = world()
    assert len(before) == 5

    if source == "reconfigure":
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "credentials"}
        )
    else:
        result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"client_id": "id2", "client_secret": "neu"}
    )
    assert result["type"] is FlowResultType.ABORT
    await hass.async_block_till_done()

    after = world()
    assert entry.unique_id == "id2"
    assert set(after) == set(before)
    assert all(uid.startswith("id2-world-") for uid in after.values())
    assert hass.states.get("sensor.wow_world_eu_wow_token").state == "345"


async def test_back_to_earlier_client_id(hass: HomeAssistant, aioclient_mock) -> None:
    """Rueckwechsel auf eine Client-ID mit verwaisten Entitaeten aus 0.17.1:
    kein Fehler, Home Assistant uebernimmt die vorhandene Entitaet."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    ent_reg = er.async_get(hass)
    # Verwaist aus einem frueheren Wechsel, mit der unique_id der neuen Client-ID.
    stale = ent_reg.async_get_or_create(
        "sensor",
        "wow_character",
        "id2-world-eu-token",
        config_entry=entry,
        suggested_object_id="alte_wow_marke",
    )

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "credentials"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"client_id": "id2", "client_secret": "neu"}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert hass.states.get(stale.entity_id).state == "345"
    # Die uebrigen Spielwelt-Entitaeten behalten ihre IDs.
    assert hass.states.get("sensor.wow_world_eu_weekly_reset") is not None
    assert not [
        e.entity_id
        for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if "-world-" in e.unique_id and e.entity_id.endswith("_2")
    ]


async def _forever_flow(hass: HomeAssistant, entry):
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "character"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**BASE_INPUT, "game_version": "forever"}
    )


async def test_forever_skips_forbidden_namespace(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """HTTP 403 fuer den ersten Kandidaten: der naechste wird probiert."""
    mock_token(aioclient_mock)
    ns = {"locale": "de_DE"}
    aioclient_mock.get(
        REALMS_URL, params={**ns, "namespace": "dynamic-forever-eu"}, status=403
    )
    aioclient_mock.get(
        REALMS_URL, params={**ns, "namespace": "dynamic-camelot-eu"}, json=REALMS
    )
    aioclient_mock.get(
        API, params={**ns, "namespace": "profile-camelot-eu"}, json=PROFILE
    )
    entry = await _setup(hass)

    result = await _forever_flow(hass, entry)
    assert result["step_id"] == "character"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    (subentry,) = entry.subentries.values()
    assert subentry.data["namespace_suffix"] == "-camelot"


async def test_forever_all_forbidden(hass: HomeAssistant, aioclient_mock) -> None:
    """Alle Kandidaten mit 403: Hinweis "keine Realm-Liste" statt Verbindungsfehler."""
    mock_token(aioclient_mock)
    ns = {"locale": "de_DE"}
    for suffix in ("-forever", "-camelot"):
        aioclient_mock.get(
            REALMS_URL, params={**ns, "namespace": f"dynamic{suffix}-eu"}, status=403
        )
    entry = await _setup(hass)

    result = await _forever_flow(hass, entry)
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "realms_not_found"}
