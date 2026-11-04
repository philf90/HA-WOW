"""Tests fuer 0.33.10: Reset in der Vergangenheit sofort neu abfragen."""

from homeassistant.core import HomeAssistant

from .conftest import GAME, character_subentry, main_entry, mock_api, mock_token

INDEX_URL = f"{GAME}/mythic-keystone/period/index"
PERIOD_URL = f"{GAME}/mythic-keystone/period/1001"
NEXT_URL = f"{GAME}/mythic-keystone/period/1002"
# 31.12.2099 23:59:59 UTC; Reset daraus eine Sekunde spaeter
FUTURE = 4102444799000
FUTURE_RESET = "2100-01-01T00:00:00+00:00"
# Mock-Reset aus conftest: 28.10.2025, also vorbei
PAST_RESET = "2025-10-28T07:00:00+00:00"
RESET_ENTITY = "sensor.wow_world_eu_weekly_reset"


async def _setup(hass: HomeAssistant, aioclient_mock, override: dict | None = None):
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, override)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _calls(aioclient_mock, url: str) -> int:
    return sum(1 for c in aioclient_mock.mock_calls if str(c[1]).startswith(url))


async def _next_run(hass: HomeAssistant, aioclient_mock, entry, override=None):
    """Naechster Lauf der Spielwelt (15 Minuten spaeter) mit neuen Antworten."""
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, override)
    (world,) = entry.runtime_data.worlds.values()
    for key in world._fetched:
        world._fetched[key] -= 15 * 60
    await world.async_refresh()
    await hass.async_block_till_done()


async def test_past_reset_asked_again(hass: HomeAssistant, aioclient_mock) -> None:
    """Reset vorbei: der naechste Lauf fragt den Zeitraum neu, nicht erst nach 1 h."""
    entry = await _setup(hass, aioclient_mock)
    assert hass.states.get(RESET_ENTITY).state == PAST_RESET

    # API meldet noch den alten Zeitraum: wieder gefragt, Wert bleibt
    await _next_run(hass, aioclient_mock, entry)
    assert _calls(aioclient_mock, INDEX_URL) == 1
    assert hass.states.get(RESET_ENTITY).state == PAST_RESET

    # Neuer Zeitraum da: Sensor springt beim naechsten Lauf um
    await _next_run(
        hass,
        aioclient_mock,
        entry,
        {
            INDEX_URL: {"current_period": {"id": 1002}},
            NEXT_URL: {"end_timestamp": FUTURE},
        },
    )
    assert _calls(aioclient_mock, INDEX_URL) == 1
    assert hass.states.get(RESET_ENTITY).state == FUTURE_RESET


async def test_future_reset_hourly(hass: HomeAssistant, aioclient_mock) -> None:
    """Reset noch nicht erreicht: wie bisher hoechstens einmal je Stunde."""
    future = {PERIOD_URL: {"end_timestamp": FUTURE}}
    entry = await _setup(hass, aioclient_mock, future)
    assert hass.states.get(RESET_ENTITY).state == FUTURE_RESET

    await _next_run(hass, aioclient_mock, entry, future)
    assert _calls(aioclient_mock, INDEX_URL) == 0
    assert _calls(aioclient_mock, f"{GAME}/token/index") == 0


async def test_past_reset_failure_keeps_value(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Scheitert die erneute Abfrage, bleibt der alte Reset und die Spielwelt laeuft."""
    entry = await _setup(hass, aioclient_mock)
    await _next_run(hass, aioclient_mock, entry, {INDEX_URL: 500})
    (world,) = entry.runtime_data.worlds.values()
    assert world.last_update_success
    assert hass.states.get(RESET_ENTITY).state == PAST_RESET
