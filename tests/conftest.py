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
    "average_item_level": 703,
    "experience": 1500,
    "active_title": {"name": "Champion", "display_string": "{name} der Champion"},
}
PROFILE2 = {**PROFILE, "name": "Zweitchar", "level": 80, "realm": {"name": "Aegwynn"}}
MYTHIC = {
    "current_mythic_rating": {
        "rating": 2512.345,
        "color": {"r": 255, "g": 128, "b": 0, "a": 1.0},
    },
    # Hoechste Season des Charakters (15) weicht von der aktuellen (14) ab.
    "seasons": [{"id": 13}, {"id": 14}, {"id": 15}],
}

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


GAME = "https://eu.api.blizzard.com/data/wow"

# Detail-Antworten mit den Feldern, die parsers.py liest; Werte erfunden.
RAIDS = {
    "expansions": [
        {
            "expansion": {"id": 503, "name": "Alte Erweiterung"},
            "instances": [
                {
                    "instance": {"name": "Alter Raid"},
                    "modes": [
                        {
                            "difficulty": {"type": "HEROIC", "name": "Heroisch"},
                            "progress": {"completed_count": 9, "total_count": 9},
                        }
                    ],
                }
            ],
        },
        {
            "expansion": {"id": 514, "name": "Neue Erweiterung"},
            "instances": [
                {
                    "instance": {"name": "Neuer Raid"},
                    "modes": [
                        {
                            "difficulty": {"type": "HEROIC", "name": "Heroisch"},
                            "progress": {
                                "completed_count": 6,
                                "total_count": 8,
                                "encounters": [
                                    {
                                        "encounter": {"name": "Erster Boss"},
                                        "completed_count": 3,
                                        "last_kill_timestamp": 1761000000000,
                                    }
                                ],
                            },
                        },
                        {
                            "difficulty": {"type": "MYTHIC", "name": "Mythisch"},
                            "progress": {"completed_count": 1, "total_count": 8},
                        },
                    ],
                }
            ],
        },
    ]
}
MYTHIC_SEASON = {
    "best_runs": [
        {
            "dungeon": {"name": "Dungeon A"},
            "keystone_level": 12,
            "is_completed_within_time": True,
        },
        {
            "dungeon": {"name": "Dungeon B"},
            "keystone_level": 10,
            "is_completed_within_time": True,
        },
        {
            "dungeon": {"name": "Dungeon C"},
            "keystone_level": 11,
            "is_completed_within_time": False,
        },
    ]
}
PVP = {"honor_level": 50, "honorable_kills": 1234}
STATS = {
    "health": 500000,
    "strength": {"effective": 1000},
    "intellect": {"effective": 9000},
    "melee_crit": {"value": 10.5},
    "spell_crit": {"value": 25.123},
    "mastery": {"value": 40.0},
    "spell_haste": {"value": 20.0},
    "versatility_damage_done_bonus": 5.555,
}
ACHIEVEMENTS = {
    "total_points": 12345,
    "recent_events": [
        {"achievement": {"name": "Alter Erfolg"}, "timestamp": 1761000000000}
    ],
}
PROFESSIONS = {
    "primaries": [
        {
            "profession": {"id": 164, "name": "Blacksmithing"},
            "tiers": [
                {
                    "tier": {"id": 2822, "name": "Alte Schmiedekunst"},
                    "skill_points": 100,
                    "max_skill_points": 100,
                },
                {
                    "tier": {"id": 2872, "name": "Neue Schmiedekunst"},
                    "skill_points": 42,
                    "max_skill_points": 100,
                },
            ],
        }
    ]
}
MEDIA = {
    "assets": [
        {"key": "avatar", "value": "https://render.example/avatar.jpg"},
        {"key": "main-raw", "value": "https://render.example/main-raw.png"},
    ]
}

# Felder wie in den Typdefinitionen von @blizzard-api/wow und im Arsenal-Import
# von SimulationCraft; Werte erfunden.
EQUIPMENT = {
    "equipped_items": [
        {
            "item": {"id": 5001},
            "slot": {"type": "HEAD", "name": "Kopf"},
            "quality": {"type": "EPIC", "name": "Episch"},
            "name": "Testhelm",
            "media": {"id": 6001},
            "level": {"value": 253, "display_string": "Gegenstandsstufe 253"},
            "enchantments": [
                {
                    "display_string": "Verzaubert: +16 Intelligenz |A:Professions-ChatIcon-Quality-Tier2:20:20|a",
                    "enchantment_id": 7001,
                }
            ],
            "sockets": [
                {
                    "socket_type": {"type": "PRISMATIC"},
                    "item": {"name": "Testedelstein"},
                },
                {"socket_type": {"type": "PRISMATIC"}},
            ],
            "set": {"item_set": {"name": "Testset"}},
        },
        {
            "item": {"id": 5002},
            "slot": {"type": "MAIN_HAND", "name": "Waffenhand"},
            "quality": {"type": "RARE", "name": "Selten"},
            "name": "Teststab",
            "media": {"id": 6002},
            "level": {"value": 259},
        },
    ]
}
REPUTATIONS = {
    "reputations": [
        {
            "faction": {"name": "Testfraktion"},
            "standing": {
                "raw": 42000,
                "value": 0,
                "max": 0,
                "tier": 7,
                "name": "Ehrfürchtig",
            },
            "paragon": {"raw": 3000, "value": 3000, "max": 10000},
        },
        {
            "faction": {"name": "Neue Fraktion"},
            "standing": {
                "raw": 500,
                "value": 500,
                "max": 2500,
                "renown_level": 4,
                "name": "Renommee 4",
            },
        },
    ]
}


def mock_api(
    aioclient_mock: AiohttpClientMocker,
    override: dict | None = None,
    base: str = API,
) -> None:
    """Alle Antworten fuer einen Retail-Charakter und die Spielwelt EU nachstellen.

    override: volle URL -> Antwort (dict) oder HTTP-Status (int).
    """
    override = override or {}
    responses = {
        "": PROFILE,
        "/mythic-keystone-profile": MYTHIC,
        "/encounters/raids": RAIDS,
        "/mythic-keystone-profile/season/14": MYTHIC_SEASON,
        "/pvp-summary": PVP,
        "/statistics": STATS,
        "/achievements": ACHIEVEMENTS,
        "/professions": PROFESSIONS,
        "/collections/mounts": {"mounts": [{}, {}, {}]},
        "/collections/pets": {"pets": [{}, {}]},
        "/collections/toys": {"toys": [{}]},
        "/character-media": MEDIA,
        "/equipment": EQUIPMENT,
        "/reputations": REPUTATIONS,
    }
    world = {
        "/token/index": {"price": 3456789},
        "/mythic-keystone/period/index": {"current_period": {"id": 1001}},
        "/mythic-keystone/period/1001": {"end_timestamp": 1761634799000},
        "/mythic-keystone/season/index": {"current_season": {"id": 14}},
        "/realm/die-aldor": {
            "name": "Die Aldor",
            "connected_realm": {
                "href": "https://eu.api.blizzard.com/data/wow/connected-realm/1234?namespace=dynamic-eu"
            },
        },
        # Statische Spieldaten: deutscher Berufsname (Berufe-Seite liefert Englisch).
        "/profession/164": {"id": 164, "name": "Schmiedekunst"},
        # Symbole der Items; fuer 6002 liefert die API nichts.
        "/media/item/6001": {
            "assets": [{"key": "icon", "value": "https://render.example/helm.jpg"}]
        },
        "/media/item/6002": 404,
        "/connected-realm/1234": {
            "status": {"type": "UP"},
            "population": {"name": "Hoch", "type": "HIGH"},
            "has_queue": False,
        },
    }
    for path, body in {
        **{base + k: v for k, v in responses.items()},
        **{GAME + k: v for k, v in world.items()},
    }.items():
        body = override.get(path, body)
        if isinstance(body, int):
            aioclient_mock.get(path, status=body)
        else:
            aioclient_mock.get(path, json=body)
