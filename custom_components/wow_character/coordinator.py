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
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import parsers as p
from .api import BattleNetAuthError, BattleNetClient, BattleNetError, BattleNetNotFound
from .const import (
    CONF_CHARACTER,
    CONF_CHARACTER_ID,
    CONF_GAME_VERSION,
    CONF_NAMESPACE_SUFFIX,
    CONF_REALM,
    CONF_REGION,
    DETAIL_ENDPOINTS,
    DETAIL_INTERVAL,
    DOMAIN,
    GAME_VERSIONS,
    NOT_FOUND_IS_FINAL,
    NOT_FOUND_LIMIT,
    PVP_BRACKETS,
    STATUS_INTERVAL,
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
    "reputation": "reputations",
    "empty_sockets": "equipment",
    "enchantments": "equipment",
    "item_set": "equipment",
    "achievements": "achievements",
    "specialization": "specializations",
    "talent_tree": "specializations",
    "talents": "specializations",
    "titles": "titles",
    "game_statistics": "game_statistics",
    "quests_completed": "quests",
    "guild": "guild",
    "new_collectible": "mounts",
    "hunter_pets": "hunter_pets",
}
# Entitaeten, die ausser ihrem Endpunkt aus DETAIL_KEYS weitere brauchen.
# Der Level-Sensor (Profil) zeigt zusaetzlich Attribute aus dem Aussehen.
EXTRA_ENDPOINTS: dict[str, tuple[str, ...]] = {
    "guild": ("guild_activity", "guild_roster"),
    "new_collectible": ("pets", "toys", "titles"),
    "level": ("appearance",),
}
PROFESSION_PREFIX = "profession-"
# Ein Sensor je Ausruestungsplatz, z. B. "equipment_head".
EQUIPMENT_PREFIX = "equipment_"
# Ein Sensor je PvP-Bracket, z. B. "pvp_bracket_3v3".
PVP_BRACKET_PREFIX = "pvp_bracket_"


def config_snapshot(entry: ConfigEntry) -> Any:
    """Stand von Eintrag und Untereintraegen, mit dem der Eintrag laeuft."""
    return (
        dict(entry.data),
        {
            subentry_id: (subentry.title, dict(subentry.data))
            for subentry_id, subentry in entry.subentries.items()
        },
    )


def issue_id(subentry_id: str) -> str:
    """Ein Reparaturhinweis je Charakter; der Grund steht im translation_key."""
    return f"character_{subentry_id}"


def _update_failed(err: Exception) -> UpdateFailed:
    return UpdateFailed(
        translation_domain=DOMAIN,
        translation_key="update_failed",
        translation_placeholders={"error": str(err)},
    )


def _auth_failed(err: Exception) -> ConfigEntryAuthFailed:
    # Startet den Dialog zum erneuten Anmelden am Haupteintrag.
    return ConfigEntryAuthFailed(
        translation_domain=DOMAIN,
        translation_key="auth_failed",
        translation_placeholders={"error": str(err)},
    )


def endpoint_for_key(key: str) -> str | None:
    if key.startswith(PROFESSION_PREFIX):
        return "professions"
    if key.startswith(EQUIPMENT_PREFIX):
        return "equipment"
    if key.startswith(PVP_BRACKET_PREFIX):
        return "pvp_brackets"
    return DETAIL_KEYS.get(key)


@dataclass
class WowRuntimeData:
    """Gemeinsamer API-Client und die Coordinators aller Charaktere und Regionen."""

    client: BattleNetClient
    coordinators: dict[str, WowCoordinator] = field(default_factory=dict)
    details: dict[str, WowDetailCoordinator] = field(default_factory=dict)
    # Schluessel: (Region, Namespace-Suffix), z. B. ("eu", "").
    worlds: dict[tuple[str, str], WowWorldCoordinator] = field(default_factory=dict)
    # Stand von Eintrag und Untereintraegen beim Start; der Update-Listener
    # laedt nur neu, wenn er sich davon unterscheidet.
    config_snapshot: Any = None


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
    def is_retail(self) -> bool:
        return self.game_version == "retail"

    def supports_endpoint(self, endpoint: str) -> bool:
        """Kennt die Spielversion diesen Detail-Endpunkt (laut Blizzard-Doku)?"""
        known = GAME_VERSIONS[self.game_version]["endpoints"]
        return known is None or endpoint in known

    def supports_static(self, path: str) -> bool:
        """Kennt die Spielversion diese statischen Spieldaten, z. B. "media/item/1"?"""
        known = GAME_VERSIONS[self.game_version]["static"]
        return known is None or any(
            path == kind or path.startswith(f"{kind}/") for kind in known
        )


class WowCoordinator(_CharacterMixin, DataUpdateCoordinator[dict[str, Any]]):
    """Profil und Mythic+-Profil alle 15 Minuten.

    data: {"profile": {...}, "mythic": {...} oder None, "season_id": int oder None}
    """

    config_entry: WowConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: WowConfigEntry,
        client: BattleNetClient,
        subentry: ConfigSubentry,
        world: WowWorldCoordinator | None = None,
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
        self._world = world
        # 404 in Folge; ab NOT_FOUND_LIMIT gibt es einen Reparaturhinweis.
        self._not_found = 0
        # Letzte erfolgreiche Pruefung ueber den Status-Endpunkt.
        self._status_checked: float | None = None
        # "character_changed" oder "character_invalid", solange Blizzard die
        # Daten nicht mehr diesem Charakter zuordnet; die Details warten dann.
        self.identity_problem: str | None = None
        # Symbole von Klasse und Spezialisierung
        self._media = MediaCache(self)

    async def _async_update_data(self) -> dict[str, Any]:
        args = (self.region, self.realm, self.character, self.suffix)
        try:
            profile = await self.client.get_profile(*args)
        except BattleNetNotFound as err:
            self._not_found += 1
            if self._not_found >= NOT_FOUND_LIMIT:
                self._create_issue("character_not_found")
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="character_not_found",
                translation_placeholders={"character": self.subentry.title},
            ) from err
        except BattleNetAuthError as err:
            raise _auth_failed(err) from err
        except BattleNetError as err:
            raise _update_failed(err) from err
        self._not_found = 0
        await self._check_identity(profile)
        self.identity_problem = None
        ir.async_delete_issue(self.hass, DOMAIN, issue_id(self.subentry.subentry_id))

        mythic = None
        if self.mythic_plus:
            try:
                mythic = await self.client.get_mythic_profile(*args)
            except BattleNetNotFound:
                # Charakter ohne Mythic+-Lauf in dieser Season.
                mythic = {}
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                raise _update_failed(err) from err

        # Aktuelle M+-Season der Region, damit die Wertung nur fuer sie gilt.
        season_id = ((self._world.data if self._world else None) or {}).get("season_id")
        await self._media.lookup(
            [
                ("playable-class", (profile.get("character_class") or {}).get("id")),
                (
                    "playable-specialization",
                    (profile.get("active_spec") or {}).get("id"),
                ),
            ]
        )
        return {
            "profile": profile,
            "mythic": mythic,
            "season_id": season_id,
            "media_urls": self._media.urls(),
        }

    async def _check_identity(self, profile: dict[str, Any]) -> None:
        """Gleicher Charakter wie beim Einrichten und laut Blizzard noch gueltig?

        Blizzard empfiehlt, die Daten eines Charakters zu verwerfen, wenn der
        Status-Endpunkt 404 oder is_valid false meldet oder die ID nicht mehr
        zur gespeicherten passt. Die Integration zeigt dann nichts an und legt
        einen Reparaturhinweis an.
        """
        char_id = profile.get("id")
        if isinstance(char_id, int):
            recorded = self.subentry.data.get(CONF_CHARACTER_ID)
            if recorded is None:
                self._record_id(char_id)
            elif recorded != char_id:
                raise self._identity_failed("character_changed")

        now = time.monotonic()
        if (
            self._status_checked is not None
            and now - self._status_checked < STATUS_INTERVAL.total_seconds()
        ):
            return
        try:
            status = await self.client.get_character_resource(
                self.region, self.realm, self.character, self.suffix, "status"
            )
        except BattleNetAuthError as err:
            raise _auth_failed(err) from err
        except BattleNetError as err:
            # Das Profil kam an; die Pruefung holt der naechste Takt nach.
            # Ein bekannter ungueltiger Stand bleibt bis dahin bestehen.
            _LOGGER.debug("%s: Status nicht abgefragt: %s", self.name, err)
            if self.identity_problem == "character_invalid":
                raise self._identity_failed("character_invalid") from err
            return
        if status.get("is_valid") is False:
            raise self._identity_failed("character_invalid")
        self._status_checked = now

    def _identity_failed(self, reason: str) -> UpdateFailed:
        self.identity_problem = reason
        self._create_issue(reason)
        return UpdateFailed(
            translation_domain=DOMAIN,
            translation_key=reason,
            translation_placeholders={"character": self.subentry.title},
        )

    def _record_id(self, char_id: int) -> None:
        """ID nachtragen (Charaktere aus Versionen vor 0.7.0).

        Loest kein Neuladen aus: Der neue Stand wird gleich als laufender Stand
        vermerkt, der Update-Listener findet dann keinen Unterschied. Aendert
        dagegen "Neu konfigurieren" die ID, wird neu geladen.
        """
        entry = self.config_entry
        data = {**self.subentry.data, CONF_CHARACTER_ID: char_id}
        # Vorher vermerken: Der Listener startet sofort (eager task). Beim
        # Start ist runtime_data noch nicht gesetzt; dann vermerkt
        # async_setup_entry den Stand an seinem Ende.
        if (runtime := getattr(entry, "runtime_data", None)) is not None:
            snapshot = config_snapshot(entry)
            snapshot[1][self.subentry.subentry_id] = (self.subentry.title, dict(data))
            runtime.config_snapshot = snapshot
        self.hass.config_entries.async_update_subentry(entry, self.subentry, data=data)
        self.subentry = entry.subentries[self.subentry.subentry_id]

    def _create_issue(self, reason: str) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id(self.subentry.subentry_id),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=reason,
            translation_placeholders={"character": self.subentry.title},
        )


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
        # Endpunkte aus NOT_FOUND_IS_FINAL, die 404 meldeten, z. B. hunter_pets
        # fuer Nicht-Jaeger; bis zum Neuladen nicht mehr abgefragt.
        self._absent: set[str] = set()
        # Endpunkte, die seit dem Start schon Daten lieferten.
        self._delivered: set[str] = set()
        # Beruf-ID -> Name aus den statischen Spieldaten (Sprache der Region).
        self._profession_names: dict[int, str] = {}
        # Stufen-ID -> Name, aus derselben Abfrage wie die Berufsnamen.
        self._tier_names: dict[int, str] = {}
        # Medien-ID eines Items -> URL des Symbols; Symbole aendern sich nicht.
        self._item_icons: dict[int, str] = {}
        # Brackets mit Sensor; setzt sensor.py beim Anlegen, None bis dahin.
        # Brackets ohne Sensor werden bis zum Neuladen nicht abgefragt.
        self.pvp_bracket_sensors: set[str] | None = None
        # True, sobald alle Plattformen ihre Entitaeten angelegt haben (setzt
        # __init__.py). Danach entsteht bis zum Neuladen keine neue Entitaet;
        # Endpunkte ohne Entitaet werden nicht mehr abgefragt.
        self.entities_ready = False
        # Talentbaeume der Spezialisierung je Pfad; statisch bis zum Neuladen.
        self._talent_trees: dict[str, dict[str, Any]] = {}
        # Item-ID -> Name fuer den Transmog (Sprache der Region).
        self._transmog_names: dict[int, str] = {}
        # Klassen-ID -> Name fuer die Gildenmitglieder (Sprache der Region).
        self._class_names: dict[int, str] = {}
        # Hauptkategorien der Erfolge: ID -> Name in der Sprache der Region.
        self._achievement_roots: dict[int, str] = {}
        # Symbole aus den statischen Spieldaten, z. B. "profession/164" -> URL.
        self._media = MediaCache(self)

    def entity_enabled(self, key: str, platform: str = "sensor") -> bool:
        """Ist die Entitaet aktiv? Vor dem Anlegen der Entitaeten immer ja."""
        if not self.entities_ready:
            return True
        ent_reg = er.async_get(self.hass)
        entity_id = ent_reg.async_get_entity_id(
            platform, DOMAIN, f"{self.subentry.unique_id}-{key}"
        )
        entry = ent_reg.async_get(entity_id) if entity_id else None
        return entry is not None and entry.disabled_by is None

    def needed_endpoints(self) -> set[str]:
        """Endpunkte mit mindestens einer aktiven Entitaet.

        Vor dem Anlegen der Entitaeten zaehlen auch Endpunkte, fuer die noch
        keine Entitaet existiert: Ob sie entsteht, haengt an der Antwort.
        """
        ent_reg = er.async_get(self.hass)
        prefix = f"{self.subentry.unique_id}-"
        registered: set[str] = set()
        enabled: set[str] = set()
        for entry in er.async_entries_for_config_entry(
            ent_reg, self.config_entry.entry_id
        ):
            if not entry.unique_id.startswith(prefix):
                continue
            key = entry.unique_id[len(prefix) :]
            endpoints = {endpoint_for_key(key), *EXTRA_ENDPOINTS.get(key, ())}
            endpoints.discard(None)
            if not endpoints:
                continue
            registered |= endpoints
            if entry.disabled_by is None:
                enabled |= endpoints
        needed = set(enabled)
        if not self.entities_ready:
            needed |= set(DETAIL_ENDPOINTS) - registered
        if not self.mythic_plus:
            needed.discard("mythic_season")
        if self.pvp_bracket_sensors == set():
            # Kein Bracket mit Sensor: nichts abzufragen.
            needed.discard("pvp_brackets")
        return {
            e for e in needed if self.supports_endpoint(e) and e not in self._absent
        }

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
        if reason := self._profile.identity_problem:
            # Blizzard ordnet die Daten nicht mehr diesem Charakter zu.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key=reason,
                translation_placeholders={"character": self.subentry.title},
            )
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
            guild = None
            if "{guild}" in resource:
                guild = p.guild_path((self._profile.data or {}).get("profile"))
                if guild is None:
                    # Ohne Gilde gibt es nichts abzufragen.
                    data[endpoint] = None
                    continue
            attempted += 1
            try:
                if guild is not None:
                    data[endpoint] = await self.client.get_profile_data(
                        self.region, self.suffix, resource.format(guild=guild)
                    )
                elif "{bracket}" in resource:
                    data[endpoint] = await self._pvp_brackets(resource)
                else:
                    data[endpoint] = await self.client.get_character_resource(
                        self.region, self.realm, self.character, self.suffix, resource
                    )
            except BattleNetNotFound:
                # Lieferte der Endpunkt seit dem Start schon Daten, gilt ein
                # 404 nicht als endgueltig (z. B. kurzer Fehler der API).
                if endpoint in NOT_FOUND_IS_FINAL and endpoint not in self._delivered:
                    self._absent.add(endpoint)
                data[endpoint] = None
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                # Alten Stand behalten, beim naechsten Takt erneut versuchen.
                failed += 1
                _LOGGER.debug("%s: %s fehlgeschlagen: %s", self.name, endpoint, err)
                continue
            if data[endpoint] is not None:
                self._delivered.add(endpoint)
            self._fetched[endpoint] = now
        if attempted and failed == attempted:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="details_failed"
            )
        await self._lookup_profession_names(data.get("professions"))
        data["profession_names"] = dict(self._profession_names)
        data["tier_names"] = dict(self._tier_names)
        await self._lookup_item_icons(data.get("equipment"))
        data["item_icons"] = dict(self._item_icons)
        if data.get("achievements") is not None:
            await self._lookup_achievement_roots()
        data["achievement_roots"] = dict(self._achievement_roots)
        await self._lookup_class_names(data.get("guild_roster"))
        data["class_names"] = dict(self._class_names)
        await self._lookup_transmog_names(data.get("appearance"), data.get("equipment"))
        data["transmog_names"] = dict(self._transmog_names)
        data["talent_tree"] = await self._talent_tree(data.get("specializations"))
        await self._media.lookup(
            [
                *(("profession", i) for i in self._profession_ids(data)),
                *(
                    ("journal-instance", i)
                    for i in p.raid_instances(data.get("raids")).values()
                ),
                *(
                    ("achievement", a["id"])
                    for a in p.recent_achievements(data.get("achievements"))[-5:]
                ),
            ]
        )
        data["media_urls"] = self._media.urls()
        return data

    async def _pvp_brackets(self, resource: str) -> dict[str, Any]:
        """Je Bracket die Antwort; None, wenn die API 404 meldet.

        Vor dem Anlegen der Sensoren alle aus PVP_BRACKETS, danach nur die mit
        Sensor. Andere Fehler gelten fuer den ganzen Endpunkt (alter Stand bleibt).
        """
        result: dict[str, Any] = {}
        wanted = self.pvp_bracket_sensors
        for bracket in PVP_BRACKETS:
            if wanted is not None and bracket not in wanted:
                continue
            try:
                result[bracket] = await self.client.get_character_resource(
                    self.region,
                    self.realm,
                    self.character,
                    self.suffix,
                    resource.format(bracket=bracket),
                )
            except BattleNetNotFound:
                result[bracket] = None
        return result

    async def _talent_tree(self, specs: Any) -> dict[str, Any] | None:
        """Talentbaum der Spezialisierung mit der Verteilung des aktiven Loadouts.

        Nur solange der Sensor "Talentbaum" aktiv ist. Der Baum kommt einmal je
        Start; die Symbole erst nach dem Anlegen der Entitaeten, damit der Start
        nicht auf rund hundert Abfragen wartet.
        """
        if not self.entity_enabled("talent_tree"):
            return None
        loadout = p.active_loadout(specs)
        path = p.spec_tree_path(loadout)
        if path is None or not self.supports_static(path):
            return None
        if path not in self._talent_trees:
            try:
                self._talent_trees[path] = await self.client.get_static_data(
                    self.region, self.suffix, path
                )
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                _LOGGER.debug("Talentbaum %s fehlt: %s", path, err)
                return None
        tree = self._talent_trees[path]
        hero_id = p.hero_tree_id(specs, loadout)
        if self.entities_ready:
            await self._media.lookup(
                [("spell", i) for i in p.tree_spell_ids(tree, hero_id)]
            )
        return p.talent_tree(tree, loadout, hero_id, self._media.urls())

    async def _lookup_transmog_names(
        self, appearance: dict[str, Any] | None, equipment: dict[str, Any] | None
    ) -> None:
        """Namen der Transmog-Gegenstaende, nur wenn die IDs belegt Item-IDs sind.

        Weder Doku noch Typdefinitionen sagen, was transmog[].id ist. Stimmt die
        ID auf mindestens einem Platz mit dem dort angelegten Item ueberein (ein
        nicht transmogrifizierter Platz), sind es Item-IDs. Dann kommen die Namen
        aus der Ausruestung oder aus item/{id}, sonst gibt es keine.
        """
        items = p.equipment(equipment)
        transmog = p.appearance(appearance)["transmog"]
        if not any(
            isinstance(t["id"], int)
            and t["id"] == (items.get(t["slot"]) or {}).get("item_id")
            for t in transmog
        ):
            return
        equipped = {
            i["item_id"]: i["name"]
            for i in items.values()
            if isinstance(i.get("item_id"), int) and isinstance(i.get("name"), str)
        }
        for t in transmog:
            item_id = t["id"]
            if not isinstance(item_id, int) or item_id in self._transmog_names:
                continue
            if item_id in equipped:
                self._transmog_names[item_id] = equipped[item_id]
                continue
            path = f"item/{item_id}"
            if not self.supports_static(path):
                continue
            try:
                static = await self.client.get_static_data(
                    self.region, self.suffix, path
                )
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                _LOGGER.debug("Item %s nicht nachgeschlagen: %s", item_id, err)
                continue
            if isinstance(name := static.get("name"), str) and name:
                self._transmog_names[item_id] = name

    async def _lookup_class_names(self, roster: dict[str, Any] | None) -> None:
        """Klassennamen der Gildenmitglieder nachschlagen, jede Klasse einmal.

        Die Mitgliederliste nennt nur die Klassen-ID. Faellt das Nachschlagen
        aus, bleibt die ID bis zum naechsten Takt ohne Namen.
        """
        for class_id in p.roster_class_ids(roster):
            path = f"playable-class/{class_id}"
            if class_id in self._class_names or not self.supports_static(path):
                continue
            try:
                static = await self.client.get_static_data(
                    self.region, self.suffix, path
                )
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                _LOGGER.debug("Klasse %s nicht nachgeschlagen: %s", class_id, err)
                continue
            if isinstance(name := static.get("name"), str) and name:
                self._class_names[class_id] = name

    @staticmethod
    def _profession_ids(data: dict[str, Any]) -> list[int]:
        return list(
            p.professions(
                data.get("professions"),
                data.get("profession_names"),
                data.get("tier_names"),
            )
        )

    async def _lookup_achievement_roots(self) -> None:
        """Hauptkategorien der Erfolge einmalig nachschlagen.

        Die Erfolge-Seite mischt Haupt- und Unterkategorien und nennt sie auf
        Englisch. Faellt das Nachschlagen aus, bleiben alle Kategorien.
        """
        if self._achievement_roots or not self.supports_static(
            "achievement-category/index"
        ):
            return
        try:
            index = await self.client.get_static_data(
                self.region, self.suffix, "achievement-category/index"
            )
        except BattleNetAuthError as err:
            raise _auth_failed(err) from err
        except BattleNetError as err:
            _LOGGER.debug("Erfolgskategorien nicht nachgeschlagen: %s", err)
            return
        for root in index.get("root_categories") or []:
            if (
                isinstance(root, dict)
                and isinstance(root.get("id"), int)
                and isinstance(name := root.get("name"), str)
            ):
                self._achievement_roots[root["id"]] = name

    async def _lookup_item_icons(self, equipment: dict[str, Any] | None) -> None:
        """Symbole der angelegten Items nachschlagen, jedes nur einmal.

        Die Ausruestungs-Seite nennt nur die Medien-ID. Faellt das Nachschlagen
        aus, fehlt das Symbol bis zum naechsten Takt.
        """
        for item in p.equipment(equipment).values():
            media_id = item["media_id"]
            if (
                not isinstance(media_id, int)
                or media_id in self._item_icons
                or not self.supports_static(f"media/item/{media_id}")
            ):
                continue
            try:
                media = await self.client.get_static_data(
                    self.region, self.suffix, f"media/item/{media_id}"
                )
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                _LOGGER.debug("Symbol fuer Item %s fehlt: %s", media_id, err)
                continue
            if url := p.icon_url(media):
                self._item_icons[media_id] = url

    async def _lookup_profession_names(
        self, professions: dict[str, Any] | None
    ) -> None:
        """Namen der Berufe und ihrer Stufen einmalig nachschlagen.

        Die Berufe-Seite eines Charakters liefert Namen auf Englisch, auch mit
        locale=de_DE. Faellt das Nachschlagen aus, bleibt der englische Name.
        """
        for group in ("primaries", "secondaries"):
            for entry in (professions or {}).get(group) or []:
                prof_id = (entry.get("profession") or {}).get("id")
                if (
                    not isinstance(prof_id, int)
                    or prof_id in self._profession_names
                    or not self.supports_static(f"profession/{prof_id}")
                ):
                    continue
                try:
                    static = await self.client.get_static_data(
                        self.region, self.suffix, f"profession/{prof_id}"
                    )
                except BattleNetError as err:
                    _LOGGER.debug("Beruf %s nicht nachgeschlagen: %s", prof_id, err)
                    continue
                if isinstance(name := static.get("name"), str) and name:
                    self._profession_names[prof_id] = name
                for tier in static.get("skill_tiers") or []:
                    if (
                        isinstance(tier, dict)
                        and isinstance(tier.get("id"), int)
                        and isinstance(tier_name := tier.get("name"), str)
                        and tier_name
                    ):
                        self._tier_names[tier["id"]] = tier_name


class MediaCache:
    """Symbole aus den statischen Spieldaten, je Objekt nur einmal abgefragt.

    Schluessel wie der Pfad unter /data/wow/media, z. B. "playable-class/8".
    Faellt eine Abfrage aus, fehlt das Symbol bis zum naechsten Takt.
    """

    def __init__(self, coordinator: _CharacterMixin) -> None:
        self._coordinator = coordinator
        self._urls: dict[str, str] = {}

    async def lookup(self, items: list[tuple[str, Any]]) -> None:
        c = self._coordinator
        for kind, obj_id in items:
            key = f"{kind}/{obj_id}"
            if (
                not isinstance(obj_id, int)
                or key in self._urls
                or not c.supports_static(f"media/{key}")
            ):
                continue
            try:
                media = await c.client.get_static_data(
                    c.region, c.suffix, f"media/{key}"
                )
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                _LOGGER.debug("Symbol %s fehlt: %s", key, err)
                continue
            if url := p.icon_url(media):
                self._urls[key] = url

    def urls(self) -> dict[str, str]:
        return dict(self._urls)


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
        game_version: str,
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
        self.game_version = game_version
        self.mythic_plus: bool = GAME_VERSIONS[game_version]["mythic_plus"]
        self._fetched: dict[str, float] = {}
        # Gibt es den Sensor "WoW-Marke"? Setzt sensor.py beim Anlegen; None
        # bis dahin. Ohne Sensor wird die WoW-Marke nicht mehr abgefragt.
        self.token_sensor: bool | None = None
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
        """Jede Teilabfrage fuer sich: Faellt eine aus, bleibt ihr alter Wert.

        Nur wenn alle ausfallen, gilt die Abfrage als gescheitert.
        """
        now = time.monotonic()
        data: dict[str, Any] = dict(self.data or {"realms": {}})
        data["realms"] = dict(data.get("realms") or {})
        parts: list[tuple[str, Any]] = []
        if self.token_sensor is not False and self._due("token", 60, now):
            parts.append(("token", self._token))
        if self.mythic_plus and self._due("period", 60, now):
            parts.append(("period", self._weekly_reset))
        if self.mythic_plus and self._due("season", 360, now):
            parts.append(("season", self._season))
        realms = sorted(self.realms)

        errors: list[BattleNetError] = []
        for key, fetch in parts:
            try:
                value = await fetch()
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                errors.append(err)
                _LOGGER.debug("%s: %s fehlgeschlagen: %s", self.name, key, err)
                continue
            data[{"period": "reset", "season": "season_id"}.get(key, key)] = value
            self._fetched[key] = now
        for slug in realms:
            try:
                data["realms"][slug] = await self._realm_status(slug)
            except BattleNetAuthError as err:
                raise _auth_failed(err) from err
            except BattleNetError as err:
                errors.append(err)
                _LOGGER.debug("%s: Realm %s fehlgeschlagen: %s", self.name, slug, err)
        if errors and len(errors) == len(parts) + len(realms):
            raise _update_failed(errors[0])
        return data

    async def _token(self) -> int | None:
        token = await self._get("token/index")
        price = (token or {}).get("price")
        # Preis in Kupfer: 1 Gold = 100 Silber = 10.000 Kupfer.
        return price // 10000 if isinstance(price, int) else None

    async def _season(self) -> int | None:
        index = await self._get("mythic-keystone/season/index")
        return ((index or {}).get("current_season") or {}).get("id")

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
