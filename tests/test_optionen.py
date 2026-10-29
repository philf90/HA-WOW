"""Tests fuer 0.20.0: Takte und ausgeschaltete Gruppen als Optionen."""

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    PROFILE,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

GUILD = "https://eu.api.blizzard.com/data/wow/guild/die-aldor/testgilde"
IN_GUILD = {
    **PROFILE,
    "guild": {"key": {"href": f"{GUILD}?namespace=profile-eu"}, "name": "Testgilde"},
}
GUILD_ANSWERS = {
    API: IN_GUILD,
    GUILD: {"name": "Testgilde", "member_count": 123},
    f"{GUILD}/activity": {"activities": []},
    f"{GUILD}/roster": {"members": []},
}


async def _setup(hass: HomeAssistant, options: dict | None = None):
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    if options is not None:
        hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _eid(hass: HomeAssistant, platform: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{UID1}-{key}")


def _calls(aioclient_mock, part: str) -> int:
    return sum(1 for call in aioclient_mock.mock_calls if part in str(call[1]))


def _coordinators(entry):
    runtime = entry.runtime_data
    (profile,) = runtime.coordinators.values()
    (detail,) = runtime.details.values()
    return profile, detail


# Takte


async def test_default_intervals(hass: HomeAssistant, aioclient_mock) -> None:
    """Ohne Optionen dieselben Takte wie vor 0.20.0."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    profile, detail = _coordinators(await _setup(hass))
    assert profile.update_interval == timedelta(minutes=15)
    assert detail.update_interval == timedelta(minutes=60)
    intervals = detail.endpoint_intervals()
    assert intervals["raids"] == 60
    assert intervals["professions"] == 360
    assert intervals["guild"] == 360  # ohne Gilde keine Entitaet: selten


async def test_chosen_intervals(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    options = {"profile_minutes": 30, "detail_minutes": 120, "rare_minutes": 720}
    entry = await _setup(hass, options)
    profile, detail = _coordinators(entry)
    assert profile.update_interval == timedelta(minutes=30)
    assert detail.update_interval == timedelta(minutes=120)
    intervals = detail.endpoint_intervals()
    # Vorgabe 60 -> Details, Vorgabe 360 -> seltene Details
    assert intervals["raids"] == 120
    assert intervals["equipment"] == 120
    assert intervals["professions"] == 720
    # Ohne Entitaet (keine Gilde): seltener Takt
    assert intervals["guild"] == 720


async def test_rare_brackets_and_token_follow_option(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Brackets ohne Sensor und die WoW-Marke ohne Sensor folgen dem seltenen Takt."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, {"rare_minutes": 120})
    _profile, detail = _coordinators(entry)
    # 2v2 ohne Sensor: nach 121 Minuten wieder gefragt (Vorgabe waeren 6 h)
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    for times in (detail._fetched, detail._bracket_checked):
        for key in times:
            times[key] -= 121 * 60
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, "/pvp-bracket/2v2") == 1

    # WoW-Marke ohne Sensor (sonst nur ausserhalb von Retail): ebenso
    (world,) = entry.runtime_data.worlds.values()
    world.token_sensor = False
    for key in world._fetched:
        world._fetched[key] -= 121 * 60
    await world.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, "/token/index") == 1


# Optionsdialog


async def _options_flow(hass: HomeAssistant, entry, data: dict):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    return await hass.config_entries.options.async_configure(result["flow_id"], data)


async def test_options_flow_saves_whole_minutes(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    result = await _options_flow(
        hass,
        entry,
        {
            "language": "region",
            "profile_minutes": 20.0,
            "detail_minutes": 90.0,
            "rare_minutes": 240.0,
            "disabled_groups": ["quests"],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {
        "language": "region",
        "profile_minutes": 20,
        "detail_minutes": 90,
        "rare_minutes": 240,
        "disabled_groups": ["quests"],
    }
    # Ganze Minuten, nicht 20.0 (20.0 == 20 waere in Python wahr)
    assert all(
        type(entry.options[key]) is int
        for key in ("profile_minutes", "detail_minutes", "rare_minutes")
    )
    profile, detail = _coordinators(entry)
    assert profile.update_interval == timedelta(minutes=20)
    assert "quests" not in detail.endpoint_intervals()


async def test_options_flow_rare_not_below_detail(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    result = await _options_flow(
        hass, entry, {"detail_minutes": 120, "rare_minutes": 60}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "rare_below_detail"}
    assert entry.options == {}


@pytest.mark.parametrize(
    "value", [{"profile_minutes": 4}, {"detail_minutes": 721}, {"rare_minutes": 59}]
)
async def test_options_flow_limits(hass: HomeAssistant, aioclient_mock, value) -> None:
    """Werte ausserhalb der Grenzen lehnt der Dialog ab."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], value)


# Gruppen


async def test_disabled_group_no_entities_no_queries(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ausgeschaltete Gruppen: keine Abfragen, keine Entitaeten, auch keine Ereignisse."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, GUILD_ANSWERS)
    groups = ["guild", "collections", "raids", "achievements", "professions"]
    await _setup(hass, {"disabled_groups": groups})

    for part in (
        GUILD,
        "/collections/",
        "/titles",
        "/encounters/raids",
        f"{API}/achievements?",  # nicht /achievements/statistics (andere Gruppe)
        "/professions",
    ):
        assert _calls(aioclient_mock, part) == 0, part
    for platform, key in (
        ("sensor", "guild"),
        ("sensor", "mounts"),
        ("sensor", "titles"),
        ("event", "new_collectible"),
        ("sensor", "raid_heroic"),
        ("event", "boss_killed"),
        ("sensor", "achievements"),
        ("event", "new_achievement"),
        ("sensor", "profession-164"),
    ):
        assert _eid(hass, platform, key) is None, key
    # Andere Gruppen laufen weiter.
    assert _eid(hass, "sensor", "reputation")
    assert _eid(hass, "sensor", "equipment_head")


async def test_group_off_and_on_keeps_entity(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ausschalten laesst die Entitaet in der Registry; Einschalten bringt sie zurueck."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    entity_id = _eid(hass, "sensor", "reputation")
    assert hass.states.get(entity_id).state == "2"

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _options_flow(hass, entry, {"disabled_groups": ["reputations"]})
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, "/reputations") == 0
    # Nicht mehr bereitgestellt, aber mit gleicher ID in der Registry
    assert _eid(hass, "sensor", "reputation") == entity_id
    assert hass.states.get(entity_id).state == "unavailable"

    await _options_flow(hass, entry, {"disabled_groups": []})
    await hass.async_block_till_done()
    assert _eid(hass, "sensor", "reputation") == entity_id
    assert hass.states.get(entity_id).state == "2"


async def test_disabled_group_not_discovered_later(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Auch das Nachlegen ohne Neuladen beachtet ausgeschaltete Gruppen."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, {"disabled_groups": ["guild"]})
    profile, detail = _coordinators(entry)

    # Spaeter Gildenbeitritt
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, GUILD_ANSWERS)
    await profile.async_refresh()
    for key in detail._fetched:
        detail._fetched[key] -= 7 * 3600
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _eid(hass, "sensor", "guild") is None
    assert _calls(aioclient_mock, GUILD) == 0
