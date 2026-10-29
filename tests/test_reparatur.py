"""Tests fuer Charakter-Status, Reparaturhinweise, Neu konfigurieren und Aufraeumen."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

import custom_components.wow_character as wow
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    PROFILE,
    REALMS,
    REALMS_URL,
    UID1,
    UID2,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

NEW_API = "https://eu.api.blizzard.com/profile/wow/character/die-aldor/neuname"
LEVEL = "sensor.testchar_die_aldor_level"


async def _setup(hass: HomeAssistant, *subentries):
    entry = main_entry(*(subentries or (character_subentry(),)))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _issue(hass: HomeAssistant, entry) -> ir.IssueEntry | None:
    (subentry_id,) = entry.subentries
    return ir.async_get(hass).async_get_issue(DOMAIN, f"character_{subentry_id}")


async def test_character_id_recorded_without_reload(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Charaktere aus aelteren Versionen bekommen ihre ID ohne Neuladen."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: {**PROFILE, "id": 42}})
    starts = []
    setup_entry = wow.async_setup_entry

    async def counting(hass: HomeAssistant, entry) -> bool:
        starts.append(entry.entry_id)
        return await setup_entry(hass, entry)

    # Gezaehlt statt runtime_data verglichen: Ein Neuladen ist vor dem
    # Vergleich schon durch (bis 0.17.1 unbemerkt doppelt gestartet).
    with patch.object(wow, "async_setup_entry", counting):
        entry = await _setup(hass)
        await hass.async_block_till_done()

    (subentry,) = entry.subentries.values()
    assert subentry.data["character_id"] == 42
    assert len(starts) == 1
    assert hass.states.get(LEVEL).state == "90"
    assert _issue(hass, entry) is None


async def test_changed_id_creates_issue(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: {**PROFILE, "id": 99}})
    sub = character_subentry()
    sub["data"] = {**sub["data"], "character_id": 42}
    entry = await _setup(hass, sub)

    assert hass.states.get(LEVEL).state == "unavailable"
    issue = _issue(hass, entry)
    assert issue.translation_key == "character_changed"
    assert issue.translation_placeholders == {"character": "Testchar – Die Aldor"}


async def test_not_found_issue_after_limit_and_cleared(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: 404})
    entry = await _setup(hass)
    coordinator = next(iter(entry.runtime_data.coordinators.values()))

    # Erste und zweite 404: noch kein Hinweis
    assert _issue(hass, entry) is None
    await coordinator.async_refresh()
    assert _issue(hass, entry) is None
    await coordinator.async_refresh()
    assert _issue(hass, entry).translation_key == "character_not_found"
    assert hass.states.get(LEVEL).state == "unavailable"

    # Charakter wieder da: Hinweis verschwindet, Werte kommen zurueck
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _issue(hass, entry) is None
    assert hass.states.get(LEVEL).state == "90"


async def test_invalid_status_creates_issue(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock, valid=False)
    mock_api(aioclient_mock)
    entry = await _setup(hass)

    assert hass.states.get(LEVEL).state == "unavailable"
    assert _issue(hass, entry).translation_key == "character_invalid"


async def test_status_error_keeps_values(hass: HomeAssistant, aioclient_mock) -> None:
    """Faellt nur der Status-Endpunkt aus, bleiben die Werte sichtbar."""
    # Vor mock_token registriert: Der erste passende Mock gewinnt.
    aioclient_mock.get(f"{API}/status", status=500)
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)

    assert hass.states.get(LEVEL).state == "90"
    assert _issue(hass, entry) is None


async def _start_reconfigure(hass: HomeAssistant, entry):
    (subentry_id,) = [
        sid for sid, sub in entry.subentries.items() if sub.unique_id == UID1
    ]
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "character"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry_id,
        },
    )


async def test_reconfigure_character_keeps_entities(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    aioclient_mock.get(
        REALMS_URL, params={"namespace": "dynamic-eu", "locale": "de_DE"}, json=REALMS
    )
    entry = await _setup(hass)
    device_id = er.async_get(hass).async_get(LEVEL).device_id

    result = await _start_reconfigure(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    # Nach der Umbenennung liefert die API den Charakter unter dem neuen Namen.
    mock_api(
        aioclient_mock, {NEW_API: {**PROFILE, "name": "Neuname", "id": 7}}, NEW_API
    )
    aioclient_mock.get(f"{NEW_API}/status", json={"id": 7, "is_valid": True})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"realm": "die-aldor", "character": "Neuname"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    (subentry,) = entry.subentries.values()
    assert subentry.title == "Neuname – Die Aldor"
    assert subentry.unique_id == UID1
    assert subentry.data["character"] == "Neuname"
    assert subentry.data["character_id"] == 7
    # Gleiche Entitaets-ID und gleiches Geraet, Werte vom neuen Namen
    entity = er.async_get(hass).async_get(LEVEL)
    assert entity.unique_id == f"{UID1}-level"
    assert entity.device_id == device_id
    assert hass.states.get(LEVEL).state == "90"
    assert dr.async_get(hass).async_get(device_id).name == "Neuname – Die Aldor"


async def test_reconfigure_to_existing_character_aborts(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    aioclient_mock.get(
        REALMS_URL, params={"namespace": "dynamic-eu", "locale": "de_DE"}, json=REALMS
    )
    second = character_subentry(UID2, "Zweitchar – Aegwynn", "aegwynn", "Zweitchar")
    entry = await _setup(hass, character_subentry(), second)

    result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"realm": "aegwynn", "character": "zweitchar"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_new_character_after_rename_gets_own_unique_id(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Der alte Name ist nach einer Umbenennung wieder frei."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {NEW_API: {**PROFILE, "name": "Neuname"}}, NEW_API)
    aioclient_mock.get(
        REALMS_URL, params={"namespace": "dynamic-eu", "locale": "de_DE"}, json=REALMS
    )
    mock_api(aioclient_mock, {API: {**PROFILE, "id": 8}})
    # Umbenannter Charakter: alte unique_id, neuer Name
    renamed = character_subentry(UID1, "Neuname – Die Aldor", character="Neuname")
    entry = await _setup(hass, renamed)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "character"), context={"source": config_entries.SOURCE_USER}
    )
    # Menue "Charaktere hinzufuegen": von Hand eingeben.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"region": "eu", "game_version": "retail"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"realm": "die-aldor", "character": "Testchar"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["unique_id"] == f"{UID1}-8"
    assert result["data"]["character_id"] == 8


async def test_stale_world_entities_devices_and_issues_removed(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    # Realm ohne Charakter (frueher Aegwynn) und Spielwelt einer Region ohne Charakter
    old_realm = ent_reg.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        "id-world-eu-realm-aegwynn-status",
        config_entry=entry,
    )
    old_world = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}-world-us")},
    )
    ir.async_create_issue(
        hass,
        DOMAIN,
        "character_entfernt",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="character_not_found",
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert ent_reg.async_get(old_realm.entity_id) is None
    assert dev_reg.async_get(old_world.id) is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, "character_entfernt") is None
    # Was noch gebraucht wird, bleibt
    current = ent_reg.async_get_entity_id(
        "binary_sensor", DOMAIN, "id-world-eu-realm-die-aldor-status"
    )
    assert hass.states.get(current).state == "on"
    assert hass.states.get(LEVEL).state == "90"


async def test_remove_device_only_when_unused(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    dev_reg = dr.async_get(hass)

    character = dev_reg.async_get_device(identifiers={(DOMAIN, UID1)})
    world = dev_reg.async_get_device(
        identifiers={(DOMAIN, f"{entry.entry_id}-world-eu")}
    )
    orphan = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "alt-geloescht")}
    )
    assert not await wow.async_remove_config_entry_device(hass, entry, character)
    assert not await wow.async_remove_config_entry_device(hass, entry, world)
    assert await wow.async_remove_config_entry_device(hass, entry, orphan)


async def test_reconfigure_same_name_accepts_new_id(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Gleicher Name, neue ID: Speichern uebernimmt den aktuellen Charakter."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: {**PROFILE, "id": 99}})
    aioclient_mock.get(
        REALMS_URL, params={"namespace": "dynamic-eu", "locale": "de_DE"}, json=REALMS
    )
    sub = character_subentry()
    sub["data"] = {**sub["data"], "character_id": 42}
    entry = await _setup(hass, sub)
    assert _issue(hass, entry).translation_key == "character_changed"

    result = await _start_reconfigure(hass, entry)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"realm": "die-aldor", "character": "Testchar"}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    (subentry,) = entry.subentries.values()
    assert subentry.data["character_id"] == 99
    assert _issue(hass, entry) is None
    assert hass.states.get(LEVEL).state == "90"


async def test_character_id_recorded_while_running(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Auch eine spaeter nachgetragene ID laedt den Eintrag nicht neu."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    runtime = entry.runtime_data
    (subentry,) = entry.subentries.values()
    assert "character_id" not in subentry.data

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: {**PROFILE, "id": 42}})
    await next(iter(runtime.coordinators.values())).async_refresh()
    await hass.async_block_till_done()

    (subentry,) = entry.subentries.values()
    assert subentry.data["character_id"] == 42
    assert entry.runtime_data is runtime


async def test_changed_id_holds_back_details(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Auch Ausruestung, Raids usw. zeigen nichts vom fremden Charakter."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: {**PROFILE, "id": 99}})
    sub = character_subentry()
    sub["data"] = {**sub["data"], "character_id": 42}
    await _setup(hass, sub)

    head = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{UID1}-equipment_head"
    )
    assert hass.states.get(head).state == "unavailable"


async def test_status_error_keeps_known_invalid(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock, valid=False)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    coordinator = next(iter(entry.runtime_data.coordinators.values()))
    assert _issue(hass, entry).translation_key == "character_invalid"

    # Status-Endpunkt faellt aus: Der bekannte ungueltige Stand bleibt.
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/status", status=500)
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    # Pruefung faellig machen, als waere ein Tag vergangen
    coordinator._status_checked = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(LEVEL).state == "unavailable"
    assert _issue(hass, entry).translation_key == "character_invalid"


async def test_stale_forever_world_removed_retail_kept(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Forever-Entitaeten ohne Forever-Charakter gehen, Retail bleibt."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    forever = ent_reg.async_get_or_create(
        "sensor", DOMAIN, "id-world-eu-forever-token", config_entry=entry
    )
    # Unbekannter Schluessel einer Spielwelt mit Charakter (z. B. aus einer
    # kuenftigen Version) bleibt stehen.
    future = ent_reg.async_get_or_create(
        "sensor", DOMAIN, "id-world-eu-season_end", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert ent_reg.async_get(forever.entity_id) is None
    assert ent_reg.async_get(future.entity_id) is not None
    token = ent_reg.async_get_entity_id("sensor", DOMAIN, "id-world-eu-token")
    assert hass.states.get(token).state == "345"
