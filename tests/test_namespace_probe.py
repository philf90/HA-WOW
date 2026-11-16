"""Tests fuer 0.34.0: Aktion probe_namespaces (Forever-Namespaces pruefen)."""

from pathlib import Path

import pytest
import voluptuous as vol
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.wow_character import probe, services
from custom_components.wow_character.const import DOMAIN, REGIONS, TOKEN_URL

from .conftest import character_subentry, main_entry, mock_api, mock_token

STATIC = "/data/wow/playable-class/index"
DYNAMIC = "/data/wow/realm/index"
NOT_FOUND = '{"code":404,"type":"BLZWEBAPI00000404","detail":"Not Found"}'
CLASSES = {
    "_links": {"self": {"href": "https://eu.api.blizzard.com/data/wow/..."}},
    "classes": [
        {"key": {"href": "x"}, "name": "Krieger", "id": 1},
        {"key": {"href": "x"}, "name": "Paladin", "id": 2},
        {"key": {"href": "x"}, "name": "Jäger", "id": 3},
        {"key": {"href": "x"}, "name": "Schurke", "id": 4},
    ],
}
REALMS = {
    "_links": {},
    "realms": [
        {"id": 901, "name": "Testrealm Normal", "slug": "testrealm-normal"},
        {"id": 902, "name": "Testrealm PvP", "slug": "testrealm-pvp"},
    ],
}
# Erfundener Charakter; Felder wie auf der Armory-Seite (name, surname, ruleset)
SLUG = "vorname-nachname"
FOREVER_PROFILE = {
    "_links": {},
    "id": 42,
    "name": "Vorname",
    "surname": "Nachname",
    "level": 10,
    "ruleset": {"name": "Normal", "slug": "normal"},
}


def _url(region: str, path: str) -> str:
    return f"{REGIONS[region]['api']}{path}"


def _ns(kind: str, suffix: str, region: str) -> dict:
    return {"namespace": f"{kind}{suffix}-{region}"}


def _fallback(aioclient_mock, paths: list[str]) -> None:
    """Alles nicht eigens Nachgestellte antwortet wie Blizzard mit 404."""
    for region in REGIONS:
        for path in paths:
            aioclient_mock.get(_url(region, path), status=404, text=NOT_FOUND)


async def _setup(hass: HomeAssistant, aioclient_mock):
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    return entry


async def _probe(hass: HomeAssistant, data: dict | None = None) -> dict:
    return await hass.services.async_call(
        DOMAIN, "probe_namespaces", data or {}, blocking=True, return_response=True
    )


def _paths(aioclient_mock) -> list[str]:
    """Abgefragte Adressen mit Namespace, ohne Token und Status."""
    return [
        f"{call[1].host} {call[1].path} {call[1].query.get('namespace')}"
        for call in aioclient_mock.mock_calls
        if call[0] == "GET" and call[1].path != "/oauth/token"
    ]


async def test_without_character(hass: HomeAssistant, aioclient_mock) -> None:
    """Ohne Angaben: static und dynamic je Region und Kandidat, 16 Abfragen."""
    await _setup(hass, aioclient_mock)
    aioclient_mock.get(
        _url("eu", STATIC), params=_ns("static", "-forever", "eu"), json=CLASSES
    )
    _fallback(aioclient_mock, [STATIC, DYNAMIC])
    states = {s.entity_id: s.state for s in hass.states.async_all()}

    response = await _probe(hass)

    assert probe.candidates() == ["-forever", "-camelot"]
    assert response["candidates"] == ["-forever", "-camelot"]
    assert response["requests"] == 16
    assert len(_paths(aioclient_mock)) == 16
    assert response["status_counts"] == {"200": 1, "404": 15}
    assert response["found"] == [f"static-forever-eu {STATIC}"]
    # Jede Region und jeder Namespace genau einmal je Endpunkt
    namespaces = {(r["namespace"], r["path"]) for r in response["results"]}
    assert len(namespaces) == 16
    assert ("profile-forever-eu", STATIC) not in namespaces
    for region in REGIONS:
        for suffix in ("-forever", "-camelot"):
            assert (f"static{suffix}-{region}", STATIC) in namespaces
            assert (f"dynamic{suffix}-{region}", DYNAMIC) in namespaces

    found = response["results"][0]
    assert found["status"] == 200
    assert found["keys"] == ["classes"]
    assert found["sample"] == {
        "classes": {
            "count": 4,
            "first": [
                {"id": 1, "name": "Krieger"},
                {"id": 2, "name": "Paladin"},
                {"id": 3, "name": "Jäger"},
            ],
        }
    }
    assert found["body"] is None
    missing = response["results"][1]
    assert missing["namespace"] == "dynamic-forever-eu"
    assert missing["status"] == 404
    assert missing["keys"] == [] and missing["sample"] == {}
    assert missing["body"] == NOT_FOUND
    # Liest nur: keine Entitaet aendert sich
    assert {s.entity_id: s.state for s in hass.states.async_all()} == states


async def test_with_character_and_ruleset(hass: HomeAssistant, aioclient_mock) -> None:
    """Mit Charakter: Regelsatz-Pfad, Pfad ohne Realm, Realms aus der Liste."""
    await _setup(hass, aioclient_mock)
    aioclient_mock.get(
        _url("eu", DYNAMIC), params=_ns("dynamic", "-camelot", "eu"), json=REALMS
    )
    aioclient_mock.get(
        _url("eu", f"/profile/wow/character/testrealm-pvp/{SLUG}"),
        params=_ns("profile", "-camelot", "eu"),
        json=FOREVER_PROFILE,
    )
    profile_paths = [
        f"/profile/wow/character/normal/{SLUG}",
        f"/profile/wow/character/{SLUG}",
        f"/profile/wow/character/testrealm-normal/{SLUG}",
        f"/profile/wow/character/testrealm-pvp/{SLUG}",
    ]
    _fallback(aioclient_mock, [STATIC, DYNAMIC, *profile_paths])

    response = await _probe(
        hass,
        {"regions": ["eu"], "character": " Vorname-Nachname ", "ruleset": "Normal"},
    )

    # -forever: static, dynamic, 2 Profilpfade; -camelot: dazu 2 Realms
    assert response["requests"] == 10
    assert [(r["namespace"], r["path"]) for r in response["results"]] == [
        ("static-forever-eu", STATIC),
        ("dynamic-forever-eu", DYNAMIC),
        ("profile-forever-eu", profile_paths[0]),
        ("profile-forever-eu", profile_paths[1]),
        ("static-camelot-eu", STATIC),
        ("dynamic-camelot-eu", DYNAMIC),
        ("profile-camelot-eu", profile_paths[0]),
        ("profile-camelot-eu", profile_paths[1]),
        ("profile-camelot-eu", profile_paths[2]),
        ("profile-camelot-eu", profile_paths[3]),
    ]
    assert response["found"] == [
        f"dynamic-camelot-eu {DYNAMIC}",
        f"profile-camelot-eu {profile_paths[3]}",
    ]
    hit = response["results"][-1]
    assert hit["keys"] == ["id", "level", "name", "ruleset", "surname"]
    assert hit["sample"]["surname"] == "Nachname"
    assert hit["sample"]["ruleset"] == {"name": "Normal", "slug": "normal"}
    realms = response["results"][5]["sample"]["realms"]
    assert realms["count"] == 2
    assert realms["first"][0] == {
        "id": 901,
        "name": "Testrealm Normal",
        "slug": "testrealm-normal",
    }
    # Andere Regionen bleiben unberuehrt
    assert all(p.startswith("eu.api.blizzard.com") for p in _paths(aioclient_mock))


async def test_realm_paths_limited(hass: HomeAssistant, aioclient_mock) -> None:
    """Hoechstens MAX_REALMS Realms aus einer Liste als Profilpfad."""
    await _setup(hass, aioclient_mock)
    many = {
        "realms": [
            {"id": i, "name": f"Realm {i}", "slug": f"realm-{i}"} for i in range(15)
        ]
    }
    aioclient_mock.get(
        _url("kr", DYNAMIC), params=_ns("dynamic", "-forever", "kr"), json=many
    )
    aioclient_mock.get(
        f"https://kr.api.blizzard.com/profile/wow/character/{SLUG}", status=404
    )
    for i in range(15):
        aioclient_mock.get(
            f"https://kr.api.blizzard.com/profile/wow/character/realm-{i}/{SLUG}",
            status=404,
        )
    _fallback(aioclient_mock, [STATIC, DYNAMIC])

    response = await _probe(hass, {"regions": ["kr"], "character": SLUG})

    realm_paths = [
        r["path"]
        for r in response["results"]
        if r["path"].startswith("/profile/wow/character/realm-")
    ]
    assert len(realm_paths) == probe.MAX_REALMS == 10
    assert realm_paths[-1] == f"/profile/wow/character/realm-9/{SLUG}"
    # Ohne Regelsatz kein Regelsatz-Pfad; je Kandidat der Pfad ohne Realm
    assert response["requests"] == 2 + 1 + 10 + 2 + 1


async def test_empty_and_duplicate_regions(hass: HomeAssistant, aioclient_mock) -> None:
    """Leere Liste heisst alle Regionen; doppelte Regionen nur einmal."""
    await _setup(hass, aioclient_mock)
    _fallback(aioclient_mock, [STATIC, DYNAMIC])
    assert (await _probe(hass, {"regions": []}))["requests"] == 16
    response = await _probe(hass, {"regions": ["tw", "tw", "us"]})
    assert response["requests"] == 8
    assert [r["region"] for r in response["results"]][::4] == ["tw", "us"]


async def test_token_retry_and_timeout(hass: HomeAssistant, aioclient_mock) -> None:
    """401: einmal neues Token; keine Antwort: Status null mit Fehlertext."""
    await _setup(hass, aioclient_mock)
    aioclient_mock.get(_url("eu", STATIC), status=401, text="")
    aioclient_mock.get(_url("eu", DYNAMIC), exc=TimeoutError())

    response = await _probe(hass, {"regions": ["eu"]})

    static, dynamic = response["results"][:2]
    assert static["status"] == 401
    assert static["body"] is None and static["error"] is None
    assert dynamic["status"] is None
    assert dynamic["error"].startswith("keine Antwort nach")
    assert response["status_counts"] == {"401": 2, "None": 2}
    # Je 401 ein neues Token, aber nur ein zweiter Versuch
    assert sum(1 for c in aioclient_mock.mock_calls if str(c[1]) == TOKEN_URL) == 2
    assert sum(1 for c in aioclient_mock.mock_calls if c[1].path == STATIC) == 4


@pytest.mark.parametrize(
    "data",
    [
        {"character": "realm/name"},
        {"character": SLUG, "ruleset": "a/b"},
        {"character": "  "},
        {"regions": ["cn"]},
    ],
)
async def test_invalid_input(hass: HomeAssistant, aioclient_mock, data) -> None:
    """Schraegstrich, leerer Name und unbekannte Region werden abgelehnt."""
    await _setup(hass, aioclient_mock)
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _probe(hass, data)
    assert _paths(aioclient_mock) == []


def test_sample_shortens() -> None:
    """Beispielwerte: ohne _links, Texte gekuerzt, verschachtelte Objekte kurz."""
    data = {
        "_links": {"self": {}},
        "text": "x" * 200,
        "nested": {"name": "N", "id": 7, "key": {"href": "h"}},
        "plain": {"a": 1, "b": 2},
        "flag": True,
        **{f"k{i}": i for i in range(20)},
    }
    result = probe.sample(data)
    assert "_links" not in result
    assert len(result) == probe.MAX_KEYS
    assert result["text"] == "x" * probe.MAX_TEXT
    assert result["nested"] == {"name": "N", "id": 7}
    assert result["plain"] == {"keys": ["a", "b"]}
    assert result["flag"] is True
    assert probe.sample("kein Objekt") == {}


def test_regions_selector_matches_schema() -> None:
    """Auswahl und Vorgabe in services.yaml = Regionen des Schemas."""
    path = Path(__file__).parents[1] / "custom_components/wow_character/services.yaml"
    regions = yaml.safe_load(path.read_text())["probe_namespaces"]["fields"]["regions"]
    assert regions["selector"]["select"]["options"] == list(REGIONS)
    assert regions["selector"]["select"]["multiple"] is True
    assert regions["default"] == list(REGIONS)
    assert services.PROBE_NAMESPACES_SCHEMA({})["regions"] == list(REGIONS)
