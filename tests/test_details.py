"""Tests fuer die Werte aus Version 0.3: Details je Charakter und Spielwelt."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    ACHIEVEMENTS,
    API,
    GAME,
    RAIDS,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)


def _eid(hass: HomeAssistant, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, "wow_character", unique_id)


def _state(hass: HomeAssistant, platform: str, key: str, uid: str = UID1):
    entity_id = _eid(hass, platform, f"{uid}-{key}")
    assert entity_id, f"{platform} {key} fehlt"
    return hass.states.get(entity_id)


async def _setup(hass: HomeAssistant, *subentries):
    entry = main_entry(*subentries)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_retail_values(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, character_subentry())

    # Paket A: aus dem Profil und dem Mythic+-Profil
    assert _state(hass, "sensor", "item_level_average").state == "703"
    assert _state(hass, "sensor", "experience").state == "1500"
    assert (
        _state(hass, "sensor", "level").attributes["title"] == "Testchar der Champion"
    )
    assert _state(hass, "sensor", "mythic_rating").attributes["color"] == "#ff8000"

    # Raids: nur die neueste Erweiterung zaehlt, mit allen Raids des Journals
    # (ohne Weltbosse), Namen aus dem Journal
    heroic = _state(hass, "sensor", "raid_heroic")
    assert heroic.state == "6"
    assert heroic.attributes["expansion"] == "Neue Erweiterung (Journal)"
    assert heroic.attributes["total_bosses"] == 12
    assert heroic.attributes["raids"] == {
        "Neuer Raid (Journal)": "6/8",
        "Zweiter Raid": "0/4",
    }
    assert heroic.attributes["latest_raid"] == "Neuer Raid (Journal)"
    assert _state(hass, "sensor", "raid_mythic").state == "1"
    # LFR: nur Raids, die es in LFR gibt
    lfr = _state(hass, "sensor", "raid_lfr")
    assert lfr.state == "0"
    assert lfr.attributes["raids"] == {"Neuer Raid (Journal)": "0/8"}

    # Mythic+-Season 14 aus der Spielwelt, nicht die hoechste des Charakters
    assert _state(hass, "sensor", "mythic_best_key").state == "12"
    assert _state(hass, "sensor", "mythic_runs_timed").state == "2"

    assert _state(hass, "sensor", "honor_level").state == "50"
    assert _state(hass, "sensor", "honorable_kills").state == "1234"
    assert _state(hass, "sensor", "mounts").state == "3"
    assert _state(hass, "sensor", "pets").state == "2"
    assert _state(hass, "sensor", "toys").state == "1"

    # Beruf: Skill der neuesten Stufe
    prof = _state(hass, "sensor", "profession-164")
    assert prof.state == "42"
    # Stufen- und Berufsname aus den statischen Spieldaten
    assert prof.attributes["tier"] == "Neue Schmiedekunst (deutsch)"
    # Name aus den statischen Spieldaten statt des englischen der Berufe-Seite
    assert prof.name.endswith("Profession Schmiedekunst")

    # Bilder
    avatar = _state(hass, "image", "avatar")
    assert avatar is not None
    assert _state(hass, "image", "full_body") is not None

    # Werte sind angelegt, aber standardmaessig deaktiviert
    entry = er.async_get(hass).async_get(_eid(hass, "sensor", f"{UID1}-stat_crit"))
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # Spielwelt EU
    world = "id-world-eu"
    assert hass.states.get(_eid(hass, "sensor", f"{world}-token")).state == "345"
    assert (
        hass.states.get(_eid(hass, "sensor", f"{world}-weekly_reset")).state
        == "2025-10-28T07:00:00+00:00"
    )
    status = hass.states.get(
        _eid(hass, "binary_sensor", f"{world}-realm-die-aldor-status")
    )
    assert status.state == "on"
    assert status.name.endswith("Server Die Aldor")
    # Name des Realms als Attribut, fuer Karten (seit 0.33.9)
    assert status.attributes["realm"] == "Die Aldor"
    queue = _eid(hass, "binary_sensor", f"{world}-realm-die-aldor-queue")
    assert hass.states.get(queue).state == "off"
    assert hass.states.get(queue).attributes["realm"] == "Die Aldor"
    population = _eid(hass, "sensor", f"{world}-realm-die-aldor-population")
    # Zustand aus population.type, uebersetzt in strings.json (seit 0.22.0)
    assert hass.states.get(population).state == "high"
    assert hass.states.get(population).attributes["realm"] == "Die Aldor"
    assert hass.states.get(population).attributes["options"] == [
        "full",
        "high",
        "medium",
        "low",
        "recommended",
    ]


async def test_disabled_sensors_skip_endpoint(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())

    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    # Werte-Sensoren sind alle deaktiviert, also kein Abruf mehr.
    assert "statistics" not in detail.needed_endpoints()
    assert "raids" in detail.needed_endpoints()

    aioclient_mock.mock_calls.clear()
    detail._fetched.clear()
    await detail.async_refresh()
    urls = [str(call[1]) for call in aioclient_mock.mock_calls]
    assert not any("/statistics" in u for u in urls)
    assert any("/encounters/raids" in u for u in urls)


async def test_events_fire_only_for_new_entries(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    boss = _eid(hass, "event", f"{UID1}-boss_killed")
    achievement = _eid(hass, "event", f"{UID1}-new_achievement")
    # Alte Kills und Erfolge loesen beim Start nicht aus.
    assert hass.states.get(boss).state == "unknown"
    assert hass.states.get(achievement).state == "unknown"

    new_raids = {
        "expansions": [
            *RAIDS["expansions"][:1],
            {
                **RAIDS["expansions"][1],
                "instances": [
                    {
                        "instance": {"name": "Neuer Raid", "id": 9201},
                        "modes": [
                            {
                                "difficulty": {"type": "HEROIC", "name": "Heroisch"},
                                "progress": {
                                    "completed_count": 7,
                                    "total_count": 8,
                                    "encounters": [
                                        {
                                            "encounter": {"name": "Zweiter Boss"},
                                            "last_kill_timestamp": 1761500000000,
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            },
        ]
    }
    new_achievements = {
        **ACHIEVEMENTS,
        "recent_events": [
            *ACHIEVEMENTS["recent_events"],
            {"achievement": {"name": "Neuer Erfolg"}, "timestamp": 1761500000000},
        ],
    }
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {f"{API}/encounters/raids": new_raids, f"{API}/achievements": new_achievements},
    )
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(boss)
    assert state.attributes["event_type"] == "boss_killed"
    assert state.attributes["boss"] == "Zweiter Boss"
    assert state.attributes["difficulty"] == "Heroisch"
    state = hass.states.get(achievement)
    assert state.attributes["achievement"] == "Neuer Erfolg"
    assert _state(hass, "sensor", "raid_heroic").state == "7"


async def test_forever_creates_only_available(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    forever = character_subentry()
    forever["data"] = {
        **forever["data"],
        "game_version": "forever",
        "namespace_suffix": "-forever",
    }
    # Forever-Namespace: nur Profil und PvP antworten, Spielwelt kennt nur den Realm.
    not_found = {
        f"{API}/{path}": 404
        for path in (
            "encounters/raids",
            "statistics",
            "achievements",
            "professions",
            "collections/mounts",
            "collections/pets",
            "collections/toys",
            "character-media",
            "equipment",
            "reputations",
        )
    }
    not_found[f"{GAME}/token/index"] = 404
    mock_api(aioclient_mock, not_found)
    await _setup(hass, forever)

    assert _state(hass, "sensor", "level").state == "90"
    assert _state(hass, "sensor", "honor_level").state == "50"
    for platform, key in (
        ("sensor", "raid_heroic"),
        ("sensor", "mounts"),
        ("sensor", "mythic_best_key"),
        ("sensor", "mythic_rating"),
        ("event", "boss_killed"),
        ("image", "avatar"),
        ("sensor", "equipment_head"),
        ("sensor", "reputation"),
    ):
        assert _eid(hass, platform, f"{UID1}-{key}") is None, key
    world = "id-world-eu-forever"
    assert _eid(hass, "sensor", f"{world}-token") is None
    assert _eid(hass, "sensor", f"{world}-weekly_reset") is None
    assert _eid(hass, "binary_sensor", f"{world}-realm-die-aldor-status")


async def test_shared_realm_has_one_status(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    second_base = (
        "https://eu.api.blizzard.com/profile/wow/character/die-aldor/zweitchar"
    )
    mock_api(aioclient_mock)
    mock_api(aioclient_mock, base=second_base)
    second = character_subentry(
        "eu-profile-eu-die-aldor-zweitchar",
        "Zweitchar – Die Aldor",
        "die-aldor",
        "Zweitchar",
    )
    await _setup(hass, character_subentry(), second)

    statuses = [
        e
        for e in er.async_get(hass).entities.values()
        if e.unique_id.endswith("-status") and e.platform == "wow_character"
    ]
    assert len(statuses) == 1


async def test_diagnostics_hide_credentials(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["client_secret"] == "**REDACTED**"
    assert diag["entry"]["client_id"] == "**REDACTED**"
    char = diag["characters"]["Testchar – Die Aldor"]
    assert char["profile"]["profile"]["experience"] == 1500
    assert char["details"]["mounts"] == {"count": 3, "first": [{}, {}]}
    assert "statistics" not in char["needed_endpoints"]
    assert diag["worlds"]["eu"]["token"] == 345


async def test_events_do_not_repeat(hass: HomeAssistant, aioclient_mock) -> None:
    """Ohne neue Eintraege loest eine weitere Abfrage nichts aus."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    boss = _eid(hass, "event", f"{UID1}-boss_killed")
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    for _ in range(2):
        detail._fetched.clear()
        await detail.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(boss).state == "unknown"


def test_color_formats() -> None:
    from custom_components.wow_character.parsers import color_hex

    assert color_hex({"r": 255, "g": 128, "b": 0, "a": 1.0}) == "#ff8000"
    # Falls die API Anteile von 0 bis 1 liefert (ungeprueft), ebenfalls umrechnen.
    assert color_hex({"r": 1.0, "g": 0.5, "b": 0.0, "a": 1.0}) == "#ff8000"
    assert color_hex(None) is None


async def test_profession_name_fallback(hass: HomeAssistant, aioclient_mock) -> None:
    """Liefern die Spieldaten keinen Namen, bleibt der englische der Berufe-Seite."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {f"{GAME}/profession/164": 404})
    await _setup(hass, character_subentry())
    prof = _state(hass, "sensor", "profession-164")
    assert prof.state == "42"
    assert prof.name.endswith("Profession Blacksmithing")
    assert prof.attributes["tier"] == "Neue Schmiedekunst"


async def test_mythic_rating_only_for_current_season(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Spielte der Charakter die aktuelle Season nicht, ist die Wertung unbekannt."""
    mock_token(aioclient_mock)
    old_season = {
        "current_mythic_rating": {
            "rating": 170,
            "color": {"r": 255, "g": 255, "b": 255, "a": 0},
        },
        "seasons": [{"id": 13}],
    }
    mock_api(aioclient_mock, {f"{API}/mythic-keystone-profile": old_season})
    await _setup(hass, character_subentry())
    rating = _state(hass, "sensor", "mythic_rating")
    assert rating.state == "unknown"
    assert rating.attributes["season"] == 14
    assert rating.attributes["color"] is None
    # Rohwert wie im Arsenal bleibt als Attribut erhalten.
    assert rating.attributes["api_rating"] == 170


async def test_diagnostics_without_recipes(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    professions = {
        "primaries": [
            {
                "profession": {"id": 164, "name": "Blacksmithing"},
                "tiers": [
                    {
                        "tier": {"id": 1, "name": "Stufe"},
                        "skill_points": 5,
                        "known_recipes": [{"name": "Rezept"}],
                    }
                ],
            }
        ]
    }
    mock_api(aioclient_mock, {f"{API}/professions": professions})
    entry = await _setup(hass, character_subentry())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    details = diag["characters"]["Testchar – Die Aldor"]["details"]
    tier = details["professions"]["primaries"][0]["tiers"][0]
    assert "known_recipes" not in tier
    assert tier["skill_points"] == 5
    assert details["profession_names"] == {164: "Schmiedekunst"}


async def test_equipment(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())

    head = _state(hass, "sensor", "equipment_head")
    assert head.state == "253"
    assert head.name.endswith("Equipment head")
    assert head.attributes["entity_picture"] == "https://render.example/helm.jpg"
    assert head.attributes["name"] == "Testhelm"
    assert head.attributes["item_id"] == 5001
    assert head.attributes["quality"] == "EPIC"
    assert head.attributes["quality_name"] == "Episch"
    # Symbol-Steuerzeichen des Spiels werden entfernt.
    assert head.attributes["enchantments"] == ["Verzaubert: +16 Intelligenz"]
    assert head.attributes["sockets"] == [
        {"type": "PRISMATIC", "gem": "Testedelstein"},
        {"type": "PRISMATIC", "gem": None},
    ]
    assert head.attributes["set"] == "Testset"

    # Ohne Symbol von der API bleibt das Standard-Icon.
    weapon = _state(hass, "sensor", "equipment_main_hand")
    assert weapon.state == "259"
    assert "entity_picture" not in weapon.attributes
    assert weapon.attributes["enchantments"] == []

    # Leere Plaetze gibt es trotzdem, damit Karten feste Entitaeten haben.
    assert _state(hass, "sensor", "equipment_shirt").state == "unknown"
    slots = [
        e
        for e in er.async_get(hass).entities.values()
        if e.unique_id.startswith(f"{UID1}-equipment_")
    ]
    assert len(slots) == 18

    # Bekannte Symbole werden nicht erneut abgefragt, fehlende schon.
    aioclient_mock.mock_calls.clear()
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._fetched.clear()
    await detail.async_refresh()
    urls = [str(call[1]) for call in aioclient_mock.mock_calls]
    assert not any("/media/item/6001" in u for u in urls)
    assert any("/media/item/6002" in u for u in urls)


async def test_reputation(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, character_subentry())

    rep = _state(hass, "sensor", "reputation")
    assert rep.state == "2"
    assert rep.attributes["factions"] == [
        {
            "faction": "Testfraktion",
            "faction_id": 1091,
            "standing": "Ehrfürchtig",
            "value": 0,
            "max": 0,
            "paragon": {"value": 3000, "max": 10000},
        },
        {
            "faction": "Neue Fraktion",
            "faction_id": 2600,
            "standing": "Renommee 4",
            "value": 500,
            "max": 2500,
            "renown": 4,
        },
    ]


async def test_equipment_tooltip(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, character_subentry())

    tip = _state(hass, "sensor", "equipment_head").attributes["tooltip"]
    assert tip == {
        "name": "Testhelm",
        "quality": "EPIC",
        "quality_name": "Episch",
        "level": "Gegenstandsstufe 253",
        "binding": "Wird beim Aufheben gebunden",
        "slot": "Kopf",
        "subclass": "Stoff",
        "armor": "30 Rüstung",
        "stats": [
            {
                "text": "+91 Intelligenz",
                "color": "#ffffff",
                "bonus": False,
                "negated": False,
            },
            {"text": "+92 Tempo", "color": "#1eff00", "bonus": True, "negated": False},
        ],
        "enchantments": ["Verzaubert: +16 Intelligenz"],
        "sockets": ["Testedelstein", "Prismatischer Sockel"],
        "set": {
            "name": "Testset (1/2)",
            "items": [
                {"name": "Testhelm", "equipped": True},
                {"name": "Testhose", "equipped": False},
            ],
            "effects": [{"text": "Set: +5 Testwert", "active": False, "required": 2}],
        },
        "durability": "Haltbarkeit 96 / 100",
        "requirements": ["Klassen: Magier", "Benötigt Stufe 90"],
        "sell_price": {
            "header": "Verkaufspreis:",
            "gold": "42",
            "silver": "90",
            "copper": "73",
        },
    }

    # Waffe: Schaden, Tempo, DPS, Effekt; versteckte Unterklasse fehlt
    tip = _state(hass, "sensor", "equipment_main_hand").attributes["tooltip"]
    assert tip["damage"] == "100 - 200 Schaden"
    assert tip["speed"] == "Tempo 3,60"
    assert tip["dps"] == "(41,7 Schaden pro Sekunde)"
    assert tip["spells"] == ["Benutzen: Testeffekt stark"]
    assert "subclass" not in tip
    assert "set" not in tip

    # Leerer Platz: kein Tooltip
    assert _state(hass, "sensor", "equipment_shirt").attributes["tooltip"] is None


def test_tooltip_not_recorded() -> None:
    from custom_components.wow_character.sensor import WowEquipmentSensor

    assert "tooltip" in WowEquipmentSensor._unrecorded_attributes


def test_reputation_not_recorded() -> None:
    """Die lange Fraktionsliste kommt nicht in die Datenbank."""
    from custom_components.wow_character.sensor import WowReputationSensor

    assert "factions" in WowReputationSensor._unrecorded_attributes


async def test_diagnostics_equipment(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    diag = await async_get_config_entry_diagnostics(hass, entry)
    details = diag["characters"]["Testchar – Die Aldor"]["details"]
    head = details["equipment"]["equipped_items"][0]
    assert head["slot"]["type"] == "HEAD"
    # Volle Felder fuer die Pruefung, ohne Bonus-IDs
    assert head["stats"][0]["display"]["display_string"] == "+91 Intelligenz"
    assert "bonus_list" not in head
    assert details["reputations"]["count"] == 2
    assert details["item_icons"] == {6001: "https://render.example/helm.jpg"}


def test_clean_text() -> None:
    from custom_components.wow_character.parsers import clean_text

    assert clean_text("|cnGREEN_FONT_COLOR:+16 Intelligenz|r") == "+16 Intelligenz"
    assert clean_text("|cff1eff00Grün|r Text") == "Grün Text"
    assert clean_text("Ohne Steuerzeichen") == "Ohne Steuerzeichen"
    assert clean_text(None) is None


def test_icon_url() -> None:
    from custom_components.wow_character.parsers import icon_url

    assets = [
        {"key": "zoom", "value": "https://render.example/zoom.jpg"},
        {"key": "icon", "value": "https://render.example/icon.jpg"},
    ]
    assert icon_url({"assets": assets}) == "https://render.example/icon.jpg"
    # Ohne "icon" das erste Bild, ohne Bilder nichts.
    assert icon_url({"assets": assets[:1]}) == "https://render.example/zoom.jpg"
    assert icon_url({}) is None
