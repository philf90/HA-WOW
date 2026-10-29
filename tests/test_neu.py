"""Tests fuer 0.8.0: Ereignisse fuer Neues, Gilde, Quests, Symbole, Spielwelt."""

from homeassistant import config_entries
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.wow_character.api import BattleNetClient, BattleNetError
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    ACHIEVEMENTS,
    API,
    GAME,
    PROFILE,
    RAIDS,
    REALMS,
    REALMS_URL,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

MEDIA = "https://eu.api.blizzard.com/data/wow/media"
GUILD = "https://eu.api.blizzard.com/data/wow/guild/die-aldor/testgilde"
PROFILE_IDS = {
    **PROFILE,
    "character_class": {"name": "Magier", "id": 8},
    "active_spec": {"name": "Frost", "id": 64},
    "guild": {
        "key": {"href": f"{GUILD}?namespace=profile-eu"},
        "name": "Testgilde",
        "id": 77,
    },
}


def _icon(url: str) -> dict:
    return {"assets": [{"key": "icon", "value": url}]}


async def _setup(hass: HomeAssistant):
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, domain: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{UID1}-{key}")


async def test_quests_and_profession_icon(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass)

    assert hass.states.get(_entity(hass, "sensor", "quests_completed")).state == "4"
    profession = hass.states.get(_entity(hass, "sensor", "profession-164"))
    assert (
        profession.attributes["entity_picture"] == "https://render.example/schmied.jpg"
    )
    # Ohne Gilden-Link im Profil gibt es keinen Gilden-Sensor.
    assert _entity(hass, "sensor", "guild") is None


async def test_class_spec_and_raid_images(hass: HomeAssistant, aioclient_mock) -> None:
    raids = {
        "expansions": [
            {
                **RAIDS["expansions"][1],
                "instances": [
                    {
                        **RAIDS["expansions"][1]["instances"][0],
                        "instance": {"name": "Neuer Raid", "id": 1302},
                    }
                ],
            }
        ]
    }
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            API: {**PROFILE_IDS, "guild": None},
            f"{API}/encounters/raids": raids,
            f"{MEDIA}/playable-class/8": _icon("https://render.example/magier.jpg"),
            f"{MEDIA}/playable-specialization/64": _icon(
                "https://render.example/frost.jpg"
            ),
            f"{MEDIA}/journal-instance/1302": {
                "assets": [{"key": "tile", "value": "https://render.example/raid.jpg"}]
            },
        },
    )
    await _setup(hass)

    level = hass.states.get("sensor.testchar_die_aldor_level").attributes
    assert level["class_icon"] == "https://render.example/magier.jpg"
    assert level["spec_icon"] == "https://render.example/frost.jpg"
    heroic = hass.states.get(_entity(hass, "sensor", "raid_heroic")).attributes
    assert heroic["images"] == {"Neuer Raid": "https://render.example/raid.jpg"}


async def test_guild_sensor(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            API: PROFILE_IDS,
            f"{MEDIA}/playable-class/8": 404,
            f"{MEDIA}/playable-specialization/64": 404,
            GUILD: {
                "name": "Testgilde",
                "member_count": 123,
                "achievement_points": 4560,
                "created_timestamp": 1500000000000,
                "realm": {"name": "Die Aldor"},
                "faction": {"name": "Allianz"},
            },
            f"{GUILD}/activity": {
                "activities": [
                    {
                        "activity": {"type": "CHARACTER_ACHIEVEMENT"},
                        "character_achievement": {
                            "character": {"name": "Mitglied"},
                            "achievement": {"name": "Ein Erfolg"},
                        },
                        "timestamp": 1761000000000,
                    },
                    {
                        "activity": {"type": "ENCOUNTER"},
                        "encounter_completed": {
                            "encounter": {"name": "Ein Boss"},
                            "mode": {"name": "Heroisch", "type": "HEROIC"},
                        },
                        "timestamp": 1761100000000,
                    },
                ]
            },
            # Felder wie in den Typdefinitionen von @blizzard-api/classic-wow
            # 4.2.0 und @blizzard-api/wow 4.1.4; Klassen nur als ID.
            f"{GUILD}/roster": {
                "members": [
                    {
                        "character": {
                            "name": "Anton",
                            "level": 70,
                            "playable_class": {"id": 3},
                        },
                        "rank": 2,
                    },
                    {
                        "character": {
                            "name": "Zora",
                            "level": 80,
                            "playable_class": {"id": 8},
                        },
                        "rank": 0,
                    },
                ]
            },
            f"{GAME}/playable-class/8": {"id": 8, "name": "Magier"},
            # Klasse 3 laesst sich nicht nachschlagen: Name fehlt.
            f"{GAME}/playable-class/3": 404,
        },
    )
    await _setup(hass)

    state = hass.states.get(_entity(hass, "sensor", "guild"))
    assert state.state == "123"
    attrs = state.attributes
    assert attrs["name"] == "Testgilde"
    assert attrs["achievement_points"] == 4560
    assert attrs["faction"] == "Allianz"
    assert attrs["created"] == "2017-07-14T02:40:00+00:00"
    # Neueste zuerst
    assert attrs["activities"][0]["boss"] == "Ein Boss"
    assert attrs["activities"][0]["difficulty"] == "Heroisch"
    assert attrs["activities"][1] == {
        "type": "CHARACTER_ACHIEVEMENT",
        "timestamp": "2025-10-20T22:40:00+00:00",
        "character": "Mitglied",
        "achievement": "Ein Erfolg",
    }
    # Nach Rang sortiert, nicht nach Name; Klassenname nur, wo das Nachschlagen
    # klappt.
    assert attrs["members"] == [
        {"name": "Zora", "level": 80, "class": "Magier", "class_id": 8, "rank": 0},
        {"name": "Anton", "level": 70, "class": None, "class_id": 3, "rank": 2},
    ]


async def test_new_collectible_event(hass: HomeAssistant, aioclient_mock) -> None:
    mounts = {"mounts": [{"mount": {"name": "Braunes Pferd", "id": 6}}]}
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/collections/mounts": mounts})
    entry = await _setup(hass)
    event_id = _entity(hass, "event", "new_collectible")
    # Beim Start loest nichts aus.
    assert hass.states.get(event_id).state == "unknown"

    detail = next(iter(entry.runtime_data.details.values()))
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{API}/collections/mounts": {
                "mounts": [*mounts["mounts"], {"mount": {"name": "Rappe", "id": 9}}]
            },
            f"{API}/titles": {"titles": [{"name": "der Neue", "id": 47}]},
        },
    )
    fired: list[tuple[str, str]] = []

    @callback
    def _record(event: Event) -> None:
        new = event.data["new_state"]
        if event.data["entity_id"] == event_id and new is not None:
            fired.append((new.attributes["event_type"], new.attributes["name"]))

    hass.bus.async_listen(EVENT_STATE_CHANGED, _record)
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()

    # Je neuem Eintrag ein Ereignis, das schon vorhandene Pferd nicht.
    assert fired == [("mount", "Rappe"), ("title", "der Neue")]


async def test_new_mount_fires(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    event_id = _entity(hass, "event", "new_collectible")
    detail = next(iter(entry.runtime_data.details.values()))

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{API}/collections/mounts": {
                "mounts": [{}, {}, {"mount": {"name": "Rappe", "id": 9}}]
            }
        },
    )
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()

    attrs = hass.states.get(event_id).attributes
    assert attrs["event_type"] == "mount"
    assert attrs["name"] == "Rappe"
    assert attrs["id"] == 9


async def test_level_up_event(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    event_id = _entity(hass, "event", "level_up")
    assert hass.states.get(event_id).state == "unknown"

    coordinator = next(iter(entry.runtime_data.coordinators.values()))
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: {**PROFILE, "level": 91}})
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    attrs = hass.states.get(event_id).attributes
    assert attrs["event_type"] == "level_up"
    assert attrs["level"] == 91
    assert attrs["previous"] == 90


async def test_achievement_event_has_icon(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    event_id = _entity(hass, "event", "new_achievement")
    detail = next(iter(entry.runtime_data.details.values()))

    newer = {
        **ACHIEVEMENTS,
        "recent_events": [
            *ACHIEVEMENTS["recent_events"],
            {
                "achievement": {"name": "Neuer Erfolg", "id": 61679},
                "timestamp": 1762000000000,
            },
        ],
    }
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{API}/achievements": newer,
            f"{MEDIA}/achievement/61679": _icon("https://render.example/erfolg.jpg"),
        },
    )
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()

    attrs = hass.states.get(event_id).attributes
    assert attrs["achievement"] == "Neuer Erfolg"
    assert attrs["icon"] == "https://render.example/erfolg.jpg"


async def test_collectible_needs_its_endpoints(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Ist nur das Ereignis aktiv, werden die Sammlungen trotzdem abgefragt."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    ent_reg = er.async_get(hass)
    for key in ("mounts", "pets", "toys", "titles"):
        ent_reg.async_update_entity(
            _entity(hass, "sensor", key),
            disabled_by=er.RegistryEntryDisabler.USER,
        )
    detail = next(iter(entry.runtime_data.details.values()))
    assert {"mounts", "pets", "toys", "titles"} <= detail.needed_endpoints()

    ent_reg.async_update_entity(
        _entity(hass, "event", "new_collectible"),
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    assert not {"mounts", "pets", "toys", "titles"} & detail.needed_endpoints()


async def test_world_part_failure_keeps_others(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/token/index": 500})
    await _setup(hass)

    reset = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, "id-world-eu-weekly_reset"
    )
    server = er.async_get(hass).async_get_entity_id(
        "binary_sensor", DOMAIN, "id-world-eu-realm-die-aldor-status"
    )
    token = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, "id-world-eu-token"
    )
    assert hass.states.get(reset).state == "2025-10-28T07:00:00+00:00"
    assert hass.states.get(server).state == "on"
    assert hass.states.get(token).state == "unknown"


async def test_world_all_parts_fail(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{GAME}/token/index": 500,
            f"{GAME}/mythic-keystone/period/index": 500,
            f"{GAME}/mythic-keystone/season/index": 500,
            f"{GAME}/realm/die-aldor": 500,
        },
    )
    await _setup(hass)
    token = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, "id-world-eu-token"
    )
    assert hass.states.get(token).state == "unavailable"


async def test_timeout_message(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(f"{GAME}/token/index", exc=TimeoutError())
    client = BattleNetClient(async_get_clientsession(hass), "id", "secret")
    try:
        await client.get_game_data("eu", "", "token/index")
    except BattleNetError as err:
        assert str(err) == "/data/wow/token/index: keine Antwort nach 15 s"
    else:
        raise AssertionError("kein Fehler")


async def test_internal_realms_hidden(hass: HomeAssistant, aioclient_mock) -> None:
    realms = {
        "realms": [
            *REALMS["realms"],
            {"id": 9, "name": "EU1A Account Realm", "slug": "eu1a-account-realm"},
            {"id": 10, "name": "EU4A1-INST-BFA", "slug": "eu4a1instbfa"},
            {"id": 11, "name": "RDB EU", "slug": "rdb-eu"},
            {"id": 12, "name": "zzz_RDB EU", "slug": "zzzrdb-eu"},
            {"id": 13, "name": "EU Arena Pass CSBG", "slug": "eu-arena-pass-csbg"},
        ]
    }
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    aioclient_mock.get(
        REALMS_URL, params={"namespace": "dynamic-eu", "locale": "de_DE"}, json=realms
    )
    entry = await _setup(hass)
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
    (selector,) = [v for k, v in result["data_schema"].schema.items() if k == "realm"]
    assert [o["value"] for o in selector.config["options"]] == [
        "aegwynn",
        "die-aldor",
        "kult-der-verdammten",
    ]


async def test_two_boss_kills_in_one_update(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Zwei neue Kills in einer Abfrage loesen zwei Ereignisse aus."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    event_id = _entity(hass, "event", "boss_killed")
    detail = next(iter(entry.runtime_data.details.values()))

    mode = RAIDS["expansions"][1]["instances"][0]["modes"][0]
    encounters = [
        *mode["progress"]["encounters"],
        {"encounter": {"name": "Zweiter Boss"}, "last_kill_timestamp": 1762000000000},
        {"encounter": {"name": "Dritter Boss"}, "last_kill_timestamp": 1762000100000},
    ]
    raids = {
        "expansions": [
            RAIDS["expansions"][0],
            {
                **RAIDS["expansions"][1],
                "instances": [
                    {
                        **RAIDS["expansions"][1]["instances"][0],
                        "modes": [
                            {
                                **mode,
                                "progress": {
                                    **mode["progress"],
                                    "encounters": encounters,
                                },
                            },
                            *RAIDS["expansions"][1]["instances"][0]["modes"][1:],
                        ],
                    }
                ],
            },
        ]
    }
    fired: list[str] = []

    @callback
    def _record(event: Event) -> None:
        new = event.data["new_state"]
        if event.data["entity_id"] == event_id and new is not None:
            fired.append(new.attributes["boss"])

    hass.bus.async_listen(EVENT_STATE_CHANGED, _record)
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/encounters/raids": raids})
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()

    assert fired == ["Zweiter Boss", "Dritter Boss"]
