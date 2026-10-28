"""Tests fuer die Karte "WoW Talentbaum": Auslieferung und Laden im Frontend."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.wow_character import CARD_PATH, CARDS
from custom_components.wow_character.const import DOMAIN

MANIFEST = Path(__file__).parents[1] / "custom_components" / DOMAIN / "manifest.json"
VERSION = json.loads(MANIFEST.read_text())["version"]


@pytest.mark.parametrize(
    ("card", "element"),
    [
        ("wow-talent-tree-card.js", "wow-talent-tree-card"),
        ("wow-arsenal-card.js", "wow-arsenal-card"),
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
