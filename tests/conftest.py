"""Gemeinsame Fixtures: nachgebaute API-Antworten statt echter Abfragen."""

import pytest
from homeassistant.config_entries import ConfigSubentryData
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.wow_character.const import DOMAIN

TOKEN_URL = "https://oauth.battle.net/token"
REALMS_URL = "https://eu.api.blizzard.com/data/wow/realm/index"
API = "https://eu.api.blizzard.com/profile/wow/character/die-aldor/testchar"
API2 = "https://eu.api.blizzard.com/profile/wow/character/aegwynn/zweitchar"

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
PROFILE2 = {**PROFILE, "name": "Zweitchar", "level": 80, "realm": {"name": "Aegwynn"}}
MYTHIC = {"current_mythic_rating": {"rating": 2512.345}}

# Aufbau wie im Blizzard-Forum gezeigt: "realms" mit "name" und "slug".
REALMS = {
    "realms": [
        {"id": 1, "name": "Kult der Verdammten", "slug": "kult-der-verdammten"},
        {"id": 2, "name": "Die Aldor", "slug": "die-aldor"},
        {"id": 3, "name": "Aegwynn", "slug": "aegwynn"},
    ]
}

CREDENTIALS = {"client_id": "id", "client_secret": "secret"}
BASE_INPUT = {"region": "eu", "game_version": "retail"}
CHARACTER_INPUT = {"realm": "die-aldor", "character": "Testchar"}
UID1 = "eu-profile-eu-die-aldor-testchar"
UID2 = "eu-profile-eu-aegwynn-zweitchar"


def character_subentry(
    uid: str = UID1,
    title: str = "Testchar – Die Aldor",
    realm: str = "die-aldor",
    character: str = "Testchar",
) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={
            **BASE_INPUT,
            "realm": realm,
            "character": character,
            "namespace_suffix": "",
        },
        subentry_type="character",
        title=title,
        unique_id=uid,
    )


def main_entry(*subentries: ConfigSubentryData) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Battle.net API",
        unique_id="id",
        data=CREDENTIALS,
        subentries_data=list(subentries),
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def mock_token(aioclient_mock: AiohttpClientMocker, status: int = 200) -> None:
    aioclient_mock.post(
        TOKEN_URL,
        status=status,
        json={"access_token": "tok", "token_type": "bearer", "expires_in": 86399},
    )
