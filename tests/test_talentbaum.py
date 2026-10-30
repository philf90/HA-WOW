"""Tests fuer den Sensor "Talentbaum" (Retail).

Aufbau wie die echte Antwort vom 28.10.2026 (Magier, Frost): Baum der
Spezialisierung mit class_talent_nodes, spec_talent_nodes (darin auch die
Knoten der Heldenbaeume), hero_talent_trees und restriction_lines; IDs und
Namen erfunden.
"""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.wow_character import parsers as p
from custom_components.wow_character.api import BattleNetClient, BattleNetRateLimited

from .conftest import (
    API,
    GAME,
    SPECIALIZATIONS,
    UID1,
    character_subentry,
    mock_api,
    mock_token,
)
from .test_classic import _classic_subentry
from .test_details import _eid, _setup, _state

TREE_PATH = "talent-tree/790/playable-specialization/64"


def _node(node_id, row, col, talents, ranks=1, kind="PASSIVE", unlocks=None):
    """Knoten; talents: [(Talent-ID, Spell-ID, Name)], mehrere = Wahlknoten."""
    tooltips = [
        {
            "talent": {"id": t},
            "spell_tooltip": {
                "spell": {"id": s, "name": n},
                "description": f"{n}: Beschreibung.",
            },
        }
        for t, s, n in talents
    ]
    if not talents:
        rank_list = [{"rank": 1}]
    elif len(tooltips) > 1:
        rank_list = [{"rank": 1, "choice_of_tooltips": tooltips}]
    else:
        rank_list = [{"rank": r + 1, "tooltip": tooltips[0]} for r in range(ranks)]
    return {
        "id": node_id,
        "display_row": row,
        "display_col": col,
        "node_type": {"type": "CHOICE" if len(talents) > 1 else kind},
        "ranks": rank_list,
        "unlocks": unlocks,
    }


HERO_A = [_node(900, 1, 10, [(9000, 19000, "Held A")])]
HERO_B = [_node(910, 1, 22, [(9100, 19100, "Held B")])]
TREE = {
    "name": "Frost",
    "class_talent_nodes": [
        _node(100, 1, 4, [(1000, 11000, "Klasse 1")], kind="ACTIVE", unlocks=[101]),
        # Wahl des Heldenbaums: Knoten ohne Talent
        _node(199, 1, 12, []),
        _node(101, 2, 4, [(1010, 11010, "Wahl 1"), (1011, 11011, "Wahl 2")]),
        _node(102, 2, 5, [(1020, 11020, "Klasse 2")], ranks=2),
    ],
    # Wie in der echten Antwort stehen Heldenknoten auch hier.
    "spec_talent_nodes": [
        _node(200, 1, 18, [(2000, 12000, "Spez 1")], kind="ACTIVE"),
        _node(210, 11, 18, [(2100, 12100, "Spitze")]),
        *HERO_A,
        *HERO_B,
    ],
    "hero_talent_trees": [
        {"id": 40, "name": "Held A", "hero_talent_nodes": HERO_A},
        {"id": 41, "name": "Held B", "hero_talent_nodes": HERO_B},
    ],
    "restriction_lines": [
        {"required_points": 8, "restricted_row": 4.5, "is_for_class": True},
        {"required_points": 20, "restricted_row": 7.5, "is_for_class": False},
    ],
}
SPELLS = (11000, 11010, 11011, 11020, 12000, 12100, 19000)
# Weitere Stufen des Apex-Knotens: nur im Profil, nicht im Baum
STAGE_SPELLS = (12101, 12102)


def _taken(node_id, talent_id, rank=1, spell=None):
    tooltip = {"talent": {"id": talent_id}}
    if spell:
        tooltip["spell_tooltip"] = {
            "spell": {"id": spell[0], "name": spell[1]},
            "description": f"{spell[1]}: Stufe.",
        }
    return {"id": node_id, "rank": rank, "tooltip": tooltip}


# Apex wie Knoten 110422 der echten Antwort: dreimal, Abschluss, Mitte (Rang 2),
# erste Stufe
APEX_TAKEN = [
    _taken(210, 2102, 1, (12102, "Spitze Abschluss")),
    _taken(210, 2101, 2, (12101, "Spitze Mitte")),
    _taken(210, 2100, 1, (12100, "Spitze")),
]


def _specs(apex=APEX_TAKEN) -> dict:
    specs = {
        **SPECIALIZATIONS,
        "specializations": list(SPECIALIZATIONS["specializations"]),
    }
    frost = specs["specializations"][1]
    active = {
        **frost["loadouts"][1],
        "selected_class_talent_tree": {
            "key": {"href": f"{GAME}/talent-tree/790?namespace=static-eu"}
        },
        "selected_spec_talent_tree": {
            "key": {"href": f"{GAME}/{TREE_PATH}?namespace=static-eu"}
        },
        "selected_hero_talent_tree": {"id": 40, "name": "Held A"},
        "selected_class_talents": [
            _taken(100, 1000),
            _taken(199, None),
            _taken(101, 1011),
            _taken(102, 1020, 2),
        ],
        "selected_spec_talents": [_taken(200, 2000), *apex],
        "selected_hero_talents": [_taken(900, 9000)],
    }
    specs["specializations"][1] = {**frost, "loadouts": [frost["loadouts"][0], active]}
    return specs


def _media(spell_id: int) -> dict:
    return {
        "assets": [{"key": "icon", "value": f"https://render.example/{spell_id}.jpg"}]
    }


def _mock(aioclient_mock, apex=APEX_TAKEN, **extra) -> None:
    mock_token(aioclient_mock)
    mock_api(
        aioclient_mock,
        {
            f"{API}/specializations": _specs(apex),
            f"{GAME}/{TREE_PATH}": TREE,
            **{f"{GAME}/media/spell/{i}": _media(i) for i in (*SPELLS, *STAGE_SPELLS)},
            **extra,
        },
    )


def _calls(aioclient_mock, part: str) -> int:
    return sum(1 for call in aioclient_mock.mock_calls if part in str(call[1]))


async def test_talent_tree(hass: HomeAssistant, aioclient_mock) -> None:
    _mock(aioclient_mock)
    await _setup(hass, character_subentry())

    state = _state(hass, "sensor", "talent_tree")
    assert state.state == "Frost"
    attrs = state.attributes
    assert attrs["hero"] == "Held A"
    # Knoten ohne Talent faellt weg
    assert [n["id"] for n in attrs["class_nodes"]] == [100, 101, 102]
    first, choice, double = attrs["class_nodes"]
    assert first == {
        "id": 100,
        "row": 1,
        "col": 4,
        "type": "ACTIVE",
        "max_rank": 1,
        "rank": 1,
        "talent": 1000,
        "talents": [
            {
                "id": 1000,
                "name": "Klasse 1",
                "spell_id": 11000,
                "description": "Klasse 1: Beschreibung.",
                "icon": "https://render.example/11000.jpg",
            }
        ],
        "unlocks": [101],
    }
    assert (choice["type"], choice["talent"]) == ("CHOICE", 1011)
    assert [t["id"] for t in choice["talents"]] == [1010, 1011]
    assert (double["rank"], double["max_rank"]) == (2, 2)
    # Heldenknoten nicht im Baum der Spezialisierung, nur der aktive Heldenbaum
    assert [n["id"] for n in attrs["spec_nodes"]] == [200, 210]
    assert [n["id"] for n in attrs["hero_nodes"]] == [900]
    assert attrs["hero_nodes"][0]["rank"] == 1
    assert attrs["gates"] == [
        {"tree": "class", "row": 4.5, "points": 8},
        {"tree": "spec", "row": 7.5, "points": 20},
    ]


def _apex(hass):
    spec_nodes = _state(hass, "sensor", "talent_tree").attributes["spec_nodes"]
    return next(n for n in spec_nodes if n["id"] == 210)


async def test_apex_stages(hass: HomeAssistant, aioclient_mock) -> None:
    """Apex: Raenge aller Stufen zusammen, hoechstens 4; erste Stufe zuerst."""
    _mock(aioclient_mock)
    await _setup(hass, character_subentry())

    apex = _apex(hass)
    assert (apex["rank"], apex["max_rank"], apex["talent"]) == (4, 4, 2100)
    assert apex["stages"] == [
        {
            "id": 2100,
            "name": "Spitze",
            "spell_id": 12100,
            "description": "Spitze: Beschreibung.",
            "icon": "https://render.example/12100.jpg",
            "rank": 1,
        },
        {
            "id": 2101,
            "name": "Spitze Mitte",
            "spell_id": 12101,
            "description": "Spitze Mitte: Stufe.",
            "icon": "https://render.example/12101.jpg",
            "rank": 2,
        },
        {
            "id": 2102,
            "name": "Spitze Abschluss",
            "spell_id": 12102,
            "description": "Spitze Abschluss: Stufe.",
            "icon": "https://render.example/12102.jpg",
            "rank": 1,
        },
    ]
    # Andere Knoten unveraendert, ohne Stufen
    spec_nodes = _state(hass, "sensor", "talent_tree").attributes["spec_nodes"]
    assert "stages" not in spec_nodes[0]
    assert (spec_nodes[0]["rank"], spec_nodes[0]["max_rank"]) == (1, 1)


@pytest.mark.parametrize(
    ("taken", "rank", "talent", "stage_ranks"),
    [
        ([], 0, None, [0]),
        ([_taken(210, 2100, 1, (12100, "Spitze"))], 1, 2100, [1]),
    ],
)
async def test_apex_partly_or_not_taken(
    hass: HomeAssistant, aioclient_mock, taken, rank, talent, stage_ranks
) -> None:
    """Ohne oder mit nur der ersten Stufe: Hoechstzahl bleibt 4."""
    _mock(aioclient_mock, apex=taken)
    await _setup(hass, character_subentry())

    apex = _apex(hass)
    assert (apex["rank"], apex["max_rank"], apex["talent"]) == (rank, 4, talent)
    assert [s["rank"] for s in apex["stages"]] == stage_ranks


def test_apex_only_single_node_in_last_row() -> None:
    """Stehen mehrere Knoten in der untersten Zeile, gibt es keinen Apex."""
    tree = {
        **TREE,
        "spec_talent_nodes": [
            *TREE["spec_talent_nodes"],
            _node(211, 11, 20, [(2110, 12110, "Nachbar")]),
        ],
    }
    built = p.talent_tree(tree, {}, 40, {})
    assert all("stages" not in n for n in built["spec_nodes"])
    assert next(n for n in built["spec_nodes"] if n["id"] == 210)["max_rank"] == 1
    assert p.tree_spell_ids(tree, 40) == [
        11000,
        11010,
        11011,
        11020,
        12000,
        12100,
        12110,
        19000,
    ]


async def test_tree_once_icons_after_start(hass: HomeAssistant, aioclient_mock) -> None:
    """Baum einmal je Start; Symbole einmal je Talent, erst nach dem Anlegen."""
    _mock(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    # Symbole auch fuer die Apex-Stufen aus dem Profil
    spells = len(SPELLS) + len(STAGE_SPELLS)
    assert _calls(aioclient_mock, "/talent-tree/") == 1
    assert _calls(aioclient_mock, "/media/spell/") == spells

    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, "/talent-tree/") == 1
    assert _calls(aioclient_mock, "/media/spell/") == spells


async def test_tree_without_icons_before_entities(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Der erste Abruf beim Start fragt keine Symbole ab."""
    _mock(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail.entities_ready = False
    detail._media._urls.clear()
    before = _calls(aioclient_mock, "/media/spell/")
    await detail.async_refresh()
    assert _calls(aioclient_mock, "/media/spell/") == before
    assert detail.data["talent_tree"]["class_nodes"][0]["talents"][0]["icon"] is None


async def test_tree_error_is_retried(hass: HomeAssistant, aioclient_mock) -> None:
    _mock(aioclient_mock, **{f"{GAME}/{TREE_PATH}": 500})
    entry = await _setup(hass, character_subentry())
    assert _state(hass, "sensor", "talent_tree").state == "unknown"

    aioclient_mock.clear_requests()
    _mock(aioclient_mock)
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", "talent_tree").state == "Frost"


async def test_tree_error_logged_once(
    hass: HomeAssistant, aioclient_mock, caplog: pytest.LogCaptureFixture
) -> None:
    """Fehlt der Baum, steht das einmal als Warnung im Log, die Erholung als Info."""
    _mock(aioclient_mock, **{f"{GAME}/{TREE_PATH}": 500})
    entry = await _setup(hass, character_subentry())
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    warnings = [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "Talentbaum" in r.getMessage()
    ]
    assert len(warnings) == 1
    assert "Testchar – Die Aldor" in warnings[0].getMessage()
    assert TREE_PATH in warnings[0].getMessage()

    # Scheitert er erneut: keine zweite Warnung
    caplog.clear()
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert not [r for r in caplog.records if r.levelname == "WARNING"]

    # Kommt er wieder: eine Info, danach nichts mehr
    aioclient_mock.clear_requests()
    _mock(aioclient_mock)
    caplog.clear()
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    infos = [
        r.getMessage()
        for r in caplog.records
        if r.levelname == "INFO" and "Talentbaum" in r.getMessage()
    ]
    assert infos == [
        f"Talentbaum von Testchar – Die Aldor wieder geladen ({TREE_PATH})"
    ]
    assert _state(hass, "sensor", "talent_tree").state == "Frost"


async def test_disabled_sensor_skips_tree(hass: HomeAssistant, aioclient_mock) -> None:
    _mock(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    er.async_get(hass).async_update_entity(
        _eid(hass, "sensor", f"{UID1}-talent_tree"),
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    detail._talent_trees.clear()
    detail._fetched.clear()
    calls = _calls(aioclient_mock, "/talent-tree/")
    await detail.async_refresh()
    assert _calls(aioclient_mock, "/talent-tree/") == calls
    assert detail.data["talent_tree"] is None


async def test_classic_has_no_talent_tree(hass: HomeAssistant, aioclient_mock) -> None:
    """Classic kennt laut Doku keine Talent-Endpunkte."""
    _mock(aioclient_mock)
    await _setup(hass, _classic_subentry())
    uid = "eu-profile-classic1x-eu-die-aldor-testchar"
    assert _eid(hass, "sensor", f"{uid}-talent_tree") is None
    assert _calls(aioclient_mock, "/talent-tree/") == 0


async def test_tree_keeps_specializations_needed(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Auch ohne Sensor "Spezialisierung" bleibt der Endpunkt aktuell."""
    _mock(aioclient_mock)
    entry = await _setup(hass, character_subentry())
    er.async_get(hass).async_update_entity(
        _eid(hass, "sensor", f"{UID1}-specialization"),
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    detail = entry.runtime_data.details[next(iter(entry.subentries))]
    assert "specializations" in detail.needed_endpoints()


async def _limited(method, url, data):
    return AiohttpClientMockResponse(method, url, status=429)


def _ok_after(times: int, body: dict):
    """Erst times-mal 429, danach die Antwort."""
    calls = {"n": 0}

    async def respond(method, url, data):
        calls["n"] += 1
        if calls["n"] <= times:
            return AiohttpClientMockResponse(method, url, status=429)
        return AiohttpClientMockResponse(method, url, json=body)

    return respond


async def test_rate_limit_waits_and_retries(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """429 laut Blizzard-Doku bis zum Ende der Sekunde: eine Sekunde warten."""
    mock_token(aioclient_mock)
    url = f"{GAME}/media/spell/11000"
    mock_api(aioclient_mock, {f"{API}/specializations": _specs()})
    aioclient_mock.get(url, side_effect=_ok_after(1, _media(11000)))
    client = BattleNetClient(async_get_clientsession(hass), "id", "secret")
    with patch("custom_components.wow_character.api.asyncio.sleep") as sleep:
        media = await client.get_static_data("eu", "", "media/spell/11000")
    assert media == _media(11000)
    sleep.assert_awaited_once_with(1)
    assert _calls(aioclient_mock, "/media/spell/11000") == 2


async def test_rate_limit_twice_raises(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    aioclient_mock.get(f"{GAME}/media/spell/11000", side_effect=_limited)
    client = BattleNetClient(async_get_clientsession(hass), "id", "secret")
    with (
        patch("custom_components.wow_character.api.asyncio.sleep"),
        pytest.raises(BattleNetRateLimited),
    ):
        await client.get_static_data("eu", "", "media/spell/11000")
    assert _calls(aioclient_mock, "/media/spell/11000") == 2


async def test_icons_stop_at_rate_limit(hass: HomeAssistant, aioclient_mock) -> None:
    """Noch am Limit nach der Pause: keine weiteren Symbole bis zum naechsten Takt."""
    _mock(aioclient_mock, **{f"{GAME}/media/spell/{i}": 500 for i in SPELLS})
    entry = await _setup(hass, character_subentry())
    detail = entry.runtime_data.details[next(iter(entry.subentries))]

    aioclient_mock.clear_requests()
    _mock(aioclient_mock, **{f"{GAME}/media/spell/{i}": 429 for i in SPELLS})
    detail._fetched.clear()
    with patch("custom_components.wow_character.api.asyncio.sleep"):
        await detail.async_refresh()
    # Erstes Symbol zweimal (mit Pause), danach Abbruch
    assert _calls(aioclient_mock, "/media/spell/") == 2

    aioclient_mock.clear_requests()
    _mock(aioclient_mock)
    detail._fetched.clear()
    await detail.async_refresh()
    await hass.async_block_till_done()
    assert _calls(aioclient_mock, "/media/spell/") == len(SPELLS)
    icons = [
        t["icon"]
        for n in detail.data["talent_tree"]["class_nodes"]
        for t in n["talents"]
    ]
    assert all(icons)


async def test_item_icons_stop_at_rate_limit(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Auch Item-Symbole: nach erneutem 429 Abbruch bis zum naechsten Takt."""
    mock_token(aioclient_mock)
    limited = {f"{GAME}/media/item/{i}": 429 for i in (6001, 6002)}
    mock_api(aioclient_mock, limited)
    with patch("custom_components.wow_character.api.asyncio.sleep"):
        await _setup(hass, character_subentry())
    # Erstes Item zweimal (mit Pause), das zweite nicht mehr
    assert _calls(aioclient_mock, "/media/item/6001") == 2
    assert _calls(aioclient_mock, "/media/item/6002") == 0
