"""Tests fuer WoW Classic: Namespaces, abgefragte Endpunkte, angelegte Entitaeten.

Namespaces und Endpunkte laut Blizzard-Doku "World of Warcraft Classic
Namespaces", "... Profile APIs" und "... Game Data APIs" (Stand 28.10.2026).
Antwortfelder nennt die Doku nicht; die Antworten hier sind nachgebaut wie bei
Retail, Werte erfunden.
"""

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character import _parse_world_key
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    ACHIEVEMENTS,
    API,
    BASE_INPUT,
    CHARACTER_INPUT,
    EQUIPMENT,
    GAME,
    PROFILE,
    REALMS,
    REALMS_URL,
    STATS,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

UID = "eu-profile-classic1x-eu-die-aldor-testchar"
WORLD = "id-world-eu-classic1x"

# Endpunkte, die die Classic-Doku nicht nennt; die Integration fragt sie nicht ab.
UNDOCUMENTED = (
    "/encounters/raids",
    "/mythic-keystone",
    "/professions",
    "/collections/",
    "/reputations",
    "/titles",
    "/quests/completed",
    "/media/playable-specialization/",
    "/media/profession/",
    "/media/journal-instance/",
    "/media/achievement/",
    "/achievement-category/",
    "/profession/",
)


def _classic_subentry(version: str = "classic_era", suffix: str = "-classic1x"):
    sub = character_subentry(UID)
    sub["data"] = {**sub["data"], "game_version": version, "namespace_suffix": suffix}
    return sub


def _eid(hass: HomeAssistant, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


async def _setup(hass: HomeAssistant, *subentries):
    entry = main_entry(*subentries)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize(
    ("version", "suffix"),
    [
        ("classic_era", "-classic1x"),
        ("classic_progression", "-classic"),
        ("classic_anniversary", "-classicann"),
    ],
)
async def test_add_classic_character_uses_documented_namespace(
    hass: HomeAssistant, aioclient_mock, version: str, suffix: str
) -> None:
    mock_token(aioclient_mock)
    ns = {"locale": "de_DE"}
    aioclient_mock.get(
        REALMS_URL, params={**ns, "namespace": f"dynamic{suffix}-eu"}, json=REALMS
    )
    aioclient_mock.get(
        API, params={**ns, "namespace": f"profile{suffix}-eu"}, json=PROFILE
    )
    entry = await _setup(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "character"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**BASE_INPUT, "game_version": version}
    )
    assert result["step_id"] == "character"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], CHARACTER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    (subentry,) = entry.subentries.values()
    assert subentry.data["game_version"] == version
    assert subentry.data["namespace_suffix"] == suffix
    # Eigene unique_id je Namespace: Retail- und Classic-Charakter gleichen
    # Namens auf gleichnamigem Realm kommen sich nicht in die Quere.
    assert subentry.unique_id == f"eu-profile{suffix}-eu-die-aldor-testchar"


async def test_classic_queries_only_documented_endpoints(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Auch wenn die API mehr liefern wuerde: nur dokumentierte Endpunkte."""
    mock_token(aioclient_mock)
    # Mit IDs, damit Symbole nachgeschlagen wuerden (Klasse ja, Spezialisierung
    # und Erfolg nein: nicht in der Classic-Doku).
    profile = {
        **PROFILE,
        "character_class": {"name": "Magier", "id": 8},
        "active_spec": {"name": "Frost", "id": 64},
    }
    achievements = {
        **ACHIEVEMENTS,
        "recent_events": [
            {"achievement": {"name": "Erfolg", "id": 6}, "timestamp": 1761000000000}
        ],
    }
    mock_api(
        aioclient_mock,
        {
            API: profile,
            f"{API}/achievements": achievements,
            f"{GAME}/token/index": 404,
            f"{GAME}/media/playable-class/8": {
                "assets": [{"key": "icon", "value": "https://render.example/mage.jpg"}]
            },
            f"{GAME}/media/playable-specialization/64": {"assets": []},
            f"{GAME}/media/achievement/6": {"assets": []},
        },
    )
    await _setup(hass, _classic_subentry())

    urls = [str(call[1]) for call in aioclient_mock.mock_calls]
    api_urls = [u for u in urls if "api.blizzard.com" in u]
    assert api_urls
    for url in api_urls:
        assert not any(part in url for part in UNDOCUMENTED), url
        assert "namespace=" in url
        assert "-classic1x-eu" in url, url
    for path in ("", "/status", "/pvp-summary", "/equipment", "/character-media"):
        assert any(u.startswith(f"{API}{path}?") for u in api_urls), path

    # Angelegt: Profil, Ausruestung, PvP, Erfolge, Bilder, Realm
    level = hass.states.get(_eid(hass, "sensor", f"{UID}-level"))
    assert level.state == "90"
    assert level.attributes["class_icon"] == "https://render.example/mage.jpg"
    assert level.attributes["spec_icon"] is None
    # Item-Symbole stehen in der Classic-Doku (media/item/{id}).
    assert any(u.startswith(f"{GAME}/media/item/6001?") for u in api_urls)
    assert hass.states.get(_eid(hass, "sensor", f"{UID}-honor_level")).state == "50"
    assert _eid(hass, "sensor", f"{UID}-equipment_head")
    assert _eid(hass, "sensor", f"{UID}-achievements")
    assert _eid(hass, "event", f"{UID}-new_achievement")
    assert _eid(hass, "event", f"{UID}-level_up")
    assert _eid(hass, "image", f"{UID}-avatar")
    assert _eid(hass, "binary_sensor", f"{WORLD}-realm-die-aldor-status")
    # Nicht angelegt: Endpunkte, die Classic nicht kennt
    for platform, key in (
        ("sensor", "raid_heroic"),
        ("sensor", "mythic_rating"),
        ("sensor", "mythic_best_key"),
        ("sensor", "mounts"),
        ("sensor", "pets"),
        ("sensor", "toys"),
        ("sensor", "reputation"),
        ("sensor", "titles"),
        ("sensor", "quests_completed"),
        ("sensor", "profession-164"),
        ("event", "boss_killed"),
        ("event", "new_collectible"),
    ):
        assert _eid(hass, platform, f"{UID}-{key}") is None, key
    # Spielwelt: ohne Mythic+ kein Reset, WoW-Marke nur mit Antwort
    assert _eid(hass, "sensor", f"{WORLD}-weekly_reset") is None
    assert _eid(hass, "sensor", f"{WORLD}-token") is None


async def test_classic_world_device_name_and_token(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, _classic_subentry("classic_progression", "-classic"))

    world = "id-world-eu-classic"
    token = _eid(hass, "sensor", f"{world}-token")
    assert token, "WoW-Marke fehlt, obwohl die API einen Preis liefert"
    assert hass.states.get(token).state == "345"
    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, f"{entry.entry_id}-world-eu-classic")}
    )
    assert device.name == "WoW world EU Classic Progression"


async def test_classic_skips_sensors_without_value(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Felder, die die Classic-Antwort nicht enthaelt, ergeben keine Sensoren."""
    mock_token(aioclient_mock)
    profile = {
        k: v
        for k, v in PROFILE.items()
        if k not in ("equipped_item_level", "average_item_level")
    }
    stats = {
        k: v
        for k, v in STATS.items()
        if k not in ("mastery", "versatility_damage_done_bonus")
    }
    mock_api(aioclient_mock, {API: profile, f"{API}/statistics": stats})
    await _setup(hass, _classic_subentry())

    assert _eid(hass, "sensor", f"{UID}-level")
    assert _eid(hass, "sensor", f"{UID}-experience")
    assert _eid(hass, "sensor", f"{UID}-item_level") is None
    assert _eid(hass, "sensor", f"{UID}-item_level_average") is None
    # Werte-Sensoren sind standardmaessig aus, aber im Register angelegt.
    assert _eid(hass, "sensor", f"{UID}-stat_crit")
    assert _eid(hass, "sensor", f"{UID}-stat_mastery") is None
    assert _eid(hass, "sensor", f"{UID}-stat_versatility") is None


async def test_classic_failed_first_query_creates_sensors(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ohne erste Antwort ist nichts bekannt: Sensoren werden angelegt."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/statistics": 500})
    await _setup(hass, _classic_subentry())

    assert _eid(hass, "sensor", f"{UID}-stat_mastery")


async def test_extra_equipment_slot_from_response(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Platz ausserhalb der Retail-Liste bekommt einen Sensor mit dem API-Namen."""
    mock_token(aioclient_mock)
    # Bezeichner und Name erfunden: Die Doku nennt keine Platz-Bezeichner.
    extra = {
        "item": {"id": 5009},
        "slot": {"type": "EXTRA_SLOT", "name": "Zusatzplatz"},
        "name": "Testbogen",
        "level": {"value": 60},
    }
    equipment = {"equipped_items": [*EQUIPMENT["equipped_items"], extra]}
    mock_api(aioclient_mock, {f"{API}/equipment": equipment})
    await _setup(hass, _classic_subentry())

    entity_id = _eid(hass, "sensor", f"{UID}-equipment_extra_slot")
    assert entity_id
    state = hass.states.get(entity_id)
    assert state.state == "60"
    assert state.attributes["name"] == "Testbogen"
    assert state.attributes["friendly_name"].endswith("Equipment Zusatzplatz")
    assert _eid(hass, "sensor", f"{UID}-equipment_head")


async def test_retail_keeps_fixed_equipment_slots(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Retail bleibt bei den 18 Plaetzen, auch wenn die Antwort mehr nennt."""
    mock_token(aioclient_mock)
    extra = {"slot": {"type": "EXTRA_SLOT", "name": "Zusatzplatz"}, "name": "X"}
    equipment = {"equipped_items": [*EQUIPMENT["equipped_items"], extra]}
    mock_api(aioclient_mock, {f"{API}/equipment": equipment})
    await _setup(hass, character_subentry())

    uid = "eu-profile-eu-die-aldor-testchar"
    assert _eid(hass, "sensor", f"{uid}-equipment_head")
    assert _eid(hass, "sensor", f"{uid}-equipment_extra_slot") is None


@pytest.mark.parametrize(
    ("subentry", "uid", "expected"),
    [
        # Classic Era nennt je Item kein Itemlevel (Antwort vom 28.10.2026).
        (_classic_subentry(), UID, "Testhelm"),
        # Retail bleibt beim Itemlevel; fehlt es, bleibt der Zustand leer.
        (character_subentry(), "eu-profile-eu-die-aldor-testchar", "unknown"),
    ],
)
async def test_equipment_without_item_level(
    hass: HomeAssistant, aioclient_mock, subentry, uid: str, expected: str
) -> None:
    mock_token(aioclient_mock)
    items = [
        {k: v for k, v in item.items() if k != "level"}
        for item in EQUIPMENT["equipped_items"]
    ]
    mock_api(aioclient_mock, {f"{API}/equipment": {"equipped_items": items}})
    await _setup(hass, subentry)

    head = hass.states.get(_eid(hass, "sensor", f"{uid}-equipment_head"))
    assert head.state == expected
    assert head.attributes["name"] == "Testhelm"
    # Leerer Platz: weder Itemlevel noch Name.
    neck = hass.states.get(_eid(hass, "sensor", f"{uid}-equipment_neck"))
    assert neck.state == "unknown"


def _detail_calls(aioclient_mock, path: str) -> int:
    return sum(
        1
        for call in aioclient_mock.mock_calls
        if str(call[1]).startswith(f"{API}{path}?")
    )


async def test_endpoint_without_entity_not_queried_again(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Classic Era kennt keine Erfolge (404): ohne Entitaet keine weitere Abfrage."""
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {f"{API}/achievements": 404, f"{API}/achievements/statistics": 404},
    )
    entry = await _setup(hass, _classic_subentry())
    assert _eid(hass, "sensor", f"{UID}-achievements") is None
    assert _eid(hass, "sensor", f"{UID}-game_statistics") is None
    assert _eid(hass, "event", f"{UID}-new_achievement") is None
    paths = ("/achievements", "/achievements/statistics", "/equipment")
    assert [_detail_calls(aioclient_mock, path) for path in paths] == [1, 1, 1]

    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    # Alle Abstaende zuruecksetzen: Jeder Endpunkt waere wieder faellig.
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert detail.last_update_success
    # Die Ausruestung hat Sensoren und wird weiter abgefragt.
    assert [_detail_calls(aioclient_mock, path) for path in paths] == [1, 1, 2]


def test_parse_classic_world_keys() -> None:
    assert _parse_world_key("eu-classic1x-token") == (("eu", "-classic1x"), "token")
    assert _parse_world_key("us-classic-realm-x-status") == (
        ("us", "-classic"),
        "realm-x-status",
    )
    assert _parse_world_key("eu-classicann-realm-classic-y-queue") == (
        ("eu", "-classicann"),
        "realm-classic-y-queue",
    )
    # Retail-Realm, dessen Slug mit "classic" beginnt, bleibt Retail.
    assert _parse_world_key("eu-realm-classic-z-status") == (
        ("eu", ""),
        "realm-classic-z-status",
    )


def _token_calls(aioclient_mock) -> int:
    return sum(
        1 for call in aioclient_mock.mock_calls if "/token/index" in str(call[1])
    )


async def _refresh_world(hass: HomeAssistant, world) -> None:
    # Alle Abstaende zuruecksetzen: Jede Teilabfrage waere wieder faellig.
    world._fetched.clear()
    await world.async_refresh()
    await hass.async_block_till_done()


async def test_classic_without_token_stops_asking(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Kein Preis beim Start: kein Sensor, danach keine Abfrage bis zum Neuladen."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/token/index": 404})
    entry = await _setup(hass, _classic_subentry())
    world = entry.runtime_data.worlds[("eu", "-classic1x")]
    assert _eid(hass, "sensor", f"{WORLD}-token") is None
    assert _token_calls(aioclient_mock) == 1

    await _refresh_world(hass, world)
    assert _token_calls(aioclient_mock) == 1
    # Die Realms werden weiter abgefragt.
    assert world.last_update_success
    assert world.data["realms"]["die-aldor"]["status"] == "UP"


async def test_classic_with_token_keeps_asking(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, _classic_subentry())
    world = entry.runtime_data.worlds[("eu", "-classic1x")]
    assert _eid(hass, "sensor", f"{WORLD}-token")

    await _refresh_world(hass, world)
    assert _token_calls(aioclient_mock) == 2


async def test_retail_token_asked_even_without_price(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Retail legt den Sensor immer an und fragt deshalb weiter ab."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/token/index": 404})
    entry = await _setup(hass, character_subentry())
    world = entry.runtime_data.worlds[("eu", "")]
    assert _eid(hass, "sensor", "id-world-eu-token")

    await _refresh_world(hass, world)
    assert _token_calls(aioclient_mock) == 2
