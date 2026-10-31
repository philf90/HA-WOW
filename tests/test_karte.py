"""Tests fuer die mitgelieferten Karten: Auslieferung und Laden im Frontend."""

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.wow_character import CARD_EDITOR, CARD_PATH, CARDS
from custom_components.wow_character.const import DOMAIN, GAME_VERSIONS

MANIFEST = Path(__file__).parents[1] / "custom_components" / DOMAIN / "manifest.json"
VERSION = json.loads(MANIFEST.read_text())["version"]
ARSENAL = (MANIFEST.parent / "frontend" / "wow-arsenal-card.js").read_text(
    encoding="utf-8"
)


@pytest.mark.parametrize(
    ("card", "element"),
    [
        ("wow-talent-tree-card.js", "wow-talent-tree-card"),
        ("wow-arsenal-card.js", "wow-arsenal-card"),
        ("wow-characters-card.js", "wow-characters-card"),
        ("wow-professions-card.js", "wow-professions-card"),
        ("wow-mythic-card.js", "wow-mythic-card"),
        ("wow-pvp-card.js", "wow-pvp-card"),
        ("wow-wardrobe-card.js", "wow-wardrobe-card"),
        ("wow-raid-card.js", "wow-raid-card"),
        ("wow-reputation-card.js", "wow-reputation-card"),
        ("wow-card-editor.js", "wow-character-editor"),
    ],
)
async def test_card_is_served(
    hass: HomeAssistant, hass_client, card: str, element: str
) -> None:
    assert await async_setup_component(hass, "http", {"http": {}})
    assert await async_setup_component(hass, DOMAIN, {})
    client = await hass_client()
    resp = await client.get(f"{CARD_PATH}/{card}")
    assert resp.status == 200
    assert f'customElements.define("{element}"' in await resp.text()


async def test_card_loaded_in_frontend(hass: HomeAssistant) -> None:
    """Mit Frontend: Modul mit Version im Pfad, damit Updates ankommen."""
    assert await async_setup_component(hass, "http", {"http": {}})
    hass.config.components.add("frontend")
    with patch("homeassistant.components.frontend.add_extra_js_url") as add:
        assert await async_setup_component(hass, DOMAIN, {})
    assert [c.args for c in add.call_args_list] == [
        (hass, f"{CARD_PATH}/{card}?v={VERSION}") for card in CARDS
    ]


async def test_card_without_frontend(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {"http": {}})
    with patch("homeassistant.components.frontend.add_extra_js_url") as add:
        assert await async_setup_component(hass, DOMAIN, {})
    add.assert_not_called()


@pytest.mark.parametrize("version", list(GAME_VERSIONS))
def test_arsenal_reads_game_version_from_model(version: str) -> None:
    """Kopfzeile: Spielversion aus dem Geraetemodell, neue und alte Form.

    Seit 0.22.0 heisst das Modell "World of Warcraft" bzw. "World of Warcraft
    Classic Era" (entity.py), bis 0.21.x "World of Warcraft (classic_era)".
    """
    pattern = r"function spielversion\(model\) \{\n  const m = /(.+)/\.exec"
    regex = re.compile(re.search(pattern, ARSENAL)[1])
    block = re.search(r"const VERSIONEN = \{\n(.*?)\n\};", ARSENAL, re.DOTALL)[1]
    names = dict(re.findall(r'^  (\w+): "([^"]+)",$', block, re.MULTILINE))
    assert set(names) == set(GAME_VERSIONS)
    # Wie entity.py; ohne Zusatz (Retail) zeigt die Karte VERSIONEN.retail
    new = regex.match(f"World of Warcraft{GAME_VERSIONS[version]['label']}")
    assert new, "Modell seit 0.22.0 nicht erkannt"
    assert (new[2] or names["retail"]) == names[version]
    old = regex.match(f"World of Warcraft ({version})")
    assert old, "Modell bis 0.21.x nicht erkannt"
    assert names[old[1]] == names[version]


@pytest.mark.parametrize("card", CARDS)
def test_card_uses_character_editor(card: str) -> None:
    """Im Editor nur den Charakter waehlen: gemeinsamer Editor, kein Formular
    mit allen Sensoren der Integration (seit 0.33.0)."""
    text = (MANIFEST.parent / "frontend" / card).read_text(encoding="utf-8")
    assert "static async getConfigElement()" in text
    assert f"`{CARD_EDITOR}${{new URL(import.meta.url).search}}`" in text
    assert "getConfigForm" not in text
