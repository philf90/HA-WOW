"""Tests fuer 0.31.0: Sensoren "Erbstuecke" und "Transmog-Vorlagen" (E9)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.wow_character import parsers as p
from custom_components.wow_character.const import DOMAIN
from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    API,
    UID1,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

HEIRLOOMS_URL = f"{API}/collections/heirlooms"
TRANSMOGS_URL = f"{API}/collections/transmogs"


async def _setup(
    hass: HomeAssistant,
    aioclient_mock,
    override: dict | None = None,
    options: dict | None = None,
):
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, override)
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    if options is not None:
        hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, key: str):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{UID1}-{key}"
    )
    return hass.states.get(entity_id) if entity_id else None


def _calls(aioclient_mock, url: str) -> int:
    return sum(1 for c in aioclient_mock.mock_calls if str(c[1]).startswith(url))


async def test_heirlooms_sensor(hass: HomeAssistant, aioclient_mock) -> None:
    """Anzahl; aufgewertete und Verteilung der Stufen als Attribute."""
    await _setup(hass, aioclient_mock)
    state = _state(hass, "heirlooms")
    assert state.state == "4"
    assert state.attributes["upgraded"] == 3
    assert state.attributes["upgrade_levels"] == {"0": 1, "2": 1, "6": 2}


async def test_transmogs_sensor(hass: HomeAssistant, aioclient_mock) -> None:
    """Verschiedene Vorlagen; Sets und Vorlagen je Platz als Attribute."""
    entry = await _setup(hass, aioclient_mock)
    state = _state(hass, "transmogs")
    assert state.state == "8"
    assert state.attributes["sets"] == 5
    assert state.attributes["slots"] == {"Kopf": 7, "Ruecken": 1}
    # Gespeichert nur IDs, keine Links
    (detail,) = entry.runtime_data.details.values()
    stored = detail.data["transmogs"]
    assert stored["slots"][1] == {
        "slot": {"type": "BACK", "name": "Ruecken"},
        "appearances": [50],
    }
    assert "_links" not in stored


async def test_rare_interval_and_diagnostics(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Mit Sensor im seltenen Takt (6 h); gekuerzt in der Diagnose."""
    entry = await _setup(hass, aioclient_mock)
    (detail,) = entry.runtime_data.details.values()
    intervals = detail.endpoint_intervals()
    assert intervals["heirlooms"] == intervals["transmogs"] == 360
    diag = await async_get_config_entry_diagnostics(hass, entry)
    details = diag["characters"]["Testchar – Die Aldor"]["details"]
    assert details["heirlooms"]["count"] == 4
    assert details["transmogs"]["appearance_sets"] == 5
    assert details["transmogs"]["first_appearances"] == [1, 2]


async def test_group_collections_off(hass: HomeAssistant, aioclient_mock) -> None:
    """Gruppe "Sammlungen" ausgeschaltet: keine Abfrage, keine Sensoren."""
    await _setup(hass, aioclient_mock, options={"disabled_groups": ["collections"]})
    assert _calls(aioclient_mock, HEIRLOOMS_URL) == 0
    assert _calls(aioclient_mock, TRANSMOGS_URL) == 0
    assert _state(hass, "heirlooms") is None
    assert _state(hass, "transmogs") is None


async def test_empty_answer_zero(hass: HomeAssistant, aioclient_mock) -> None:
    """Antwort ohne Listen (Typen: appearance_sets und slots optional): 0."""
    await _setup(
        hass,
        aioclient_mock,
        {HEIRLOOMS_URL: {"_links": {}}, TRANSMOGS_URL: {"_links": {}}},
    )
    assert _state(hass, "heirlooms").state == "0"
    transmogs = _state(hass, "transmogs")
    assert transmogs.state == "0"
    assert transmogs.attributes["sets"] == 0


async def test_not_found_unknown(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass, aioclient_mock, {HEIRLOOMS_URL: 404, TRANSMOGS_URL: 404})
    assert _state(hass, "heirlooms").state == "unknown"
    assert _state(hass, "transmogs").state == "unknown"


def test_transmogs_unique_and_merged_slots() -> None:
    """Jede ID einmal; Plaetze gleichen Namens zusammen (live CHEST und ROBE)."""
    data = p.compact_transmogs(
        {
            "_links": {"self": {"href": "x"}},
            "appearance_sets": [{"key": {"href": "x"}, "name": "Set", "id": 1}],
            "slots": [
                {
                    "slot": {"type": "CHEST", "name": "Brust"},
                    "appearances": [{"key": {"href": "x"}, "id": 1}, {"id": 2}],
                },
                {
                    "slot": {"type": "ROBE", "name": "Brust"},
                    "appearances": [{"id": 2}, {"id": 3}],
                },
                {"slot": {"type": "HEAD"}, "appearances": [{"id": 3}, "kaputt"]},
                None,
            ],
        }
    )
    assert data["appearance_sets"] == [{"id": 1, "name": "Set"}]
    state, attrs = p.transmogs(data)
    assert state == 3
    assert attrs == {"sets": 1, "slots": {"Brust": 3, "HEAD": 1}}


def test_heirlooms_unexpected_entries() -> None:
    """Fremde Eintraege zaehlen nicht, Stufe fehlt: nicht in der Verteilung."""
    state, attrs = p.heirlooms(
        {"heirlooms": [{"heirloom": {"id": 1}}, "kaputt", {"upgrade": {"level": 0}}]}
    )
    assert state == 2
    assert attrs == {"upgraded": 0, "upgrade_levels": {"0": 1}}
    assert p.heirlooms(None) == (None, {})
