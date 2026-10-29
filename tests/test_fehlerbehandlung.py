"""Tests fuer 0.19.1: Token-Abruf, kaputte Antworten und Berufsnamen (W1, W2)."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.wow_character.api import BattleNetClient, BattleNetError
from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    GAME,
    PROFESSIONS,
    TOKEN_URL,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

LEVEL = "sensor.testchar_die_aldor_level"


def _calls(aioclient_mock, part: str) -> int:
    return sum(1 for call in aioclient_mock.mock_calls if part in str(call[1]))


async def _setup(hass: HomeAssistant):
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# W2: Token


async def test_concurrent_requests_fetch_one_token(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Laeuft das Token ab, holen gleichzeitige Abfragen nur eines."""

    async def token(method, url, data):
        # Abgeben, damit die anderen Abfragen waehrenddessen anlaufen.
        await asyncio.sleep(0)
        body = {"access_token": "tok", "expires_in": 86399}
        return AiohttpClientMockResponse(method, url, 200, json=body)

    aioclient_mock.post(TOKEN_URL, side_effect=token)
    client = BattleNetClient(async_get_clientsession(hass), "id", "secret")
    tokens = await asyncio.gather(*(client._get_token() for _ in range(5)))
    assert tokens == ["tok"] * 5
    assert _calls(aioclient_mock, TOKEN_URL) == 1


@pytest.mark.parametrize(
    "answer",
    [
        {"json": {"token_type": "bearer"}},  # ohne access_token
        {"json": ["tok"]},  # kein JSON-Objekt
        {"text": "<html>Wartung</html>"},  # kein JSON
    ],
)
async def test_bad_token_answer(hass: HomeAssistant, aioclient_mock, answer) -> None:
    """Unbrauchbare Token-Antwort: BattleNetError statt KeyError oder ValueError."""
    aioclient_mock.post(TOKEN_URL, **answer)
    client = BattleNetClient(async_get_clientsession(hass), "id", "secret")
    with pytest.raises(BattleNetError):
        await client.validate()


async def test_bad_token_answer_retries_setup(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Beim Start fuehrt eine Token-Antwort ohne Token zu einem neuen Versuch."""
    aioclient_mock.post(TOKEN_URL, json={"token_type": "bearer"})
    entry = await _setup(hass)
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY


# W2: kaputte Antworten der API


@pytest.mark.parametrize(
    "answer",
    [{"text": "<html>Wartung</html>"}, {"json": ["kein", "Objekt"]}],
)
async def test_bad_profile_answer(
    hass: HomeAssistant, aioclient_mock, caplog: pytest.LogCaptureFixture, answer
) -> None:
    """Kein JSON-Objekt: gewoehnlicher Abfragefehler, kein Traceback im Log."""
    mock_token(aioclient_mock)
    for url, body in {API: answer}.items():
        aioclient_mock.get(url, **body)
    mock_api(aioclient_mock)
    await _setup(hass)
    assert hass.states.get(LEVEL).state == "unavailable"
    assert "Unexpected error" not in caplog.text
    assert "Antwort ist kein JSON" in caplog.text


# W1: Berufsnamen


async def test_profession_lookup_auth_error_starts_reauth(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Abgelehnte Zugangsdaten beim Nachschlagen der Berufsnamen: erneut anmelden."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/profession/164": 401})
    await _setup(hass)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_profession_lookup_stops_at_rate_limit(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Bleibt es nach der Pause bei 429, schlaegt sie die uebrigen Berufe nicht nach."""
    second = {
        "profession": {"id": 333, "name": "Enchanting"},
        "tiers": [{"tier": {"id": 1, "name": "Tier"}, "skill_points": 5}],
    }
    professions = {"primaries": [*PROFESSIONS["primaries"], second]}
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{API}/professions": professions,
            f"{GAME}/profession/164": 429,
            f"{GAME}/profession/333": {"id": 333, "name": "Verzauberkunst"},
            f"{GAME}/media/profession/333": 404,
        },
    )
    # Die Pause nach dem ersten 429 nicht wirklich abwarten.
    with patch("custom_components.wow_character.api.asyncio.sleep"):
        entry = await _setup(hass)
    assert entry.state is config_entries.ConfigEntryState.LOADED
    # Nur die Spieldaten der Berufe, nicht ihre Symbole unter /media/
    assert _calls(aioclient_mock, f"{GAME}/profession/164?") == 2
    assert _calls(aioclient_mock, f"{GAME}/profession/333?") == 0


@pytest.mark.parametrize("answer", [{"text": "<html>Wartung</html>"}, {"json": []}])
async def test_bad_login_code_answer(
    hass: HomeAssistant, aioclient_mock, answer
) -> None:
    """Code-Tausch der Battle.net-Anmeldung: kaputte Antwort als BattleNetError."""
    aioclient_mock.post(TOKEN_URL, **answer)
    client = BattleNetClient(async_get_clientsession(hass), "id", "secret")
    with pytest.raises(BattleNetError):
        await client.exchange_code("abcd", "https://example/redirect")
