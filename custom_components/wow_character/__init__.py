"""WoW Charakter: Profildaten von Charakteren aus der Battle.net API.

Ein Haupteintrag haelt Client-ID und Secret, darunter haengt je Charakter ein
Untereintrag mit eigenem Geraet und eigenen Sensoren.
"""

from __future__ import annotations

import inspect
import logging
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import BattleNetClient
from .const import (
    CONF_CHARACTER,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_GAME_VERSION,
    CONF_NAMESPACE_SUFFIX,
    CONF_REALM,
    CONF_REGION,
    DOMAIN,
    MAIN_TITLE,
    SUBENTRY_CHARACTER,
)
from .coordinator import (
    WowConfigEntry,
    WowCoordinator,
    WowDetailCoordinator,
    WowRuntimeData,
    WowWorldCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.IMAGE, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await async_migrate_integration(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WowConfigEntry) -> bool:
    client = BattleNetClient(
        async_get_clientsession(hass),
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
    )
    runtime = WowRuntimeData(client=client)
    characters = {
        subentry_id: subentry
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_CHARACTER
    }

    # Spielwelt je Region und Spielversion, mit den Realms ihrer Charaktere.
    realms: dict[tuple[str, str], set[str]] = {}
    for subentry in characters.values():
        key = (subentry.data[CONF_REGION], subentry.data[CONF_NAMESPACE_SUFFIX])
        realms.setdefault(key, set()).add(subentry.data[CONF_REALM])
    for (region, suffix), slugs in realms.items():
        mythic_plus = suffix == ""
        world = WowWorldCoordinator(
            hass, entry, client, region, suffix, slugs, mythic_plus
        )
        await world.async_refresh()
        runtime.worlds[(region, suffix)] = world

    # Bewusst kein async_config_entry_first_refresh: Scheitert ein Charakter,
    # sind nur seine Sensoren nicht verfuegbar, die anderen laufen.
    for subentry_id, subentry in characters.items():
        world = runtime.worlds.get(
            (subentry.data[CONF_REGION], subentry.data[CONF_NAMESPACE_SUFFIX])
        )
        coordinator = WowCoordinator(hass, entry, client, subentry, world)
        await coordinator.async_refresh()
        runtime.coordinators[subentry_id] = coordinator
        detail = WowDetailCoordinator(hass, entry, client, subentry, coordinator, world)
        await detail.async_refresh()
        runtime.details[subentry_id] = detail
    entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Charakter hinzugefuegt oder entfernt, Zugangsdaten geaendert: neu laden.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: WowConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WowConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: WowConfigEntry) -> bool:
    # Version 1 baut async_migrate_integration um, bevor Eintraege starten.
    # Landet ein Eintrag trotzdem hier, ist er unbekannt (z. B. neuere Version).
    _LOGGER.error("Eintrag mit Version %s wird nicht unterstuetzt", entry.version)
    return False


# Neuere Home-Assistant-Versionen ordnen ein Geraet genau einem Eintrag und
# Untereintrag zu und verschieben es mit new_config_entry_id/new_config_subentry_id.
# add_/remove_config_entry_id gelten dort als veraltet (entfallen in 2027.8).
_DEVICE_MOVE_SUPPORTED = (
    "new_config_entry_id"
    in inspect.signature(dr.DeviceRegistry.async_update_device).parameters
)


def _move_device(
    dev_reg: dr.DeviceRegistry,
    device_id: str,
    entry: ConfigEntry,
    parent: ConfigEntry,
    subentry_id: str,
) -> None:
    """Geraet eines alten Eintrags an den Untereintrag des Haupteintrags haengen."""
    if _DEVICE_MOVE_SUPPORTED:
        dev_reg.async_update_device(
            device_id,
            new_config_entry_id=parent.entry_id,
            new_config_subentry_id=subentry_id,
        )
        return
    dev_reg.async_update_device(
        device_id,
        add_config_entry_id=parent.entry_id,
        add_config_subentry_id=subentry_id,
    )
    if parent is entry:
        dev_reg.async_update_device(
            device_id,
            remove_config_entry_id=entry.entry_id,
            remove_config_subentry_id=None,
        )
    else:
        dev_reg.async_update_device(device_id, remove_config_entry_id=entry.entry_id)


async def async_migrate_integration(hass: HomeAssistant) -> None:
    """Version 1 (ein Eintrag je Charakter) in Version 2 umbauen.

    Eintraege mit derselben Client-ID werden zu einem Haupteintrag zusammengefasst;
    jeder Charakter wird ein Untereintrag. Die unique_id des alten Eintrags wird
    zur unique_id des Untereintrags, daher bleiben Geraet, Entitaets-IDs und
    Verlauf erhalten.
    """
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.version == 1]
    if not entries:
        return

    # Aktive Eintraege zuerst, damit ein aktiver Eintrag Haupteintrag wird.
    entries.sort(key=lambda e: e.disabled_by is not None)
    parents = {
        e.data[CONF_CLIENT_ID]: e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.version == 2
    }
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    for entry in entries:
        client_id = entry.data[CONF_CLIENT_ID]
        parent = parents.setdefault(client_id, entry)

        subentry = ConfigSubentry(
            data=MappingProxyType(
                {
                    key: entry.data[key]
                    for key in (
                        CONF_REGION,
                        CONF_GAME_VERSION,
                        CONF_REALM,
                        CONF_CHARACTER,
                        CONF_NAMESPACE_SUFFIX,
                    )
                }
            ),
            subentry_type=SUBENTRY_CHARACTER,
            title=entry.title,
            unique_id=entry.unique_id,
        )
        hass.config_entries.async_add_subentry(parent, subentry)

        for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            ent_reg.async_update_entity(
                entity.entity_id,
                config_entry_id=parent.entry_id,
                config_subentry_id=subentry.subentry_id,
            )
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
            _move_device(dev_reg, device.id, entry, parent, subentry.subentry_id)

        if parent is entry:
            hass.config_entries.async_update_entry(
                entry,
                title=MAIN_TITLE,
                unique_id=client_id,
                data={
                    CONF_CLIENT_ID: client_id,
                    CONF_CLIENT_SECRET: entry.data[CONF_CLIENT_SECRET],
                },
                version=2,
            )
        else:
            await hass.config_entries.async_remove(entry.entry_id)
        _LOGGER.info("Charakter %s in Version 2 uebernommen", subentry.title)
