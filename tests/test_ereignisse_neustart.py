"""Tests fuer 0.23.0: Ereignisse ueber Neustart und Neuladen hinweg (E6)."""

import copy
from datetime import timedelta

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import CoreState, Event, HomeAssistant, State, callback
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache_with_extra_data,
)

from .conftest import (
    API,
    PROFILE,
    RAIDS,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

BOSS = "event.testchar_die_aldor_boss_killed"
COLLECTIBLE = "event.testchar_die_aldor_new_collectible"
LEVEL = "event.testchar_die_aldor_level_up"
# Zustand eines Ereignisses vor dem Neustart mit seinen Attributen
OLD_STATE = "2026-10-29T10:00:00.000+00:00"


def _ms(delta: timedelta) -> int:
    """Zeitpunkt relativ zu jetzt in Millisekunden, wie die API ihn liefert."""
    return int((dt_util.utcnow() + delta).timestamp() * 1000)


def _iso(delta: timedelta) -> str:
    return (dt_util.utcnow() + delta).isoformat()


def _raids(kill: int) -> dict:
    """RAIDS mit dem letzten Kill von "Erster Boss" zum Zeitpunkt kill."""
    raids = copy.deepcopy(RAIDS)
    mode = raids["expansions"][1]["instances"][0]["modes"][0]
    mode["progress"]["encounters"][0]["last_kill_timestamp"] = kill
    return raids


def _restore(hass: HomeAssistant, entity_id: str, seen: dict | None) -> None:
    extra = {"last_event_type": "boss_killed", "last_event_attributes": {"boss": "Alt"}}
    if seen is not None:
        extra["wow_character"] = seen
    mock_restore_cache_with_extra_data(
        hass, [(State(entity_id, OLD_STATE, {"boss": "Alt"}), extra)]
    )


def _record(hass: HomeAssistant, entity_id: str) -> list[dict]:
    """Ausgeloeste Ereignisse: neue Zustaende mit event_type."""
    fired: list[dict] = []

    @callback
    def _listener(event: Event) -> None:
        new = event.data["new_state"]
        if (
            event.data["entity_id"] == entity_id
            and new is not None
            and new.state != OLD_STATE
            and new.state not in ("unknown", "unavailable")
        ):
            fired.append(dict(new.attributes))

    hass.bus.async_listen(EVENT_STATE_CHANGED, _listener)
    return fired


async def _setup(hass: HomeAssistant):
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# Bosskills und Erfolge


async def test_kill_during_restart_fires(hass: HomeAssistant, aioclient_mock) -> None:
    """Kill zwischen gespeichertem Stand und Start loest danach aus."""
    _restore(
        hass,
        BOSS,
        {"last": _ms(-timedelta(hours=2)), "saved": _iso(-timedelta(minutes=10))},
    )
    fired = _record(hass, BOSS)
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock, {f"{API}/encounters/raids": _raids(_ms(-timedelta(hours=1)))}
    )
    await _setup(hass)
    assert [(f["event_type"], f["boss"]) for f in fired] == [
        ("boss_killed", "Erster Boss")
    ]


async def test_old_kill_not_fired_after_restart(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Kills aelter als einen Tag loesen auch nach dem Neustart nicht aus."""
    _restore(
        hass,
        BOSS,
        {"last": _ms(-timedelta(days=3)), "saved": _iso(-timedelta(minutes=10))},
    )
    fired = _record(hass, BOSS)
    mock_token(aioclient_mock)
    raids = _raids(_ms(-timedelta(days=2)))
    mock_api(aioclient_mock, {f"{API}/encounters/raids": raids})
    entry = await _setup(hass)
    assert fired == []
    # Der Stand von Home Assistant (letztes Ereignis) bleibt erhalten.
    assert hass.states.get(BOSS).attributes["boss"] == "Alt"

    # Auch die naechste Abfrage loest fuer den alten Kill nicht aus.
    (detail,) = entry.runtime_data.details.values()
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert fired == []


async def test_stale_saved_state_ignored(hass: HomeAssistant, aioclient_mock) -> None:
    """Gespeicherter Stand aelter als einen Tag: wie vor 0.23.0 nichts nachholen."""
    _restore(
        hass,
        BOSS,
        {"last": _ms(-timedelta(hours=3)), "saved": _iso(-timedelta(days=2))},
    )
    fired = _record(hass, BOSS)
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock, {f"{API}/encounters/raids": _raids(_ms(-timedelta(hours=1)))}
    )
    await _setup(hass)
    assert fired == []


@pytest.mark.parametrize(
    "seen",
    [
        # Gueltiger Zeitpunkt, aber unbrauchbarer Stand: Fehler beim Lesen
        {"last": "kaputt"},
        {"last": None},
        # Ohne Stand
        {},
        # Kein Objekt
        ["kein", "Objekt"],
    ],
)
async def test_bad_saved_state_ignored(
    hass: HomeAssistant, aioclient_mock, seen
) -> None:
    """Unbrauchbarer Stand: wie ohne gespeicherten Stand, kein Fehler."""
    if isinstance(seen, dict):
        seen = {**seen, "saved": _iso(-timedelta(minutes=5))}
    _restore(hass, BOSS, seen)
    fired = _record(hass, BOSS)
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock, {f"{API}/encounters/raids": _raids(_ms(-timedelta(hours=1)))}
    )
    await _setup(hass)
    assert fired == []
    assert hass.states.get(BOSS) is not None


async def test_reload_keeps_state(hass: HomeAssistant, aioclient_mock) -> None:
    """Neuladen setzt den Stand nicht mehr zurueck (vorher ging der Kill verloren)."""
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {f"{API}/encounters/raids": _raids(_ms(-timedelta(days=1, hours=1)))},
    )
    entry = await _setup(hass)
    fired = _record(hass, BOSS)

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock, {f"{API}/encounters/raids": _raids(_ms(-timedelta(minutes=5)))}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert [f["boss"] for f in fired] == ["Erster Boss"]


async def test_restart_roundtrip(hass: HomeAssistant, aioclient_mock) -> None:
    """Gespeichert wird der Stand von Home Assistant und der eigene."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass)
    data = await async_mock_restore_state_shutdown_restart(hass)
    stored = data.last_states[BOSS].extra_data.as_dict()
    assert set(stored) == {"last_event_type", "last_event_attributes", "wow_character"}
    assert (
        stored["wow_character"]["last"]
        == RAIDS["expansions"][1]["instances"][0]["modes"][0]["progress"]["encounters"][
            0
        ]["last_kill_timestamp"]
    )
    saved = dt_util.parse_datetime(stored["wow_character"]["saved"])
    assert dt_util.utcnow() - saved < timedelta(minutes=1)
    level = data.last_states[LEVEL].extra_data.as_dict()["wow_character"]
    assert level["level"] == PROFILE["level"]


async def test_waits_until_started(hass: HomeAssistant, aioclient_mock) -> None:
    """Waehrend des Starts loest nichts aus; erst wenn Home Assistant laeuft."""
    saved = _iso(-timedelta(minutes=10))
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(BOSS, OLD_STATE),
                {
                    "last_event_type": "boss_killed",
                    "last_event_attributes": {},
                    "wow_character": {"last": _ms(-timedelta(hours=2)), "saved": saved},
                },
            ),
            (
                State(LEVEL, OLD_STATE),
                {
                    "last_event_type": "level_up",
                    "last_event_attributes": {},
                    "wow_character": {"level": 89, "saved": saved},
                },
            ),
        ],
    )
    fired = _record(hass, BOSS)
    levels = _record(hass, LEVEL)
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock, {f"{API}/encounters/raids": _raids(_ms(-timedelta(hours=1)))}
    )
    hass.set_state(CoreState.starting)
    await _setup(hass)
    assert fired == levels == []

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert [f["boss"] for f in fired] == ["Erster Boss"]
    # Ohne Abfrage danach: das Ereignis muss selbst geschrieben werden.
    assert [f["level"] for f in levels] == [PROFILE["level"]]


# Sammlungen und Level


async def test_collectible_during_restart_fires(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(COLLECTIBLE, OLD_STATE),
                {
                    "last_event_type": "mount",
                    "last_event_attributes": {},
                    "wow_character": {
                        "known": {"mounts": [6]},
                        "saved": _iso(-timedelta(hours=1)),
                    },
                },
            )
        ],
    )
    fired = _record(hass, COLLECTIBLE)
    mounts = {
        "mounts": [
            {"mount": {"name": "Braunes Pferd", "id": 6}},
            {"mount": {"name": "Rappe", "id": 9}},
        ]
    }
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{API}/collections/mounts": mounts})
    await _setup(hass)
    # Nur das neue Reittier; Haustiere und Spielzeuge ohne gespeicherten Stand
    # gelten wie bisher als bekannt.
    assert [(f["event_type"], f["name"]) for f in fired] == [("mount", "Rappe")]


async def test_level_during_restart_fires(hass: HomeAssistant, aioclient_mock) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(LEVEL, OLD_STATE),
                {
                    "last_event_type": "level_up",
                    "last_event_attributes": {"level": 89, "previous": 88},
                    "wow_character": {"level": 89, "saved": _iso(-timedelta(hours=1))},
                },
            )
        ],
    )
    fired = _record(hass, LEVEL)
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass)
    assert [(f["level"], f["previous"]) for f in fired] == [(PROFILE["level"], 89)]
