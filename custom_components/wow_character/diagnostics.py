"""Diagnose: API-Antworten ohne Zugangsdaten, zum Pruefen der Feldnamen.

Fuer den ganzen Eintrag (alle Charaktere und Spielwelten) und seit 0.27.0 je
Geraet: ein Charakter mit der Spielwelt seiner Region oder eine Spielwelt.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .api import BattleNetError, region_locale
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, DOMAIN
from .coordinator import (
    WowConfigEntry,
    WowCoordinator,
    WowDetailCoordinator,
    WowWorldCoordinator,
)

TO_REDACT = {CONF_CLIENT_ID, CONF_CLIENT_SECRET}
# Was einen Spieler erkennbar macht, unter jedem Schluessel "character": Name,
# ID und Verweis (key.href enthaelt Realm und Name). Betrifft vor allem andere
# Spieler: Gruppen der Mythic+-Laeufe, Gildenmitglieder und -aktivitaeten.
# Diagnosen landen oft oeffentlich in Issues.
_PLAYER_KEYS = ("name", "id", "key")

# Verweise des aktiven Loadouts auf seinen Talentbaum (Retail). Echte Antwort
# vom 28.10.2026: selected_spec_talent_tree zeigt auf
# "talent-tree/658/playable-specialization/64" (Endpunkt "Talent Tree"),
# selected_class_talent_tree auf "talent-tree/658" (Endpunkt "Talent Tree
# Nodes": alle Knoten der Klasse fuer alle Spezialisierungen, Verbindungen nur
# bei Heldentalenten). Die Doku nennt das Format nicht.
_TALENT_TREE_HREF = re.compile(
    r"/data/wow/(talent-tree/\d+(?:/playable-specialization/\d+)?)"
)


def _selected_talents(talents: Any) -> list[dict[str, Any]]:
    """Vergebene Talente ohne Tooltip-Texte: IDs und Rang zum Abgleich mit dem Baum."""
    result = []
    for talent in talents if isinstance(talents, list) else []:
        if not isinstance(talent, dict):
            continue
        tooltip = talent.get("tooltip") or {}
        result.append(
            {
                "id": talent.get("id"),
                "rank": talent.get("rank"),
                "default_points": talent.get("default_points"),
                "talent_id": (tooltip.get("talent") or {}).get("id"),
                "spell_id": (
                    (tooltip.get("spell_tooltip") or {}).get("spell") or {}
                ).get("id"),
            }
        )
    return result


def _tree_nodes(nodes: Any) -> list[dict[str, Any]]:
    """Knoten eines Talentbaums ohne Tooltip-Texte: Lage, Raenge, Verbindungen."""
    result = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        ranks = [r for r in node.get("ranks") or [] if isinstance(r, dict)]
        talents = []
        for rank in ranks:
            tooltips = [rank.get("tooltip"), *(rank.get("choice_of_tooltips") or [])]
            for tooltip in tooltips:
                if not isinstance(tooltip, dict):
                    continue
                spell = (tooltip.get("spell_tooltip") or {}).get("spell") or {}
                entry = {
                    "talent_id": (tooltip.get("talent") or {}).get("id"),
                    "spell_id": spell.get("id"),
                    "name": spell.get("name"),
                }
                if entry not in talents:
                    talents.append(entry)
        result.append(
            {
                "id": node.get("id"),
                "row": node.get("display_row"),
                "col": node.get("display_col"),
                "type": (node.get("node_type") or {}).get("type"),
                "ranks": len(ranks),
                "default_points": next(
                    (r["default_points"] for r in ranks if "default_points" in r), None
                ),
                "talents": talents,
                "unlocks": node.get("unlocks"),
                "locked_by": node.get("locked_by"),
            }
        )
    return result


def _talent_tree_path(specs: Any) -> str | None:
    """Pfad des Talentbaums zum aktiven Loadout der aktiven Spezialisierung."""
    if not isinstance(specs, dict):
        return None
    active = (specs.get("active_specialization") or {}).get("id")
    for spec in specs.get("specializations") or []:
        if (
            not isinstance(spec, dict)
            or (spec.get("specialization") or {}).get("id") != active
        ):
            continue
        for loadout in spec.get("loadouts") or []:
            if not isinstance(loadout, dict) or not loadout.get("is_active"):
                continue
            # Baum der Spezialisierung zuerst, sonst der Klassenbaum.
            for key in ("selected_spec_talent_tree", "selected_class_talent_tree"):
                tree = loadout.get(key) or {}
                href = (tree.get("key") or {}).get("href") or ""
                if match := _TALENT_TREE_HREF.search(href):
                    return match.group(1)
            return None
    return None


async def _talent_tree(detail: WowDetailCoordinator) -> dict[str, Any] | None:
    """Talentbaum der aktiven Spezialisierung, nur fuer die Diagnose abgefragt.

    Dient dem Abgleich, ob die IDs der vergebenen Talente die Knoten-IDs des
    Baums sind; die Doku sagt das nicht.
    """
    path = _talent_tree_path((detail.data or {}).get("specializations"))
    if path is None or not detail.supports_static(path):
        return None
    try:
        tree = await detail.client.get_static_data(detail.region, detail.suffix, path)
    except BattleNetError as err:
        return {"path": path, "error": repr(err)}
    return {
        "path": path,
        "name": tree.get("name"),
        "class_talent_nodes": _tree_nodes(tree.get("class_talent_nodes")),
        "spec_talent_nodes": _tree_nodes(tree.get("spec_talent_nodes")),
        "talent_nodes": _tree_nodes(tree.get("talent_nodes")),
        "hero_talent_trees": [
            {
                "id": hero.get("id"),
                "name": hero.get("name"),
                "nodes": _tree_nodes(hero.get("hero_talent_nodes")),
            }
            for hero in tree.get("hero_talent_trees") or []
            if isinstance(hero, dict)
        ],
        "restriction_lines": tree.get("restriction_lines"),
    }


def _without_players(data: Any) -> Any:
    """Kopie ohne Name, ID und Verweis unter jedem Schluessel "character"."""
    if isinstance(data, list):
        return [_without_players(item) for item in data]
    if not isinstance(data, dict):
        return data
    return {
        key: (
            {k: _without_players(v) for k, v in value.items() if k not in _PLAYER_KEYS}
            if key == "character" and isinstance(value, dict)
            else _without_players(value)
        )
        for key, value in data.items()
    }


def _shrink(endpoint: str, data: Any) -> Any:
    """Grosse Listen kuerzen; fuer die Pruefung reichen Aufbau und Anzahl."""
    if not isinstance(data, dict):
        return data
    if endpoint == "achievements":
        return {
            "total_points": data.get("total_points"),
            "total_quantity": data.get("total_quantity"),
            "recent_events": (data.get("recent_events") or [])[:5],
            "category_progress": data.get("category_progress"),
        }
    if endpoint == "game_statistics":
        categories = [c for c in data.get("categories") or [] if isinstance(c, dict)]
        return {
            "categories": [
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "statistics": len(c.get("statistics") or []),
                    "sub_categories": len(c.get("sub_categories") or []),
                }
                for c in categories
            ],
            "first": categories[:1],
        }
    if endpoint == "talent_tree":
        # Aufbereiteter Baum fuer den Sensor; Knoten nur als Anzahl, der
        # Baum selbst steht gekuerzt unter "talent_tree" des Charakters.
        return {
            k: (len(v) if k.endswith("_nodes") and isinstance(v, list) else v)
            for k, v in data.items()
        }
    if endpoint == "specializations":
        # Talentlisten mit Tooltips sind lang; IDs und Rang reichen zur Pruefung.
        return {
            **{k: v for k, v in data.items() if k != "specializations"},
            "specializations": [
                {
                    **{k: v for k, v in spec.items() if k != "loadouts"},
                    "loadouts": [
                        {
                            k: (_selected_talents(v) if k.endswith("_talents") else v)
                            for k, v in loadout.items()
                        }
                        for loadout in spec.get("loadouts") or []
                        if isinstance(loadout, dict)
                    ],
                }
                for spec in data.get("specializations") or []
                if isinstance(spec, dict)
            ],
        }
    if endpoint == "titles":
        items = data.get("titles") or []
        return {
            "active_title": data.get("active_title"),
            "count": len(items),
            "first": items[:3],
        }
    if endpoint == "professions":
        # Rezeptlisten machen die Diagnose sehr gross und helfen nicht.
        return {
            group: [
                {
                    **entry,
                    "tiers": [
                        {k: v for k, v in tier.items() if k != "known_recipes"}
                        for tier in entry.get("tiers") or []
                    ],
                }
                for entry in data.get(group) or []
            ]
            for group in ("primaries", "secondaries")
        }
    if endpoint == "equipment":
        # Vollstaendig, weil der Tooltip fast alle Felder nutzt; nur Links,
        # Bonus-IDs und Vorlage-IDs fallen weg.
        drop = {"bonus_list", "context", "modified_appearance_id"}
        return {
            "equipped_items": [
                {k: v for k, v in item.items() if k not in drop}
                for item in data.get("equipped_items") or []
                if isinstance(item, dict)
            ]
        }
    if endpoint == "reputations":
        items = data.get("reputations") or []
        return {"count": len(items), "first": items[:3]}
    if endpoint == "quests":
        return {"count": len(data.get("quests") or [])}
    if endpoint == "guild_activity":
        items = data.get("activities") or []
        return {"count": len(items), "first": items[:3]}
    if endpoint == "guild_roster":
        # Grosse Gilden haben hunderte Mitglieder.
        items = data.get("members") or []
        return {"count": len(items), "first": items[:3]}
    if endpoint == "hunter_pets":
        # Der Stall eines Jaegers kann viele Begleiter fassen.
        items = data.get("hunter_pets") or []
        return {"count": len(items), "first": items[:3]}
    if endpoint in ("mounts", "pets", "toys"):
        items = data.get(endpoint) or []
        return {"count": len(items), "first": items[:2]}
    if endpoint == "heirlooms":
        # Fuer den Sensor-Entwurf: Anzahl und Verteilung der Aufwertungsstufen.
        items = [i for i in data.get("heirlooms") or [] if isinstance(i, dict)]
        levels: dict[str, int] = {}
        for item in items:
            level = str((item.get("upgrade") or {}).get("level"))
            levels[level] = levels.get(level, 0) + 1
        return {
            "keys": sorted(data),
            "count": len(items),
            "upgrade_levels": dict(sorted(levels.items())),
            "first": items[:3],
        }
    if endpoint == "transmogs":
        # Je Platz oft hunderte Vorlagen (seit 0.31.0 schon beim Abruf auf IDs
        # gekuerzt); Anzahl je Platz und Beispiele reichen.
        sets = data.get("appearance_sets") or []
        slots = [s for s in data.get("slots") or [] if isinstance(s, dict)]
        return {
            "keys": sorted(data),
            "appearance_sets": len(sets),
            "first_sets": sets[:3],
            "slots": [
                {"slot": s.get("slot"), "appearances": len(s.get("appearances") or [])}
                for s in slots
            ],
            "first_appearances": (slots[0].get("appearances") or [])[:2]
            if slots
            else [],
        }
    return data


async def _character(
    coordinator: WowCoordinator, detail: WowDetailCoordinator
) -> dict[str, Any]:
    return {
        "game_version": coordinator.game_version,
        "profile": _without_players(coordinator.data),
        "details": {
            endpoint: _without_players(_shrink(endpoint, value))
            for endpoint, value in (detail.data or {}).items()
        },
        "needed_endpoints": sorted(detail.needed_endpoints()),
        "talent_tree": await _talent_tree(detail),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WowConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    characters = {
        coordinator.subentry.title: await _character(
            coordinator, runtime.details[subentry_id]
        )
        for subentry_id, coordinator in runtime.coordinators.items()
    }
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        # Locale je Region der Spielwelten, wie sie die Abfragen nutzen
        "locales": {
            f"{region}{suffix}": region_locale(region, runtime.client.language)
            for region, suffix in runtime.worlds
        },
        "characters": characters,
        "worlds": {
            f"{region}{suffix}": world.data
            for (region, suffix), world in runtime.worlds.items()
        },
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: WowConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Nur ein Charakter (mit der Spielwelt seiner Region) oder eine Spielwelt.

    Kleiner als die Diagnose des Eintrags und ohne die anderen Charaktere, z. B.
    fuer einen Fehlerbericht zu einem Charakter. Zugangsdaten enthaelt sie nicht.
    Geraete-Kennungen wie in entity.py.
    """
    runtime = entry.runtime_data
    idents = {ident for domain, ident in device.identifiers if domain == DOMAIN}

    def world_data(world: WowWorldCoordinator) -> dict[str, Any]:
        return {
            "world": f"{world.region}{world.suffix}",
            "locale": region_locale(world.region, runtime.client.language),
            "data": world.data,
        }

    base = {"options": dict(entry.options)}
    for subentry_id, coordinator in runtime.coordinators.items():
        if coordinator.subentry.unique_id in idents:
            world = runtime.worlds.get((coordinator.region, coordinator.suffix))
            return {
                **base,
                "character": {
                    "title": coordinator.subentry.title,
                    **await _character(coordinator, runtime.details[subentry_id]),
                },
                "world": world_data(world) if world else None,
            }
    for (region, suffix), world in runtime.worlds.items():
        if f"{entry.entry_id}-world-{region}{suffix}" in idents:
            return {**base, "world": world_data(world)}
    # Geraet ohne Daten (z. B. Charakter gerade entfernt)
    return base
