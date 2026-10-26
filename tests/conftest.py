"""Gemeinsame Fixtures: nachgebaute API-Antworten statt echter Abfragen."""

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

TOKEN_URL = "https://eu.battle.net/oauth/token"
REALMS_URL = "https://eu.api.blizzard.com/data/wow/realm/index"
API = "https://eu.api.blizzard.com/profile/wow/character/die-aldor/testchar"

# Felder wie im Referenzprojekt homeassistant-wow-blizzard ausgelesen;
# Werte sind erfunden.
PROFILE = {
    "name": "Testchar",
    "level": 90,
    "equipped_item_level": 701,
    "achievement_points": 12345,
    "last_login_timestamp": 1761400000000,
    "character_class": {"name": "Magier"},
    "active_spec": {"name": "Frost"},
    "race": {"name": "Mensch"},
    "faction": {"name": "Allianz"},
    "guild": {"name": "Testgilde"},
    "realm": {"name": "Die Aldor"},
}
MYTHIC = {"current_mythic_rating": {"rating": 2512.345}}

# Aufbau wie im Blizzard-Forum gezeigt: "realms" mit "name" und "slug".
REALMS = {
    "realms": [
        {"id": 1, "name": "Kult der Verdammten", "slug": "kult-der-verdammten"},
        {"id": 2, "name": "Die Aldor", "slug": "die-aldor"},
        {"id": 3, "name": "Aegwynn", "slug": "aegwynn"},
    ]
}

USER_INPUT = {
    "client_id": "id",
    "client_secret": "secret",
    "region": "eu",
    "game_version": "retail",
}
CHARACTER_INPUT = {"realm": "die-aldor", "character": "Testchar"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def mock_token(aioclient_mock: AiohttpClientMocker, status: int = 200) -> None:
    aioclient_mock.post(
        TOKEN_URL,
        status=status,
        json={"access_token": "tok", "token_type": "bearer", "expires_in": 86399},
    )
