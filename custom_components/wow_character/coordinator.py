"""Coordinators: Profil je Charakter, Detail-Endpunkte je Charakter, Spielwelt je Region."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BattleNetAuthError, BattleNetClient, BattleNetError, BattleNetNotFound
from .const import (
    CONF_CHARACTER,
    CONF_GAME_VERSION,
    CONF_NAMESPACE_SUFFIX,
    CONF_REALM,
    CONF_REGION,
    DETAIL_ENDPOINTS,
    DETAIL_INTERVAL,
    DOMAIN,
    GAME_VERSIONS,
    UPDATE_INTERVAL,
    WORLD_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# Spielraum, damit ein Endpunkt mit 60-Minuten-Abstand nicht wegen weniger
# Sekunden Versatz eine ganze Runde ueberspringt.
_TOLERANCE = 5 * 60

# Welche Entitaet (Schluessel nach der unique_id des Charakters) welchen
# Detail-Endpunkt braucht. Berufe haben je Beruf eine eigene Entitaet.
DETAIL_KEYS: dict[str, str] = {
    "raid_lfr": "raids",
    "raid_normal": "raids",
    "raid_heroic": "raids",
    "raid_mythic": "raids",
    "boss_killed": "raids",
    "mythic_best_key": "mythic_season",
    "mythic_runs_timed": "mythic_season",
    "honor_level": "pvp",
    "honorable_kills": "pvp",
    "stat_health": "statistics",
    "stat_primary": "statistics",
    "stat_crit": "statistics",
    "stat_haste": "statistics",
    "stat_mastery": "statistics",
    "stat_versatility": "statistics",
    "new_achievement": "achievements",
    "mounts": "mounts",
    "pets": "pets",
    "toys": "toys",
    "avatar": "media",
    "full_body": "media",
}
PROFESSION_PREFIX = "profession-"


def endpoint_for_key(key: str) -> str | None:
    if key.startswith(PROFESSION_PREFIX):
        return "professions"
    return DETAIL_KEYS.get(key)


@dataclass
class WowRuntimeData:
    """Gemeinsamer API-Client und die Coordinators aller Charaktere und Regionen."""

    client: BattleNetClient
    coordinators: dict[str, WowCoordinator] = field(default_factory=dict)
    details: dict[str, WowDetailCoordinator] = field(default_factory=dict)
    # Schluessel: (Region, Namespace-Suffix), z. B. ("eu", "").
    worlds: dict[tuple[str, str], WowWorldCoordinator] = field(default_factory=dict)


type WowConfigEntry = ConfigEntry[WowRuntimeData]


class _CharacterMixin:
    """Gemeinsame Charakterdaten aus dem Untereintrag."""

    def _init_character(self, subentry: ConfigSubentry) -> None:
        self.subentry = subentry
        data = subentry.data
        self.region: str = data[CONF_REGION]
        self.realm: str = data[CONF_REALM]
        self.character: str = data[CONF_CHARACTER]
        self.suffix: str = data[CONF_NAMESPACE_SUFFIX]
        self.game_version: str = data[CONF_GAME_VERSION]

    @property
    def mythic_plus(self) -> bool:
        return GAME_VERSIONS[self.game_version]["mythic_plus"]

    @property
    def is_forever(self) -> bool:
        return self.game_version == "forever"


class WowCoordinator(_CharacterMixin, DataUpdateCoordinator[dict[str, Any]]):
    """Profil und Mythic+-Profil alle 15 Minuten: {"profile": {...}, "mythic": ...}."""

    config_entry: WowConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WowConfigEntry,
        client: BattleNetClient,
        subentry: ConfigSubentry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._init_character(subentry)

    async def _async_update_data(self) -> dict[str, Any]:
        args = (self.region, self.realm, self.character, self.suffix)
        try:
            profile = await self.client.get_profile(*args)
        except BattleNetAuthError as err:
            # Startet den Dialog zum erneuten Anmelden am Haupteintrag.
            raise ConfigEntryAuthFailed(str(err)) from err
        except BattleNetError as err:
            raise UpdateFailed(str(err)) from err

        mythic = None
        if self.mythic_plus:
            try:
                mythic = await self.client.get_mythic_profile(*args)
            except BattleNetNotFound:
                # Charakter ohne Mythic+-Lauf in dieser Season.
                mythic = {}
            except BattleNetAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except BattleNetError as err:
                raise UpdateFailed(str(err)) from err

        return {"profile": profile, "mythic": mythic}


class WowDetailCoordinator(_CharacterMixin, DataUpdateCoordinator[dict[str, Any]]):
    """Detail-Endpunkte eines Charakters, stuendlich bzw. alle 6 Stunden.

    data: Endpunkt -> Antwort, None wenn die API ihn fuer den Charakter nicht
    kennt (HTTP 404). Fehlt ein Schluessel, wurde der Endpunkt nicht abgefragt.
    """

    config_entry: WowConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WowConfigEntry,
        client: BattleNetClient,
        subentry: ConfigSubentry,
        profile: WowCoordinator,
        world: WowWorldCoordinator | None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title} Details",
            update_interval=DETAIL_INTERVAL,
        )
        self.client = client
        self._init_character(subentry)
        self._profile = profile
        self._world = world
        self._fetched: dict[str, float] = {}

    def needed_endpoints(self) -> set[str]:
        """Endpunkte mit mindestens einer aktiven oder noch nicht angelegten Entitaet."""
        ent_reg = er.async_get(self.hass)
        prefix = f"{self.subentry.unique_id}-"
        registered: set[str] = set()
        enabled: set[str] = set()
        for entry in er.async_entries_for_config_entry(
            ent_reg, self.config_entry.entry_id
        ):
            if not entry.unique_id.startswith(prefix):
                continue
            endpoint = endpoint_for_key(entry.unique_id[len(prefix) :])
            if endpoint is None:
                continue
            registered.add(endpoint)
            if entry.disabled_by is None:
                enabled.add(endpoint)
        needed = enabled | (set(DETAIL_ENDPOINTS) - registered)
        if not self.mythic_plus:
            needed.discard("mythic_season")
        return needed

    def _season_id(self) -> int | None:
        """Aktuelle M+-Season aus der Spielwelt, sonst die hoechste des Charakters."""
        world = (self._world.data if self._world else None) or {}
        if (season := world.get("season_id")) is not None:
            return season
        mythic = (self._profile.data or {}).get("mythic") or {}
        ids = [s.get("id") for s in mythic.get("seasons") or [] if isinstance(s, dict)]
        ids = [i for i in ids if isinstance(i, int)]
        return max(ids) if ids else None

    async def _async_update_data(self) -> dict[str, Any]:
        now = time.monotonic()
        data = dict(self.data or {})
        attempted = failed = 0
        for endpoint in sorted(self.needed_endpoints()):
            resource, every = DETAIL_ENDPOINTS[endpoint]
            last = self._fetched.get(endpoint)
            if last is not None and now - last < every * 60 - _TOLERANCE:
                continue
            if endpoint == "mythic_season":
                season = self._season_id()
                if season is None:
                    data[endpoint] = None
                    continue
                resource = resource.format(season=season)
            attempted += 1
            try:
                data[endpoint] = await self.client.get_character_resource(
                    self.region, self.realm, self.character, self.suffix, resource
                )
            except BattleNetNotFound:
                data[endpoint] = None
            except BattleNetAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except BattleNetError as err:
                # Alten Stand behalten, beim naechsten Takt erneut versuchen.
                failed += 1
                _LOGGER.debug("%s: %s fehlgeschlagen: %s", self.name, endpoint, err)
                continue
            self._fetched[endpoint] = now
        if attempted and failed == attempted:
            raise UpdateFailed("Alle Detail-Abfragen fehlgeschlagen")
        return data


class WowWorldCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Spielwelt einer Region: WoW-Marke, Reset, M+-Season und Serverstatus.

    data: {"token": Gold oder None, "reset": datetime oder None,
           "season_id": int oder None, "realms": {slug: {...}}}
    """

    config_entry: WowConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WowConfigEntry,
        client: BattleNetClient,
        region: str,
        suffix: str,
        realms: set[str],
        mythic_plus: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} Spielwelt {region}{suffix}",
            update_interval=WORLD_INTERVAL,
        )
        self.client = client
        self.region = region
        self.suffix = suffix
        self.realms = set(realms)
        self.mythic_plus = mythic_plus
        self._fetched: dict[str, float] = {}
        # Realm-Slug -> (Anzeigename, ID des verbundenen Realms)
        self._realm_info: dict[str, tuple[str, int]] = {}

    def _due(self, key: str, minutes: int, now: float) -> bool:
        last = self._fetched.get(key)
        return last is None or now - last >= minutes * 60 - _TOLERANCE

    async def _get(self, path: str) -> dict[str, Any] | None:
        try:
            return await self.client.get_game_data(self.region, self.suffix, path)
        except BattleNetNotFound:
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        now = time.monotonic()
        data: dict[str, Any] = dict(self.data or {"realms": {}})
        data["realms"] = dict(data.get("realms") or {})
        try:
            if self._due("token", 60, now):
                token = await self._get("token/index")
                price = (token or {}).get("price")
                # Preis in Kupfer: 1 Gold = 100 Silber = 10.000 Kupfer.
                data["token"] = price // 10000 if isinstance(price, int) else None
                self._fetched["token"] = now

            if self.mythic_plus and self._due("period", 60, now):
                data["reset"] = await self._weekly_reset()
                self._fetched["period"] = now

            if self.mythic_plus and self._due("season", 360, now):
                index = await self._get("mythic-keystone/season/index")
                data["season_id"] = ((index or {}).get("current_season") or {}).get(
                    "id"
                )
                self._fetched["season"] = now

            for slug in sorted(self.realms):
                data["realms"][slug] = await self._realm_status(slug)
        except BattleNetAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BattleNetError as err:
            raise UpdateFailed(str(err)) from err
        return data

    async def _weekly_reset(self) -> datetime | None:
        index = await self._get("mythic-keystone/period/index")
        period_id = ((index or {}).get("current_period") or {}).get("id")
        if period_id is None:
            return None
        period = await self._get(f"mythic-keystone/period/{period_id}")
        end = (period or {}).get("end_timestamp")
        if not isinstance(end, int):
            return None
        # Die Woche endet eine Sekunde vor dem Reset (wie homeassistant-wow-blizzard).
        return datetime.fromtimestamp((end + 1000) / 1000, tz=UTC)

    async def _realm_status(self, slug: str) -> dict[str, Any] | None:
        if slug not in self._realm_info:
            realm = await self._get(f"realm/{slug}")
            if realm is None:
                return None
            href = (realm.get("connected_realm") or {}).get("href", "")
            match = re.search(r"connected-realm/(\d+)", href)
            connected_id = int(match.group(1)) if match else realm.get("id")
            self._realm_info[slug] = (realm.get("name") or slug, connected_id)
        name, connected_id = self._realm_info[slug]
        connected = await self._get(f"connected-realm/{connected_id}")
        if connected is None:
            return None
        return {
            "name": name,
            "status": (connected.get("status") or {}).get("type"),
            "population": (connected.get("population") or {}).get("name"),
            "population_type": (connected.get("population") or {}).get("type"),
            "queue": bool(connected.get("has_queue", False)),
        }
