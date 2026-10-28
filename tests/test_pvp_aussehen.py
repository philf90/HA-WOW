"""Tests fuer Aussehen (am Level-Sensor), PvP-Brackets und Gildenmitglieder.

Endpunkte laut Blizzard-Doku fuer Retail und Classic. Felder wie in den
Typdefinitionen von @blizzard-api/wow 4.1.4 und @blizzard-api/classic-wow 4.2.0;
Werte erfunden.
"""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.const import DOMAIN
from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    API,
    APPEARANCE,
    GAME,
    PROFILE,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

GUILD = "https://eu.api.blizzard.com/data/wow/guild/die-aldor/testgilde"
PROFILE_GUILD = {
    **PROFILE,
    "guild": {
        "name": "Testgilde",
        "key": {"href": f"{GUILD}?namespace=profile-eu"},
    },
}
ROSTER = {
    "members": [
        {
            "character": {"name": "Eins", "level": 60, "playable_class": {"id": 8}},
            "rank": 0,
        }
    ]
}


def _eid(hass: HomeAssistant, platform: str, key: str, uid: str = UID1) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{uid}-{key}")


async def _setup(hass: HomeAssistant, subentry=None):
    entry = main_entry(subentry or character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _calls(aioclient_mock, part: str) -> int:
    return sum(1 for call in aioclient_mock.mock_calls if part in str(call[1]))


async def test_level_sensor_shows_appearance(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)

    attrs = hass.states.get(_eid(hass, "sensor", "level")).attributes
    assert attrs["class"] == "Magier"
    assert attrs["gender"] == "Weiblich"
    # Keine Transmog-ID passt zur Ausruestung (Helm 5001): Bedeutung der ID
    # nicht belegt, daher keine Namen und kein Nachschlagen.
    assert attrs["transmog"] == [
        {"slot": "HEAD", "slot_name": "Kopf", "id": 7001, "name": None, "enchant": 0},
        {
            "slot": "MAIN_HAND",
            "slot_name": "Waffenhand",
            "id": 7002,
            "name": None,
            "enchant": 5,
        },
    ]
    assert _calls(aioclient_mock, "/data/wow/item/") == 0

    # Neues Aussehen kommt ueber den Detail-Coordinator am Level-Sensor an.
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {f"{API}/appearance": {**APPEARANCE, "gender": {"name": "Männlich"}}},
    )
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    attrs = hass.states.get(_eid(hass, "sensor", "level")).attributes
    assert attrs["gender"] == "Männlich"


async def test_appearance_only_with_level_sensor(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    assert "appearance" in detail.needed_endpoints()

    er.async_get(hass).async_update_entity(
        _eid(hass, "sensor", "level"), disabled_by=er.RegistryEntryDisabler.USER
    )
    assert "appearance" not in detail.needed_endpoints()


async def test_pvp_bracket_sensors(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass)

    state = hass.states.get(_eid(hass, "sensor", "pvp_bracket_3v3"))
    assert state.state == "1850"
    assert state.attributes["friendly_name"].endswith("PvP rating 3V3")
    assert state.attributes["season_won"] == 70
    assert state.attributes["season_lost"] == 50
    assert state.attributes["weekly_played"] == 10
    assert state.attributes["season_id"] == 40
    # 404 beim Start: kein Sensor
    assert _eid(hass, "sensor", "pvp_bracket_2v2") is None
    assert _eid(hass, "sensor", "pvp_bracket_rbg") is None
    assert _calls(aioclient_mock, "/pvp-bracket/") == 3


async def test_pvp_bracket_error_keeps_old_value(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Fehler ohne 404 bei einem Bracket mit Sensor: alter Stand bleibt."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    detail = entry.runtime_data.details[next(iter(entry.subentries))]

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/pvp-bracket/3v3": 500})
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, "/pvp-bracket/3v3") == 1
    state = hass.states.get(_eid(hass, "sensor", "pvp_bracket_3v3"))
    assert state.state == "1850"


async def _refresh_detail(hass: HomeAssistant, entry, aioclient_mock, override=None):
    """Alle Abstaende zuruecksetzen und neu abfragen; zaehlt nur diese Runde."""
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, override)
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    return detail


async def test_brackets_without_sensor_not_asked_again(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """2v2 und rbg ohne Sensor (404 beim Start): danach keine Abfrage mehr."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    await _refresh_detail(hass, entry, aioclient_mock)
    assert _calls(aioclient_mock, "/pvp-bracket/3v3") == 1
    assert _calls(aioclient_mock, "/pvp-bracket/2v2") == 0
    assert _calls(aioclient_mock, "/pvp-bracket/rbg") == 0


async def test_no_pvp_no_bracket_queries(hass: HomeAssistant, aioclient_mock) -> None:
    """Kein Bracket mit Daten beim Start: Endpunkt faellt bis zum Neuladen weg."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/pvp-bracket/3v3": 404})
    entry = await _setup(hass)
    assert _calls(aioclient_mock, "/pvp-bracket/") == 3
    detail = await _refresh_detail(hass, entry, aioclient_mock)
    assert "pvp_brackets" not in detail.needed_endpoints()
    assert _calls(aioclient_mock, "/pvp-bracket/") == 0
    assert detail.last_update_success


async def test_bracket_with_sensor_asked_after_404(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Bracket mit Sensor: ein spaeterer 404 beendet die Abfrage nicht."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)
    await _refresh_detail(hass, entry, aioclient_mock, {f"{API}/pvp-bracket/3v3": 404})
    await _refresh_detail(hass, entry, aioclient_mock)
    assert _calls(aioclient_mock, "/pvp-bracket/3v3") == 1
    state = hass.states.get(_eid(hass, "sensor", "pvp_bracket_3v3"))
    assert state.state == "1850"


async def test_classic_queries_new_endpoints_and_class_names(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Classic: Aussehen, Brackets, Mitgliederliste und Klassennamen im Namespace."""
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            API: PROFILE_GUILD,
            GUILD: {"name": "Testgilde", "member_count": 1},
            f"{GUILD}/activity": {"activities": []},
            f"{GUILD}/roster": ROSTER,
            f"{GAME}/playable-class/8": {"id": 8, "name": "Magier"},
        },
    )
    sub = character_subentry("eu-profile-classic1x-eu-die-aldor-testchar")
    sub["data"] = {
        **sub["data"],
        "game_version": "classic_era",
        "namespace_suffix": "-classic1x",
    }
    entry = await _setup(hass, sub)
    uid = "eu-profile-classic1x-eu-die-aldor-testchar"

    urls = [str(call[1]) for call in aioclient_mock.mock_calls]
    for part, namespace in (
        ("/appearance?", "profile-classic1x-eu"),
        ("/pvp-bracket/3v3?", "profile-classic1x-eu"),
        ("/roster?", "profile-classic1x-eu"),
        ("/playable-class/8?", "static-classic1x-eu"),
    ):
        assert any(part in u and namespace in u for u in urls), part
    guild = hass.states.get(_eid(hass, "sensor", "guild", uid)).attributes
    assert guild["members"][0]["class"] == "Magier"
    assert _eid(hass, "sensor", "pvp_bracket_3v3", uid)

    diag = await async_get_config_entry_diagnostics(hass, entry)
    (character,) = diag["characters"].values()
    assert character["details"]["guild_roster"]["count"] == 1


async def test_class_names_looked_up_once(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            API: PROFILE_GUILD,
            GUILD: {"name": "Testgilde", "member_count": 1},
            f"{GUILD}/activity": {"activities": []},
            f"{GUILD}/roster": ROSTER,
            f"{GAME}/playable-class/8": {"id": 8, "name": "Magier"},
        },
    )
    entry = await _setup(hass)
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, "/playable-class/8?") == 1
    assert _calls(aioclient_mock, "/roster?") == 2


# Kopf nicht transmogrifiziert (ID wie der angelegte Helm 5001 aus EQUIPMENT),
# Waffenhand mit fremdem Aussehen.
APPEARANCE_ITEMS = {
    **APPEARANCE,
    "items": [
        {"id": 5001, "slot": {"type": "HEAD", "name": "Kopf"}, "enchant": 0},
        {"id": 7002, "slot": {"type": "MAIN_HAND", "name": "Waffenhand"}, "enchant": 0},
    ],
}


async def test_transmog_names_when_ids_are_item_ids(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{API}/appearance": APPEARANCE_ITEMS,
            f"{GAME}/item/7002": {"id": 7002, "name": "Transmog-Schwert"},
        },
    )
    entry = await _setup(hass)

    transmog = hass.states.get(_eid(hass, "sensor", "level")).attributes["transmog"]
    assert [t["name"] for t in transmog] == ["Testhelm", "Transmog-Schwert"]
    # Der Helm kommt aus der Ausruestung, nur das Schwert wird nachgeschlagen.
    assert _calls(aioclient_mock, "/data/wow/item/5001") == 0
    assert _calls(aioclient_mock, "/data/wow/item/7002") == 1

    # Namen bleiben gemerkt: keine zweite Abfrage.
    await _refresh_detail(
        hass,
        entry,
        aioclient_mock,
        {
            f"{API}/appearance": APPEARANCE_ITEMS,
            f"{GAME}/item/7002": {"id": 7002, "name": "Transmog-Schwert"},
        },
    )
    assert _calls(aioclient_mock, "/data/wow/item/") == 0


async def test_transmog_name_lookup_fails(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {f"{API}/appearance": APPEARANCE_ITEMS, f"{GAME}/item/7002": 404},
    )
    await _setup(hass)
    transmog = hass.states.get(_eid(hass, "sensor", "level")).attributes["transmog"]
    assert [t["name"] for t in transmog] == ["Testhelm", None]


async def test_transmog_names_classic(hass: HomeAssistant, aioclient_mock) -> None:
    """Classic: item/{id} steht in der Classic-Doku, static-Namespace der Version."""
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{API}/appearance": APPEARANCE_ITEMS,
            f"{GAME}/item/7002": {"id": 7002, "name": "Transmog-Schwert"},
        },
    )
    sub = character_subentry("eu-profile-classic1x-eu-die-aldor-testchar")
    sub["data"] = {
        **sub["data"],
        "game_version": "classic_era",
        "namespace_suffix": "-classic1x",
    }
    await _setup(hass, sub)
    urls = [str(call[1]) for call in aioclient_mock.mock_calls]
    assert any("/data/wow/item/7002?" in u and "static-classic1x-eu" in u for u in urls)
