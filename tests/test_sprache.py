"""Tests fuer 0.19.0: Sprache der API-Texte als Option des Haupteintrags."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

import custom_components.wow_character as wow
from custom_components.wow_character.api import api_language, region_locale
from custom_components.wow_character.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    API,
    BASE_INPUT,
    PROFILE,
    REALMS,
    REALMS_URL,
    character_subentry,
    main_entry,
    mock_api,
    mock_token,
)


@pytest.mark.parametrize(
    ("region", "language", "locale"),
    [
        # Ohne Wahl: Sprache der Region wie bisher
        ("eu", None, "de_DE"),
        ("us", None, "en_US"),
        ("kr", None, "ko_KR"),
        ("tw", None, "zh_TW"),
        ("eu", "en", "en_GB"),
        ("us", "en", "en_US"),
        ("kr", "en", "en_US"),
        ("tw", "en", "en_US"),
        ("eu", "fr", "fr_FR"),
        ("us", "es", "es_MX"),
        ("eu", "es", "es_ES"),
        ("us", "pt", "pt_BR"),
        # Kennt die Region die Sprache nicht: Sprache der Region
        ("eu", "pt", "de_DE"),
        ("us", "de", "en_US"),
        ("eu", "ko", "de_DE"),
        ("eu", "xx", "de_DE"),
    ],
)
def test_region_locale(region: str, language: str | None, locale: str) -> None:
    assert region_locale(region, language) == locale


@pytest.mark.parametrize(
    ("choice", "ha_language", "language"),
    [
        (None, "en", None),
        ("region", "en", None),
        ("home_assistant", "en-GB", "en"),
        ("home_assistant", "zh-Hant", "zh"),
        ("home_assistant", "de", "de"),
        ("fr", "de", "fr"),
    ],
)
def test_api_language(choice, ha_language: str, language: str | None) -> None:
    assert api_language(choice, ha_language) == language


def _locales(aioclient_mock, part: str) -> set[str]:
    """Locale-Parameter aller Abfragen, deren Adresse part enthaelt."""
    return {
        call[1].query.get("locale")
        for call in aioclient_mock.mock_calls
        if part in str(call[1])
    }


async def _setup(hass: HomeAssistant, options: dict | None = None):
    entry = main_entry(character_subentry())
    entry.add_to_hass(hass)
    if options is not None:
        hass.config_entries.async_update_entry(entry, options=options)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_default_keeps_region_language(
    hass: HomeAssistant, aioclient_mock
) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass)
    assert _locales(aioclient_mock, "api.blizzard.com") == {"de_DE"}


async def test_chosen_language(hass: HomeAssistant, aioclient_mock) -> None:
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass, {"language": "en"})
    assert _locales(aioclient_mock, "api.blizzard.com") == {"en_GB"}
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["options"] == {"language": "en"}
    assert diagnostics["locales"] == {"eu": "en_GB"}


async def test_home_assistant_language(hass: HomeAssistant, aioclient_mock) -> None:
    await hass.config.async_update(language="fr")
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    await _setup(hass, {"language": "home_assistant"})
    assert _locales(aioclient_mock, "api.blizzard.com") == {"fr_FR"}


async def test_options_flow_reloads_with_new_language(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Speichern der Optionen laedt neu; danach fragt alles in der neuen Sprache."""
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    entry = await _setup(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    # Vorgabe: Sprache der Region
    (key,) = result["data_schema"].schema
    assert key.default() == "region"

    starts = []
    setup_entry = wow.async_setup_entry

    async def counting(hass: HomeAssistant, entry) -> bool:
        starts.append(entry.entry_id)
        return await setup_entry(hass, entry)

    aioclient_mock.clear_requests()
    mock_token(aioclient_mock)
    mock_api(aioclient_mock)
    with patch.object(wow, "async_setup_entry", counting):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"language": "it"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"language": "it"}
    assert len(starts) == 1
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert _locales(aioclient_mock, "api.blizzard.com") == {"it_IT"}


async def test_manual_character_uses_language(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """Realm-Liste und Profil beim Hinzufuegen von Hand in der gewaehlten Sprache."""
    mock_token(aioclient_mock)
    aioclient_mock.get(
        REALMS_URL,
        params={"namespace": "dynamic-eu", "locale": "en_GB"},
        json=REALMS,
    )
    aioclient_mock.get(
        API, params={"namespace": "profile-eu", "locale": "en_GB"}, json=PROFILE
    )
    entry = main_entry()
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={"language": "en"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "character"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], BASE_INPUT
    )
    assert result["step_id"] == "character"
    assert _locales(aioclient_mock, "/realm/index") == {"en_GB"}
