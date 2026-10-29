"""Tests fuer 0.18.0: Entitaeten entstehen ohne Neuladen, sobald Daten kommen."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.const import DISCOVERY_MINUTES, DOMAIN

from .conftest import (
    ACHIEVEMENTS,
    API,
    EQUIPMENT,
    GAME,
    PROFILE,
    PVP_3V3,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

GUILD = "https://eu.api.blizzard.com/data/wow/guild/die-aldor/testgilde"
CLASSIC_UID = "eu-profile-classic1x-eu-die-aldor-testchar"
CLASSIC_WORLD = "id-world-eu-classic1x"


def _classic_subentry():
    sub = character_subentry(CLASSIC_UID)
    sub["data"] = {
        **sub["data"],
        "game_version": "classic_era",
        "namespace_suffix": "-classic1x",
    }
    return sub


async def _setup(hass: HomeAssistant, subentry=None):
    entry = main_entry(subentry or character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _eid(hass: HomeAssistant, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


def _calls(aioclient_mock, part: str) -> int:
    return sum(1 for call in aioclient_mock.mock_calls if part in str(call[1]))


async def _refresh(hass, aioclient_mock, coordinator, minutes: int, override=None):
    """Alle bisherigen Abfragen um minutes Minuten zurueckdatieren und neu abfragen.

    Zaehlt nur diese Runde.
    """
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, override)
    # Der Profil-Coordinator fragt bei jedem Lauf ab und hat keine Zeiten.
    for times in (
        getattr(coordinator, "_fetched", {}),
        getattr(coordinator, "_bracket_checked", {}),
    ):
        for key in times:
            times[key] -= minutes * 60
    await coordinator.async_refresh()
    await hass.async_block_till_done()


def _detail(entry):
    return next(iter(entry.runtime_data.details.values()))


async def test_profession_learned_later(hass: HomeAssistant, aioclient_mock) -> None:
    """Ohne Beruf beim Start: alle 6 Stunden pruefen, neuer Beruf ohne Neuladen."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/professions": {"primaries": []}})
    entry = await _setup(hass)
    detail = _detail(entry)
    assert _eid(hass, "sensor", f"{UID1}-profession-164") is None
    assert detail.endpoint_intervals()["professions"] == DISCOVERY_MINUTES

    await _refresh(hass, aioclient_mock, detail, 61)
    assert _calls(aioclient_mock, "/professions") == 0

    await _refresh(hass, aioclient_mock, detail, DISCOVERY_MINUTES)
    assert _calls(aioclient_mock, "/professions") == 1
    entity_id = _eid(hass, "sensor", f"{UID1}-profession-164")
    assert entity_id
    assert hass.states.get(entity_id).state == "42"


async def test_guild_joined_later(hass: HomeAssistant, aioclient_mock) -> None:
    """Gildenbeitritt: Sensor aus dem Profil, Werte mit der naechsten Detailabfrage."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    assert _eid(hass, "sensor", f"{UID1}-guild") is None

    in_guild = {
        **PROFILE,
        "guild": {
            "key": {"href": f"{GUILD}?namespace=profile-eu"},
            "name": "Testgilde",
        },
    }
    guild = {
        API: in_guild,
        GUILD: {"name": "Testgilde", "member_count": 123},
        f"{GUILD}/activity": {"activities": []},
        f"{GUILD}/roster": {"members": []},
    }
    (coordinator,) = entry.runtime_data.coordinators.values()
    await _refresh(hass, aioclient_mock, coordinator, 15, guild)
    entity_id = _eid(hass, "sensor", f"{UID1}-guild")
    assert entity_id
    assert hass.states.get(entity_id).state == "unknown"

    await _refresh(hass, aioclient_mock, _detail(entry), 61, guild)
    assert _calls(aioclient_mock, GUILD) == 3
    assert hass.states.get(entity_id).state == "123"
    assert hass.states.get(entity_id).attributes["name"] == "Testgilde"


async def test_pvp_bracket_rated_later(
    hass: HomeAssistant, aioclient_mock, caplog: pytest.LogCaptureFixture
) -> None:
    """Erste Wertung in 2v2: Sensor ohne Neuladen, danach stuendlich abgefragt."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    detail = _detail(entry)
    ent_reg = er.async_get(hass)
    count = len(er.async_entries_for_config_entry(ent_reg, entry.entry_id))
    assert _eid(hass, "sensor", f"{UID1}-pvp_bracket_2v2") is None

    # Stuendlich nur Brackets mit Sensor
    await _refresh(hass, aioclient_mock, detail, 61)
    assert _calls(aioclient_mock, "/pvp-bracket/3v3") == 1
    assert _calls(aioclient_mock, "/pvp-bracket/2v2") == 0

    # Alle 6 Stunden auch die anderen
    rated = {f"{API}/pvp-bracket/2v2": {**PVP_3V3, "rating": 1600}}
    await _refresh(hass, aioclient_mock, detail, DISCOVERY_MINUTES, rated)
    assert _calls(aioclient_mock, "/pvp-bracket/2v2") == 1
    assert _calls(aioclient_mock, "/pvp-bracket/rbg") == 1
    entity_id = _eid(hass, "sensor", f"{UID1}-pvp_bracket_2v2")
    assert entity_id
    assert hass.states.get(entity_id).state == "1600"
    assert detail.pvp_bracket_sensors == {"2v2", "3v3"}

    # Jetzt mit Sensor: stuendlich; der Sensor fuer 3v3 behaelt seinen Wert.
    await _refresh(hass, aioclient_mock, detail, 61, rated)
    assert _calls(aioclient_mock, "/pvp-bracket/2v2") == 1
    assert _calls(aioclient_mock, "/pvp-bracket/rbg") == 0
    sensor_3v3 = _eid(hass, "sensor", f"{UID1}-pvp_bracket_3v3")
    assert hass.states.get(sensor_3v3).state == "1850"
    # Genau ein neuer Sensor, nichts doppelt. Doppelt angelegte Entitaeten
    # verwirft Home Assistant selbst, meldet sie aber im Log.
    assert len(er.async_entries_for_config_entry(ent_reg, entry.entry_id)) == count + 1
    assert "already exists" not in caplog.text


async def test_disabled_endpoint_not_rediscovered(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Sind alle Entitaeten eines Endpunkts deaktiviert, bleibt er aus."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    detail = _detail(entry)
    er.async_get(hass).async_update_entity(
        _eid(hass, "sensor", f"{UID1}-reputation"),
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    assert "reputations" not in detail.endpoint_intervals()

    await _refresh(hass, aioclient_mock, detail, DISCOVERY_MINUTES)
    assert _calls(aioclient_mock, "/reputations") == 0


async def test_classic_achievements_later(hass: HomeAssistant, aioclient_mock) -> None:
    """Classic: Endpunkt ohne Entitaet liefert spaeter Daten, Sensor und Ereignis
    entstehen ohne Neuladen."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/achievements": 404})
    entry = await _setup(hass, _classic_subentry())
    assert _eid(hass, "sensor", f"{CLASSIC_UID}-achievements") is None
    assert _eid(hass, "event", f"{CLASSIC_UID}-new_achievement") is None

    await _refresh(
        hass,
        aioclient_mock,
        _detail(entry),
        DISCOVERY_MINUTES,
        {f"{API}/achievements": ACHIEVEMENTS},
    )
    entity_id = _eid(hass, "sensor", f"{CLASSIC_UID}-achievements")
    assert entity_id
    assert hass.states.get(entity_id).state == str(ACHIEVEMENTS["total_quantity"])
    assert _eid(hass, "event", f"{CLASSIC_UID}-new_achievement")


async def test_classic_extra_slot_later(hass: HomeAssistant, aioclient_mock) -> None:
    """Classic: ein spaeter belegter Zusatzplatz bekommt seinen Sensor."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, _classic_subentry())
    unique_id = f"{CLASSIC_UID}-equipment_extra_slot"
    assert _eid(hass, "sensor", unique_id) is None

    extra = {"slot": {"type": "EXTRA_SLOT", "name": "Zusatzplatz"}, "name": "Bogen"}
    equipment = {"equipped_items": [*EQUIPMENT["equipped_items"], extra]}
    await _refresh(
        hass, aioclient_mock, _detail(entry), 61, {f"{API}/equipment": equipment}
    )
    entity_id = _eid(hass, "sensor", unique_id)
    assert entity_id
    assert hass.states.get(entity_id).state == "Bogen"


async def test_classic_images_later(hass: HomeAssistant, aioclient_mock) -> None:
    """Classic: Bilder, die beim Start fehlen, entstehen ohne Neuladen."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/character-media": 404})
    entry = await _setup(hass, _classic_subentry())
    assert _eid(hass, "image", f"{CLASSIC_UID}-avatar") is None

    await _refresh(hass, aioclient_mock, _detail(entry), DISCOVERY_MINUTES)
    assert _eid(hass, "image", f"{CLASSIC_UID}-avatar")
    assert _eid(hass, "image", f"{CLASSIC_UID}-full_body")


async def test_classic_token_later(hass: HomeAssistant, aioclient_mock) -> None:
    """Classic ohne Preis beim Start: alle 6 Stunden pruefen, Sensor bei Preis."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/token/index": 404})
    entry = await _setup(hass, _classic_subentry())
    world = entry.runtime_data.worlds[("eu", "-classic1x")]
    assert _eid(hass, "sensor", f"{CLASSIC_WORLD}-token") is None
    assert world.token_sensor is False

    await _refresh(hass, aioclient_mock, world, 61, {f"{GAME}/token/index": 404})
    assert _calls(aioclient_mock, "/token/index") == 0

    await _refresh(hass, aioclient_mock, world, DISCOVERY_MINUTES)
    assert _calls(aioclient_mock, "/token/index") == 1
    entity_id = _eid(hass, "sensor", f"{CLASSIC_WORLD}-token")
    assert entity_id
    assert hass.states.get(entity_id).state == "345"
    # Mit Sensor wieder stuendlich
    assert world.token_sensor is True
    await _refresh(hass, aioclient_mock, world, 61)
    assert _calls(aioclient_mock, "/token/index") == 1


async def test_classic_realm_answers_later(hass: HomeAssistant, aioclient_mock) -> None:
    """Classic: Realm ohne Antwort beim Start bekommt seine Entitaeten spaeter."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/realm/die-aldor": 404})
    entry = await _setup(hass, _classic_subentry())
    keys = (
        ("binary_sensor", "realm-die-aldor-status"),
        ("binary_sensor", "realm-die-aldor-queue"),
        ("sensor", "realm-die-aldor-population"),
    )
    for platform, key in keys:
        assert _eid(hass, platform, f"{CLASSIC_WORLD}-{key}") is None

    world = entry.runtime_data.worlds[("eu", "-classic1x")]
    await _refresh(hass, aioclient_mock, world, 15)
    for platform, key in keys:
        assert _eid(hass, platform, f"{CLASSIC_WORLD}-{key}"), key
    status = _eid(hass, "binary_sensor", f"{CLASSIC_WORLD}-realm-die-aldor-status")
    assert hass.states.get(status).state == "on"
