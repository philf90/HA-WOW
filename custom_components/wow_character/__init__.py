"""WoW Charakter: Profildaten von Charakteren aus der Battle.net API.

Ein Haupteintrag haelt Client-ID und Secret, darunter haengt je Charakter ein
Untereintrag mit eigenem Geraet und eigenen Sensoren.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    issue_registry as ir,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import BattleNetAuthError, BattleNetClient, BattleNetError, api_language
from .const import (
    CONF_CHARACTER,
    CONF_CHARACTER_ID,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_GAME_VERSION,
    CONF_LANGUAGE,
    CONF_NAMESPACE_SUFFIX,
    CONF_REALM,
    CONF_REGION,
    DOMAIN,
    GAME_VERSIONS,
    MAIN_TITLE,
    REGIONS,
    STARTUP_PARALLEL,
    SUBENTRY_CHARACTER,
)
from .coordinator import (
    WowConfigEntry,
    WowCoordinator,
    WowDetailCoordinator,
    WowRuntimeData,
    WowWorldCoordinator,
    config_snapshot,
    issue_id,
)
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.IMAGE, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
# Karten "WoW Talentbaum", "WoW Arsenal", "WoW Charaktere", "WoW Berufe" und
# "WoW Mythic+", von der Integration selbst ausgeliefert; alle Dateien unter
# frontend/ sind unter CARD_PATH erreichbar. Den Editor zur Charakterauswahl laden die Karten
# selbst nach (mit ihrer Version im Pfad), er ist deshalb kein eigenes Modul.
CARD_PATH = f"/{DOMAIN}"
CARD_DIR = Path(__file__).parent / "frontend"
CARDS = (
    "wow-talent-tree-card.js",
    "wow-arsenal-card.js",
    "wow-characters-card.js",
    "wow-professions-card.js",
    "wow-mythic-card.js",
)
CARD_EDITOR = "wow-card-editor.js"
# Eintrag -> Stand, fuer den gerade neu geladen wird (siehe _async_reload).
_RELOADING = f"{DOMAIN}_reloading"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await async_migrate_integration(hass)
    await _async_register_card(hass)
    async_setup_services(hass)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Karten ausliefern und im Frontend laden, ohne eigene Dashboard-Ressource.

    Die Version im Pfad sorgt dafuer, dass der Browser nach einem Update die
    neue Datei laedt.
    """
    if getattr(hass, "http", None) is None:
        return
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(f"{CARD_PATH}/{card}", str(CARD_DIR / card), True)
            for card in (*CARDS, CARD_EDITOR)
        ]
    )
    if "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url

    integration = await async_get_integration(hass, DOMAIN)
    for card in CARDS:
        add_extra_js_url(hass, f"{CARD_PATH}/{card}?v={integration.version}")


async def async_setup_entry(hass: HomeAssistant, entry: WowConfigEntry) -> bool:
    # Der Stand, mit dem dieser Start arbeitet. Erst am Ende genommen, enthielte
    # er auch Untereintraege, die waehrend des Starts dazukamen, ohne dass sie
    # eingerichtet sind (der Update-Listener fehlt waehrend des Neuladens).
    snapshot = config_snapshot(entry)
    client = BattleNetClient(
        async_get_clientsession(hass),
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        api_language(entry.options.get(CONF_LANGUAGE), hass.config.language),
    )
    # Ohne Token kommt keine Abfrage durch. Ein erfolgreicher Start ohne Daten
    # liesse Entitaeten weg, die nur aus der ersten Antwort entstehen (Berufe,
    # PvP-Brackets); Home Assistant wiederholt den Start stattdessen selbst.
    try:
        await client.validate()
    except BattleNetAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    except BattleNetError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="update_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    runtime = WowRuntimeData(client=client)
    characters = {
        subentry_id: subentry
        for subentry_id, subentry in entry.subentries.items()
        if subentry.subentry_type == SUBENTRY_CHARACTER
    }

    # Spielwelt je Region und Spielversion, mit den Realms ihrer Charaktere.
    realms: dict[tuple[str, str], set[str]] = {}
    # Jeder Suffix gehoert zu genau einer Spielversion.
    versions: dict[tuple[str, str], str] = {}
    for subentry in characters.values():
        key = (subentry.data[CONF_REGION], subentry.data[CONF_NAMESPACE_SUFFIX])
        realms.setdefault(key, set()).add(subentry.data[CONF_REALM])
        versions[key] = subentry.data[CONF_GAME_VERSION]
    # Zuerst die Spielwelten: Die Charaktere brauchen Season und Raid-Journal.
    runtime.worlds.update(
        {
            (region, suffix): WowWorldCoordinator(
                hass, entry, client, region, suffix, slugs, versions[(region, suffix)]
            )
            for (region, suffix), slugs in realms.items()
        }
    )
    await asyncio.gather(*(w.async_refresh() for w in runtime.worlds.values()))

    # Charaktere parallel, hoechstens STARTUP_PARALLEL zugleich (W4, seit
    # 0.26.0; vorher nacheinander). Je Charakter erst das Profil: Die Details
    # brauchen z. B. die Gilde daraus. Bewusst kein
    # async_config_entry_first_refresh: Scheitert ein Charakter, sind nur seine
    # Sensoren nicht verfuegbar, die anderen laufen.
    limit = asyncio.Semaphore(STARTUP_PARALLEL)

    async def start(
        subentry: ConfigSubentry,
    ) -> tuple[WowCoordinator, WowDetailCoordinator]:
        world = runtime.worlds.get(
            (subentry.data[CONF_REGION], subentry.data[CONF_NAMESPACE_SUFFIX])
        )
        coordinator = WowCoordinator(hass, entry, client, subentry, world)
        detail = WowDetailCoordinator(hass, entry, client, subentry, coordinator, world)
        async with limit:
            await coordinator.async_refresh()
            await detail.async_refresh()
        return coordinator, detail

    started = await asyncio.gather(*(start(s) for s in characters.values()))
    # In der Reihenfolge der Untereintraege, wie vorher
    for subentry_id, (coordinator, detail) in zip(characters, started, strict=True):
        runtime.coordinators[subentry_id] = coordinator
        runtime.details[subentry_id] = detail
    # Waehrend der Abfragen geloeschte Charaktere nicht mehr einrichten; Home
    # Assistant lehnt Entitaeten fuer unbekannte Untereintraege ab (Live-Test
    # 29.10.2026: "Can't add entities to unknown subentry").
    for subentry_id in runtime.coordinators.keys() - entry.subentries.keys():
        del runtime.coordinators[subentry_id]
        del runtime.details[subentry_id]
    # IDs, die _record_id beim Start nachgetragen hat, in den Stand uebernehmen;
    # sonst laedt der Vergleich am Ende ohne Grund neu. Jede andere Aenderung
    # waehrend des Starts laedt weiterhin neu.
    for subentry_id, (_title, data) in snapshot[1].items():
        subentry = entry.subentries.get(subentry_id)
        if (
            subentry is not None
            and CONF_CHARACTER_ID not in data
            and CONF_CHARACTER_ID in subentry.data
        ):
            data[CONF_CHARACTER_ID] = subentry.data[CONF_CHARACTER_ID]
    entry.runtime_data = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Die Entitaeten des Starts stehen: Endpunkte ohne Entitaet, z. B. Erfolge
    # in Classic Era, fragen die Detail-Coordinators nur noch selten ab.
    for detail in runtime.details.values():
        detail.entities_ready = True
        # Symbole des Talentbaums laedt erst dieser Lauf (siehe _talent_tree).
        if (detail.data or {}).get("talent_tree") is not None:
            entry.async_create_background_task(
                hass, detail.async_request_refresh(), f"{detail.name} Symbole"
            )
    _remove_stale(hass, entry)
    runtime.config_snapshot = snapshot
    # Charakter hinzugefuegt oder entfernt, Zugangsdaten geaendert: neu laden.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    if config_snapshot(entry) != snapshot:
        # Waehrend des Starts geaendert, z. B. weitere Charaktere vom Abgleich.
        hass.config_entries.async_schedule_reload(entry.entry_id)
    return True


async def _async_reload(hass: HomeAssistant, entry: WowConfigEntry) -> None:
    # Der Abgleich legt mehrere Untereintraege auf einmal an, jeder loest
    # diesen Listener sofort aus. Erst abgeben, damit alle angelegt sind, und
    # nur einmal je Stand neu laden. Den Stand, fuer den schon neu geladen
    # wird, merkt sich hass.data, weil runtime_data beim Entladen verschwindet.
    await asyncio.sleep(0)
    snapshot = config_snapshot(entry)
    runtime = getattr(entry, "runtime_data", None)
    reloading: dict[str, Any] = hass.data.setdefault(_RELOADING, {})
    if reloading.get(entry.entry_id) == snapshot or (
        runtime is not None and runtime.config_snapshot == snapshot
    ):
        return
    reloading[entry.entry_id] = snapshot
    try:
        await hass.config_entries.async_reload(entry.entry_id)
    finally:
        if reloading.get(entry.entry_id) == snapshot:
            del reloading[entry.entry_id]


# Spielwelt-Entitaeten: "<unique_id des Eintrags>-world-<region><suffix>-<key>",
# z. B. "...-world-eu-token" oder "...-world-eu-classic1x-realm-x-status".
_REALM_KEY = re.compile(r"realm-(.+)-(status|queue|population)")
_SUFFIXES = sorted(
    {s for version in GAME_VERSIONS.values() for s in version["namespaces"]},
    key=len,
    reverse=True,
)


def _parse_world_key(rest: str) -> tuple[tuple[str, str], str] | None:
    """ "eu-forever-token" -> (("eu", "-forever"), "token")."""
    for region in REGIONS:
        if not rest.startswith(f"{region}-"):
            continue
        tail = rest[len(region) :]
        for suffix in _SUFFIXES:
            if tail.startswith(f"{suffix}-"):
                return (region, suffix), tail[len(suffix) + 1 :]
    return None


def _world_scope(region: str, suffix: str) -> str:
    return f"world-{region}{suffix}"


def _world_key_in_use(world: WowWorldCoordinator, key: str) -> bool:
    """Verwaist sind nur Realm-Entitaeten von Realms ohne Charakter."""
    match = _REALM_KEY.fullmatch(key)
    return match is None or match.group(1) in world.realms


def _remove_stale(hass: HomeAssistant, entry: WowConfigEntry) -> None:
    """Spielwelt-Entitaeten und -Geraete ohne Charakter entfernen.

    Charakter-Geraete raeumt Home Assistant beim Entfernen des Untereintrags
    selbst auf. Realms und Regionen haengen dagegen nur indirekt an den
    Charakteren und blieben sonst als "nicht mehr bereitgestellt" stehen.
    Dazu Reparaturhinweise von Charakteren, die es nicht mehr gibt.
    """
    worlds = entry.runtime_data.worlds
    world_prefix = f"{entry.unique_id}-world-"
    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        uid = reg_entry.unique_id
        if not uid.startswith(world_prefix):
            continue
        parsed = _parse_world_key(uid[len(world_prefix) :])
        if parsed is None:
            continue
        scope, key = parsed
        world = worlds.get(scope)
        if world is None or not _world_key_in_use(world, key):
            _LOGGER.debug("Entferne verwaiste Entitaet %s", reg_entry.entity_id)
            ent_reg.async_remove(reg_entry.entity_id)

    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if not _device_in_use(entry, device):
            _LOGGER.debug("Entferne verwaistes Geraet %s", device.name)
            dev_reg.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )

    known = {
        issue_id(subentry_id)
        for other in hass.config_entries.async_entries(DOMAIN)
        for subentry_id in other.subentries
    }
    for domain, existing in list(ir.async_get(hass).issues):
        if (
            domain == DOMAIN
            and existing.startswith("character_")
            and existing not in known
        ):
            ir.async_delete_issue(hass, DOMAIN, existing)


def _device_in_use(entry: WowConfigEntry, device: dr.DeviceEntry) -> bool:
    """Charakter mit Untereintrag oder Spielwelt einer Region mit Charakteren."""
    in_use = {sub.unique_id for sub in entry.subentries.values()}
    runtime = getattr(entry, "runtime_data", None)
    for region, suffix in runtime.worlds if runtime else ():
        in_use.add(f"{entry.entry_id}-{_world_scope(region, suffix)}")
    return any(
        domain == DOMAIN and ident in in_use for domain, ident in device.identifiers
    )


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: WowConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Nur Geraete loeschen lassen, die nicht mehr gebraucht werden."""
    return not _device_in_use(entry, device)


async def async_remove_entry(hass: HomeAssistant, entry: WowConfigEntry) -> None:
    for subentry_id in entry.subentries:
        ir.async_delete_issue(hass, DOMAIN, issue_id(subentry_id))


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
