"""Aktionen: Charaktere sofort abfragen, beliebige Charaktere nachschlagen.

refresh fragt Charaktere (und auf Wunsch Spielwelten) sofort ab, ohne die
Takte abzuwarten, z. B. per Automation nach dem Ausloggen. get_character
liefert das Profil eines beliebigen Charakters als Antwort, ohne ihn
einzurichten (Freunde, Gildenmitglieder).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from . import parsers as p
from .api import (
    BattleNetAuthError,
    BattleNetError,
    BattleNetForbidden,
    BattleNetNotFound,
)
from .const import (
    CONF_CHARACTER,
    CONF_GAME_VERSION,
    CONF_REALM,
    CONF_REGION,
    DOMAIN,
    GAME_VERSIONS,
    REGIONS,
)
from .coordinator import (
    WowConfigEntry,
    WowCoordinator,
    WowDetailCoordinator,
    WowWorldCoordinator,
)

SERVICE_REFRESH = "refresh"
SERVICE_GET_CHARACTER = "get_character"
ATTR_DEVICE_ID = "device_id"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

REFRESH_SCHEMA = vol.Schema(
    {vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string])}
)
GET_CHARACTER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(CONF_REGION): vol.In(list(REGIONS)),
        vol.Optional(CONF_GAME_VERSION, default="retail"): vol.In(list(GAME_VERSIONS)),
        vol.Required(CONF_REALM): vol.All(cv.string, vol.Strip, vol.Length(min=1)),
        vol.Required(CONF_CHARACTER): vol.All(cv.string, vol.Strip, vol.Length(min=1)),
    }
)


def async_setup_services(hass: HomeAssistant) -> None:
    """Aktionen einmal je Home Assistant anmelden (aus async_setup)."""

    async def refresh(call: ServiceCall) -> None:
        await _async_refresh(hass, call)

    async def get_character(call: ServiceCall) -> ServiceResponse:
        return await _async_get_character(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, refresh, REFRESH_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_CHARACTER,
        get_character,
        GET_CHARACTER_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def _loaded_entries(hass: HomeAssistant) -> list[WowConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


def _not_loaded() -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN, translation_key="not_loaded"
    )


# refresh


# Name, Detail- oder Spielwelt-Coordinator, Profil-Coordinator oder None
type _Target = tuple[
    str, WowDetailCoordinator | WowWorldCoordinator, WowCoordinator | None
]


def _device_targets(hass: HomeAssistant, device_ids: list[str]) -> list[_Target]:
    dev_reg = dr.async_get(hass)
    targets: list[_Target] = []
    for device_id in device_ids:
        device = dev_reg.async_get(device_id)
        target = _device_target(hass, device) if device else None
        if target is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device": device_id},
            )
        targets.append(target)
    return targets


def _device_entry_ids(device: dr.DeviceEntry) -> set[str]:
    """Eintraege, zu denen das Geraet gehoert.

    Neuere Home-Assistant-Versionen ordnen ein Geraet genau einem Eintrag zu
    (config_entry_id); config_entries gilt dort als veraltet und entfaellt in
    2027.10 (Live-Test 30.10.2026 mit 2026.10.4). Aeltere kennen nur
    config_entries.
    """
    if hasattr(device, "config_entry_id"):
        entry_id = device.config_entry_id
        return {entry_id} if entry_id else set()
    return set(device.config_entries)


def _device_target(hass: HomeAssistant, device: dr.DeviceEntry) -> _Target | None:
    idents = {ident for domain, ident in device.identifiers if domain == DOMAIN}
    if not idents:
        return None
    for entry_id in _device_entry_ids(device):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue
        if entry.state is not ConfigEntryState.LOADED:
            raise _not_loaded()
        runtime = entry.runtime_data
        for subentry_id, detail in runtime.details.items():
            if detail.subentry.unique_id in idents:
                profile = runtime.coordinators[subentry_id]
                return detail.subentry.title, detail, profile
        for (region, suffix), world in runtime.worlds.items():
            if f"{entry.entry_id}-world-{region}{suffix}" in idents:
                return device.name_by_user or device.name or "", world, None
    return None


async def _async_refresh(hass: HomeAssistant, call: ServiceCall) -> None:
    targets: list[_Target]
    if call.data.get(ATTR_DEVICE_ID):
        targets = _device_targets(hass, call.data[ATTR_DEVICE_ID])
    else:
        entries = _loaded_entries(hass)
        if not entries:
            raise _not_loaded()
        # Ohne Geraet alle Charaktere; die Spielwelt hat ihren eigenen Takt.
        targets = [
            (detail.subentry.title, detail, entry.runtime_data.coordinators[sid])
            for entry in entries
            for sid, detail in entry.runtime_data.details.items()
        ]
    failed: list[str] = []
    for name, coordinator, profile in targets:
        ok = True
        if profile is not None:
            # Zuerst das Profil: Die Details brauchen z. B. die Gilde daraus.
            await profile.async_refresh()
            ok = profile.last_update_success
        await coordinator.async_refresh_now()
        if not (ok and coordinator.last_update_success):
            failed.append(name)
    if failed:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="refresh_failed",
            translation_placeholders={"names": ", ".join(failed)},
        )


# get_character


def _entry(hass: HomeAssistant, entry_id: str | None) -> WowConfigEntry:
    if entry_id is None:
        entries = _loaded_entries(hass)
        if len(entries) == 1:
            return entries[0]
        if not entries:
            raise _not_loaded()
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_required"
        )
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise _not_loaded()
    return entry


def _api_error(err: BattleNetError) -> HomeAssistantError:
    key = "auth_failed" if isinstance(err, BattleNetAuthError) else "update_failed"
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={"error": str(err)},
    )


async def _realm_list(
    entry: WowConfigEntry, region: str, suffix: str
) -> list[dict[str, Any]]:
    """Realm-Liste der Region; bis zum Neuladen zwischengespeichert."""
    cache = entry.runtime_data.realm_lists
    if (region, suffix) not in cache:
        cache[(region, suffix)] = await entry.runtime_data.client.get_realms(
            region, suffix
        )
    return cache[(region, suffix)]


def _realm_slug(realms: list[dict[str, Any]], wanted: str) -> str | None:
    """Slug zu Name oder Slug, ohne Gross- und Kleinschreibung."""
    wanted = wanted.casefold()
    for realm in realms:
        if wanted in (realm["slug"].casefold(), str(realm["name"]).casefold()):
            return realm["slug"]
    return None


async def _async_get_character(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    entry = _entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    client = entry.runtime_data.client
    region: str = call.data[CONF_REGION]
    version: str = call.data[CONF_GAME_VERSION]
    realm: str = call.data[CONF_REALM]
    name: str = call.data[CONF_CHARACTER]

    # Namespace-Kandidaten der Reihe nach, wie beim Einrichten.
    for suffix in GAME_VERSIONS[version]["namespaces"]:
        try:
            realms = await _realm_list(entry, region, suffix)
        except (BattleNetNotFound, BattleNetForbidden):
            continue
        except BattleNetError as err:
            raise _api_error(err) from err
        break
    else:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="realms_not_found"
        )
    slug = _realm_slug(realms, realm)
    if slug is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="realm_not_found",
            translation_placeholders={"realm": realm},
        )
    try:
        profile = await client.get_profile(region, slug, name, suffix)
    except BattleNetNotFound as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="lookup_not_found",
            translation_placeholders={"character": f"{name} – {realm}"},
        ) from err
    except BattleNetError as err:
        raise _api_error(err) from err

    rating = None
    if GAME_VERSIONS[version]["mythic_plus"]:
        try:
            mythic = await client.get_mythic_profile(region, slug, name, suffix)
        except BattleNetError:
            # Ohne Mythic+-Lauf meldet die API 404; das Profil reicht trotzdem.
            mythic = {}
        rating = (mythic.get("current_mythic_rating") or {}).get("rating")
    try:
        media = await client.get_character_resource(
            region, slug, name, suffix, "character-media"
        )
    except BattleNetError:
        media = None

    last_login = p.timestamp(profile.get("last_login_timestamp"))
    return {
        "name": profile.get("name"),
        "id": profile.get("id"),
        "realm": p.name_of(profile.get("realm")),
        "realm_slug": slug,
        "region": region,
        "game_version": version,
        "level": profile.get("level"),
        "class": p.name_of(profile.get("character_class")),
        "spec": p.name_of(profile.get("active_spec")),
        "race": p.name_of(profile.get("race")),
        "faction": p.name_of(profile.get("faction")),
        "guild": p.name_of(profile.get("guild")),
        "title": p.active_title(profile),
        "achievement_points": profile.get("achievement_points"),
        "equipped_item_level": profile.get("equipped_item_level"),
        "average_item_level": profile.get("average_item_level"),
        "last_login": last_login.isoformat() if last_login else None,
        # Wert der API ohne Season-Pruefung, wie im Arsenal.
        "mythic_rating": round(rating, 1) if isinstance(rating, int | float) else None,
        "avatar": p.media_url(media, "avatar"),
    }
