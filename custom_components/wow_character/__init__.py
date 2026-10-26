"""WoW Charakter: Profildaten eines Charakters aus der Battle.net API."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BattleNetClient
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_REGION
from .coordinator import WowConfigEntry, WowCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: WowConfigEntry) -> bool:
    client = BattleNetClient(
        async_get_clientsession(hass),
        entry.data[CONF_REGION],
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
    )
    coordinator = WowCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WowConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
