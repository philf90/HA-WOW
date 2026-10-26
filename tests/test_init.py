"""Tests fuer Start, Sensoren, Fehlertoleranz und den Umbau von Version 1."""

from unittest.mock import MagicMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.wow_character as wow
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    API2,
    MYTHIC,
    PROFILE,
    UID1,
    UID2,
    character_subentry,
    main_entry,
    mock_token,
)

SECOND = character_subentry(UID2, "Zweitchar – Aegwynn", "aegwynn", "Zweitchar")


async def test_sensors(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.testchar_die_aldor_level").state == "90"
    assert hass.states.get("sensor.testchar_die_aldor_item_level").state == "701"
    assert (
        hass.states.get("sensor.testchar_die_aldor_last_login").state
        == "2025-10-25T13:46:40+00:00"
    )
    attrs = hass.states.get("sensor.testchar_die_aldor_level").attributes
    assert attrs["class"] == "Magier"
    assert attrs["guild"] == "Testgilde"

    # Geraet und Entitaeten haengen am Untereintrag des Charakters.
    (subentry_id,) = entry.subentries
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, UID1)})
    assert device.config_entries_subentries == {entry.entry_id: {subentry_id}}
    entity = er.async_get(hass).async_get("sensor.testchar_die_aldor_level")
    assert entity.config_subentry_id == subentry_id
    assert entity.unique_id == f"{UID1}-level"


async def test_failing_character_does_not_block_others(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    aioclient_mock.get(API2, status=500)
    entry = main_entry(character_subentry(), SECOND)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert hass.states.get("sensor.testchar_die_aldor_level").state == "90"
    assert hass.states.get("sensor.zweitchar_aegwynn_level").state == "unavailable"


async def test_auth_error_starts_reauth(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock, status=401)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]
    assert hass.states.get("sensor.testchar_die_aldor_level").state == "unavailable"


async def test_remove_character(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    (subentry_id,) = entry.subentries
    hass.config_entries.async_remove_subentry(entry, subentry_id)
    await hass.async_block_till_done()
    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, UID1)}) is None
    assert er.async_get(hass).async_get("sensor.testchar_die_aldor_level") is None


# Umbau von Version 1


def _v1_entry(uid: str, title: str, realm: str, character: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title=title,
        unique_id=uid,
        data={
            "client_id": "id",
            "client_secret": "secret",
            "region": "eu",
            "game_version": "retail",
            "realm": realm,
            "character": character,
            "namespace_suffix": "",
        },
    )


def _register_v1(
    hass: HomeAssistant, entry: MockConfigEntry, object_id: str
) -> tuple[str, str]:
    """Geraet und Level-Sensor so anlegen, wie Version 1 sie hinterlassen hat."""
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        name=entry.title,
    )
    entity = er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.unique_id}-level",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id=f"{object_id}_level",
    )
    # Eigene Anpassung des Nutzers; muss den Umbau ueberstehen.
    er.async_get(hass).async_update_entity(entity.entity_id, name="Eigener Name")
    return entity.entity_id, device.id


async def test_migrate_v1_entry(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    old = _v1_entry(UID1, "Testchar – Die Aldor", "die-aldor", "Testchar")
    old.add_to_hass(hass)
    entity_id, device_id = _register_v1(hass, old, "testchar_die_aldor")

    assert await hass.config_entries.async_setup(old.entry_id)
    await hass.async_block_till_done()

    assert old.version == 2
    assert old.state is config_entries.ConfigEntryState.LOADED
    assert old.title == "Battle.net API"
    assert old.unique_id == "id"
    assert old.data == {"client_id": "id", "client_secret": "secret"}
    (subentry,) = old.subentries.values()
    assert subentry.unique_id == UID1
    assert subentry.title == "Testchar – Die Aldor"
    assert subentry.data["realm"] == "die-aldor"

    # Entitaets-ID und unique_id bleiben, Zuordnung wechselt zum Untereintrag.
    entity = er.async_get(hass).async_get(entity_id)
    assert entity_id == "sensor.testchar_die_aldor_level"
    assert entity.unique_id == f"{UID1}-level"
    assert entity.config_subentry_id == subentry.subentry_id
    assert entity.name == "Eigener Name"
    # Dasselbe Geraet (gleiche ID), damit Automationen mit Geraete-ID weiterlaufen.
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, UID1)})
    assert device.id == device_id
    assert entity.device_id == device_id
    assert device.config_entries_subentries == {old.entry_id: {subentry.subentry_id}}
    assert hass.states.get(entity_id).state == "90"


async def test_migrate_merges_entries_of_same_client(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(API, json=PROFILE)
    aioclient_mock.get(f"{API}/mythic-keystone-profile", json=MYTHIC)
    aioclient_mock.get(API2, json={**PROFILE, "name": "Zweitchar"})
    aioclient_mock.get(f"{API2}/mythic-keystone-profile", json=MYTHIC)
    first = _v1_entry(UID1, "Testchar – Die Aldor", "die-aldor", "Testchar")
    second = _v1_entry(UID2, "Zweitchar – Aegwynn", "aegwynn", "Zweitchar")
    first.add_to_hass(hass)
    second.add_to_hass(hass)
    _register_v1(hass, first, "testchar_die_aldor")
    second_entity, second_device = _register_v1(hass, second, "zweitchar_aegwynn")

    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert entries == [first]
    assert {s.unique_id for s in first.subentries.values()} == {UID1, UID2}
    entity = er.async_get(hass).async_get(second_entity)
    assert entity.config_entry_id == first.entry_id
    assert entity.name == "Eigener Name"
    assert hass.states.get(second_entity).state == "90"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, UID2)})
    assert device.id == second_device
    assert set(device.config_entries) == {first.entry_id}


async def test_move_device_uses_new_api_when_available(hass: HomeAssistant) -> None:
    """Neuere Home-Assistant-Versionen: Geraet mit new_config_entry_id verschieben.

    Die Testumgebung (2026.2.3) kennt die neue Funktion noch nicht; geprueft wird
    daher nur, dass der Aufruf so aussieht, wie Home Assistant 2026.10 ihn erwartet.
    """
    entry = MockConfigEntry(domain=DOMAIN)
    parent = MockConfigEntry(domain=DOMAIN)
    dev_reg = MagicMock()
    with patch.object(wow, "_DEVICE_MOVE_SUPPORTED", True):
        wow._move_device(dev_reg, "geraet", entry, parent, "sub")
    dev_reg.async_update_device.assert_called_once_with(
        "geraet", new_config_entry_id=parent.entry_id, new_config_subentry_id="sub"
    )
