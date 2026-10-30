"""Tests fuer 0.26.0: Charaktere starten parallel (W4)."""

import asyncio

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.wow_character.const import STARTUP_PARALLEL

from .conftest import PROFILE, character_subentry, main_entry, mock_api, mock_token

CHARACTER = "https://eu.api.blizzard.com/profile/wow/character/die-aldor"
NAMES = [f"Char{i}" for i in range(STARTUP_PARALLEL + 2)]


def _subentry(name: str):
    return character_subentry(
        f"eu-profile-eu-die-aldor-{name.lower()}",
        f"{name} – Die Aldor",
        "die-aldor",
        name,
    )


def _profile(method, url, name: str) -> AiohttpClientMockResponse:
    return AiohttpClientMockResponse(method, url, json={**PROFILE, "name": name})


async def _setup(hass: HomeAssistant, aioclient_mock, names: list[str]):
    """Charaktere mit eigenen Antworten; Profile vorher selbst nachstellen."""
    mock_token(aioclient_mock)
    for name in names:
        base = f"{CHARACTER}/{name.lower()}"
        # Status-Endpunkt (is_valid) fragt jeder Charakter beim Start ab.
        aioclient_mock.get(f"{base}/status", json={"id": 1, "is_valid": True})
        mock_api(aioclient_mock, base=base)
    entry = main_entry(*(_subentry(n) for n in names))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _level(hass: HomeAssistant, name: str) -> str:
    return hass.states.get(f"sensor.{name.lower()}_die_aldor_level").state


async def test_characters_start_in_parallel(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Das erste Profil wartet auf die Anfrage des zweiten; nacheinander hinge es."""
    second_asked = asyncio.Event()

    async def first(method, url, data):
        await asyncio.wait_for(second_asked.wait(), timeout=5)
        return _profile(method, url, "Char0")

    async def second(method, url, data):
        second_asked.set()
        return _profile(method, url, "Char1")

    aioclient_mock.get(f"{CHARACTER}/char0", side_effect=first)
    aioclient_mock.get(f"{CHARACTER}/char1", side_effect=second)
    entry = await _setup(hass, aioclient_mock, NAMES[:2])
    assert _level(hass, "Char0") == _level(hass, "Char1") == "90"
    # Reihenfolge der Untereintraege bleibt, auch wenn der zweite zuerst fertig ist.
    assert [c.subentry.title for c in entry.runtime_data.coordinators.values()] == [
        "Char0 – Die Aldor",
        "Char1 – Die Aldor",
    ]
    assert list(entry.runtime_data.details) == list(entry.runtime_data.coordinators)
    # Jeder Coordinator gehoert zu seinem Untereintrag.
    for runtime in (entry.runtime_data.coordinators, entry.runtime_data.details):
        assert all(c.subentry.subentry_id == sid for sid, c in runtime.items())


async def test_parallel_start_is_limited(hass: HomeAssistant, aioclient_mock) -> None:
    """Hoechstens STARTUP_PARALLEL Charaktere fragen zugleich ab."""
    running = {"now": 0, "max": 0}

    def slow(name: str):
        async def side_effect(method, url, data):
            running["now"] += 1
            running["max"] = max(running["max"], running["now"])
            for _ in range(10):
                await asyncio.sleep(0)
            running["now"] -= 1
            return _profile(method, url, name)

        return side_effect

    for name in NAMES:
        aioclient_mock.get(f"{CHARACTER}/{name.lower()}", side_effect=slow(name))
    await _setup(hass, aioclient_mock, NAMES)
    assert running["max"] == STARTUP_PARALLEL
    assert all(_level(hass, n) == "90" for n in NAMES)


async def test_failed_character_does_not_block_others(
    hass: HomeAssistant, aioclient_mock
) -> None:
    aioclient_mock.get(f"{CHARACTER}/char0", status=500)
    await _setup(hass, aioclient_mock, NAMES[:2])
    assert _level(hass, "Char0") == "unavailable"
    assert _level(hass, "Char1") == "90"


async def test_details_after_profile(hass: HomeAssistant, aioclient_mock) -> None:
    """Je Charakter erst das Profil, dann die Details (brauchen z. B. die Gilde)."""
    order: list[str] = []

    async def profile(method, url, data):
        for _ in range(20):
            await asyncio.sleep(0)
        order.append("profile")
        return _profile(method, url, "Char0")

    async def equipment(method, url, data):
        order.append("equipment")
        return AiohttpClientMockResponse(method, url, json={"equipped_items": []})

    aioclient_mock.get(f"{CHARACTER}/char0", side_effect=profile)
    aioclient_mock.get(f"{CHARACTER}/char0/equipment", side_effect=equipment)
    await _setup(hass, aioclient_mock, NAMES[:1])
    assert order[:2] == ["profile", "equipment"]
