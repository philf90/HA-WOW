"""Tests fuer 0.24.0: Reparaturhinweise mit Dialog (E5)."""

import json
import re
from pathlib import Path

import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.wow_character.const import DOMAIN

from .conftest import (
    API,
    PROFILE,
    REALMS,
    REALMS_URL,
    UID1,
    UID2,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)

BASE = Path(__file__).parents[1] / "custom_components" / "wow_character"
NEW_API = "https://eu.api.blizzard.com/profile/wow/character/die-aldor/neuname"
LEVEL = "sensor.testchar_die_aldor_level"


def _changed_subentry():
    """Charakter mit gespeicherter ID 42; die API meldet 99 (anderer Charakter)."""
    sub = character_subentry()
    sub["data"] = {**sub["data"], "character_id": 42}
    return sub


async def _setup(
    hass: HomeAssistant, aioclient_mock, *subentries, answers: dict | None = None
):
    assert await async_setup_component(hass, "repairs", {})
    mock_token(aioclient_mock)
    mock_api(aioclient_mock, {API: {**PROFILE, "id": 99}, **(answers or {})})
    aioclient_mock.get(REALMS_URL, json=REALMS)
    entry = main_entry(*(subentries or (_changed_subentry(),)))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _subentry_id(entry, uid: str = UID1) -> str:
    return next(sid for sid, sub in entry.subentries.items() if sub.unique_id == uid)


def _issue(hass: HomeAssistant, entry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"character_{_subentry_id(entry)}"
    )


async def _start(hass: HomeAssistant, entry, step: str = "character"):
    manager = repairs_flow_manager(hass)
    result = await manager.async_init(
        DOMAIN, data={"issue_id": f"character_{_subentry_id(entry)}"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["character", "remove"]
    assert result["description_placeholders"] == {"character": "Testchar – Die Aldor"}
    return manager, await manager.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_issue_is_fixable(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    issue = _issue(hass, entry)
    assert issue.translation_key == "character_changed"
    assert issue.is_fixable
    assert issue.data == {
        "entry_id": entry.entry_id,
        "subentry_id": _subentry_id(entry),
    }


async def test_fix_with_new_name(hass: HomeAssistant, aioclient_mock) -> None:
    """Umbenannt: neuer Name, gleiche Entitaeten, Hinweis weg."""
    entry = await _setup(hass, aioclient_mock)
    entity = er.async_get(hass).async_get(LEVEL)
    manager, result = await _start(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "character"
    # Vorgaben: bisheriger Realm und Name
    defaults = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
    }
    assert defaults == {"realm": "die-aldor", "character": "Testchar"}

    mock_api(
        aioclient_mock, {NEW_API: {**PROFILE, "name": "Neuname", "id": 7}}, NEW_API
    )
    aioclient_mock.get(f"{NEW_API}/status", json={"id": 7, "is_valid": True})
    result = await manager.async_configure(
        result["flow_id"], {"realm": "die-aldor", "character": " Neuname "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    subentry = entry.subentries[_subentry_id(entry)]
    assert subentry.title == "Neuname – Die Aldor"
    assert subentry.data["character"] == "Neuname"
    assert subentry.data["character_id"] == 7
    assert _issue(hass, entry) is None
    # Gleiche Entitaet und gleiches Geraet, Werte unter dem neuen Namen
    after = er.async_get(hass).async_get(LEVEL)
    assert (after.unique_id, after.device_id) == (entity.unique_id, entity.device_id)
    assert hass.states.get(LEVEL).state == "90"


async def test_fix_same_name_accepts_character(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Gleicher Name: Der aktuelle Charakter wird uebernommen (neue ID)."""
    entry = await _setup(hass, aioclient_mock)
    assert hass.states.get(LEVEL).state == "unavailable"
    manager, result = await _start(hass, entry)
    result = await manager.async_configure(
        result["flow_id"], {"realm": "die-aldor", "character": "Testchar"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.subentries[_subentry_id(entry)].data["character_id"] == 99
    assert _issue(hass, entry) is None
    assert hass.states.get(LEVEL).state == "90"


@pytest.mark.parametrize(
    ("answer", "error"), [(404, "character_not_found"), (500, "cannot_connect")]
)
async def test_fix_errors(hass: HomeAssistant, aioclient_mock, answer, error) -> None:
    entry = await _setup(hass, aioclient_mock)
    aioclient_mock.get(NEW_API, status=answer)
    manager, result = await _start(hass, entry)
    result = await manager.async_configure(
        result["flow_id"], {"realm": "die-aldor", "character": "Neuname"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    # Eingabe bleibt stehen, Hinweis bleibt
    assert {
        str(k): k.description["suggested_value"] for k in result["data_schema"].schema
    }["character"] == "Neuname"
    assert _issue(hass, entry) is not None


async def test_fix_to_existing_character(hass: HomeAssistant, aioclient_mock) -> None:
    other = character_subentry(UID2, "Zweitchar – Aegwynn", "aegwynn", "Zweitchar")
    entry = await _setup(
        hass,
        aioclient_mock,
        _changed_subentry(),
        other,
        answers={
            "https://eu.api.blizzard.com/profile/wow/character/aegwynn/zweitchar": {
                **PROFILE,
                "name": "Zweitchar",
            }
        },
    )
    manager, result = await _start(hass, entry)
    result = await manager.async_configure(
        result["flow_id"], {"realm": "aegwynn", "character": "zweitchar"}
    )
    assert result["errors"] == {"base": "already_configured"}


async def test_fix_remove_character(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    subentry_id = _subentry_id(entry)
    manager, result = await _start(hass, entry, "remove")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "remove"
    result = await manager.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert subentry_id not in entry.subentries
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"character_{subentry_id}") is None
    )
    assert er.async_get(hass).async_get(LEVEL) is None


async def test_fix_entry_not_loaded(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    await hass.config_entries.async_unload(entry.entry_id)
    _manager, result = await _start(hass, entry)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"


async def test_fix_without_realm_list(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    aioclient_mock.get(REALMS_URL, status=500)
    _manager, result = await _start(hass, entry)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


@pytest.mark.parametrize("path", ["strings.json", "translations/de.json"])
def test_fix_flow_translated(path: str) -> None:
    """Jeder Hinweis hat den Dialog mit allen Schritten, Fehlern und Abbruechen."""
    source = (BASE / "repairs.py").read_text()
    errors = set(re.findall(r'errors\["base"\] = "(\w+)"', source))
    aborts = set(re.findall(r'async_abort\(reason="(\w+)"\)', source))
    steps = set(re.findall(r"async def async_step_(\w+)", source))
    issues = json.loads((BASE / path).read_text(encoding="utf-8"))["issues"]
    for key in ("character_not_found", "character_changed", "character_invalid"):
        fix = issues[key]["fix_flow"]
        assert set(fix["step"]) == steps, key
        assert errors <= set(fix["error"]), key
        assert aborts <= set(fix["abort"]), key
        assert set(fix["step"]["init"]["menu_options"]) == {"character", "remove"}
