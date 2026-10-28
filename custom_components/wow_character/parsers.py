"""Auswertung der API-Antworten in Sensorwerte.

Die Feldnamen stammen aus den Typdefinitionen von @blizzard-api/wow und aus
homeassistant-wow-blizzard, das sie nach eigener Angabe live geprueft hat.
Fehlende Felder ergeben None statt eines Fehlers.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

RAID_DIFFICULTIES = {
    "raid_lfr": "LFR",
    "raid_normal": "NORMAL",
    "raid_heroic": "HEROIC",
    "raid_mythic": "MYTHIC",
}


def name_of(obj: Any) -> str | None:
    return obj.get("name") if isinstance(obj, dict) else None


def timestamp(ms: Any) -> datetime | None:
    """Millisekunden seit 1970 in eine Zeit umwandeln."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC) if isinstance(ms, int) else None


def active_title(profile: dict[str, Any]) -> str | None:
    title = profile.get("active_title")
    if not isinstance(title, dict):
        return None
    text = title.get("display_string") or title.get("name")
    if isinstance(text, str) and "{name}" in text:
        # Format ist ungeprueft; ein Platzhalter wird durch den Namen ersetzt.
        text = text.replace("{name}", profile.get("name") or "")
    return text


def color_hex(color: Any) -> str | None:
    """RGBA-Objekt der API in "#rrggbb" umwandeln."""
    if not isinstance(color, dict):
        return None
    rgb = [color.get(k) for k in ("r", "g", "b")]
    if not all(isinstance(v, (int, float)) for v in rgb):
        return None
    # Werte im Bereich 0-1 auf 0-255 hochrechnen, falls die API so liefert.
    if all(0 <= v <= 1 for v in rgb) and any(isinstance(v, float) for v in rgb):
        rgb = [v * 255 for v in rgb]
    return "#" + "".join(f"{round(v):02x}" for v in rgb)


def _current_expansion(raids: dict[str, Any] | None) -> dict[str, Any] | None:
    """Neueste Erweiterung in der Antwort (hoechste ID), wie homeassistant-wow-blizzard."""
    expansions = [
        e for e in (raids or {}).get("expansions") or [] if isinstance(e, dict)
    ]
    if not expansions:
        return None
    return max(expansions, key=lambda e: (e.get("expansion") or {}).get("id", 0))


def raid_progress(
    raids: dict[str, Any] | None, difficulty: str
) -> tuple[int | None, dict[str, Any]]:
    """Besiegte Bosse einer Schwierigkeit in der neuesten Erweiterung."""
    expansion = _current_expansion(raids)
    if expansion is None:
        return None, {}
    done = total = 0
    per_raid: dict[str, str] = {}
    for instance in expansion.get("instances") or []:
        for mode in instance.get("modes") or []:
            if (mode.get("difficulty") or {}).get("type") != difficulty:
                continue
            progress = mode.get("progress") or {}
            completed = progress.get("completed_count", 0)
            count = progress.get("total_count", 0)
            done += completed
            total += count
            per_raid[name_of(instance.get("instance")) or "?"] = f"{completed}/{count}"
    return done, {
        "expansion": name_of(expansion.get("expansion")),
        "total_bosses": total,
        "raids": per_raid,
    }


def boss_kills(raids: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Alle Bosse mit Zeitpunkt des letzten Kills, ueber alle Erweiterungen."""
    kills = []
    for expansion in (raids or {}).get("expansions") or []:
        for instance in expansion.get("instances") or []:
            for mode in instance.get("modes") or []:
                for enc in (mode.get("progress") or {}).get("encounters") or []:
                    ts = enc.get("last_kill_timestamp")
                    if not isinstance(ts, int):
                        continue
                    kills.append(
                        {
                            "boss": name_of(enc.get("encounter")),
                            "raid": name_of(instance.get("instance")),
                            "difficulty": name_of(mode.get("difficulty")),
                            "timestamp": ts,
                        }
                    )
    return sorted(kills, key=lambda k: k["timestamp"])


def recent_achievements(achievements: dict[str, Any] | None) -> list[dict[str, Any]]:
    events = []
    for event in (achievements or {}).get("recent_events") or []:
        ts = event.get("timestamp")
        if isinstance(ts, int):
            achievement = event.get("achievement") or {}
            events.append(
                {
                    "achievement": name_of(achievement),
                    "id": achievement.get("id"),
                    "timestamp": ts,
                }
            )
    return sorted(events, key=lambda e: e["timestamp"])


def mythic_season(season: dict[str, Any] | None) -> dict[str, Any]:
    runs = [r for r in (season or {}).get("best_runs") or [] if isinstance(r, dict)]
    best = max((r.get("keystone_level", 0) for r in runs), default=None)
    return {
        "best_key": best,
        "runs_timed": sum(1 for r in runs if r.get("is_completed_within_time"))
        if season
        else None,
        "best_runs": {
            name_of(r.get("dungeon")) or "?": (
                f"+{r.get('keystone_level')}"
                + (" in Zeit" if r.get("is_completed_within_time") else "")
            )
            for r in runs
        },
        "runs": [_mythic_run(r) for r in runs],
    }


def _run_seconds(duration: Any) -> int | None:
    """Dauer eines Laufs in Sekunden.

    Die Einheit der API ist nicht belegt. Ein Lauf dauert zwischen etwa
    10 Minuten und wenigen Stunden: in Sekunden unter 100.000, in
    Millisekunden darueber. Beide Faelle werden so erkannt.
    """
    if not isinstance(duration, (int, float)) or duration <= 0:
        return None
    return round(duration / 1000) if duration > 100_000 else round(duration)


def _mythic_run(run: dict[str, Any]) -> dict[str, Any]:
    """Ein bester Lauf mit Dauer, Affixen, Wertung und Gruppe."""
    duration = run.get("duration")
    rating = run.get("mythic_rating") or {}
    return {
        "dungeon": name_of(run.get("dungeon")),
        "dungeon_id": (run.get("dungeon") or {}).get("id"),
        "level": run.get("keystone_level"),
        "timed": bool(run.get("is_completed_within_time")),
        "duration": _run_seconds(duration),
        "completed": (
            ts.isoformat()
            if (ts := timestamp(run.get("completed_timestamp")))
            else None
        ),
        "rating": round(rating["rating"], 1)
        if isinstance(rating.get("rating"), (int, float))
        else None,
        "color": color_hex(rating.get("color")),
        "affixes": [
            name for a in run.get("keystone_affixes") or [] if (name := name_of(a))
        ],
        "members": [
            {
                "name": name_of(m.get("character")),
                "realm": name_of((m.get("character") or {}).get("realm")),
                "spec": name_of(m.get("specialization")),
                "item_level": m.get("equipped_item_level"),
            }
            for m in run.get("members") or []
            if isinstance(m, dict)
        ],
    }


def _stat_value(stats: dict[str, Any], *keys: str) -> float | None:
    values = [
        (stats.get(k) or {}).get("value")
        for k in keys
        if isinstance(stats.get(k), dict)
    ]
    values = [v for v in values if isinstance(v, (int, float))]
    return round(max(values), 2) if values else None


def primary_stat(stats: dict[str, Any]) -> tuple[int | None, str | None]:
    best: tuple[int | None, str | None] = (None, None)
    for key in ("strength", "agility", "intellect"):
        value = (stats.get(key) or {}).get("effective")
        if isinstance(value, (int, float)) and (best[0] is None or value > best[0]):
            best = (value, key)
    return best


def stat(stats: dict[str, Any] | None, key: str) -> float | int | None:
    stats = stats or {}
    if key == "stat_health":
        return stats.get("health")
    if key == "stat_primary":
        return primary_stat(stats)[0]
    if key == "stat_crit":
        return _stat_value(stats, "melee_crit", "spell_crit", "ranged_crit")
    if key == "stat_haste":
        return _stat_value(stats, "melee_haste", "spell_haste", "ranged_haste")
    if key == "stat_mastery":
        return _stat_value(stats, "mastery")
    if key == "stat_versatility":
        value = stats.get("versatility_damage_done_bonus")
        return round(value, 2) if isinstance(value, (int, float)) else None
    return None


def professions(
    data: dict[str, Any] | None,
    names: dict[int, str] | None = None,
    tier_names: dict[int, str] | None = None,
) -> dict[int, dict[str, Any]]:
    """Beruf-ID -> Name, Skill und Stufe der neuesten Erweiterungsstufe.

    names, tier_names: nachgeschlagene Namen von Berufen und Stufen, die die
    englischen Namen der Antwort ersetzen.
    """
    result: dict[int, dict[str, Any]] = {}
    for group in ("primaries", "secondaries"):
        for entry in (data or {}).get(group) or []:
            prof = entry.get("profession") or {}
            if not isinstance(prof.get("id"), int):
                continue
            tiers = [t for t in entry.get("tiers") or [] if isinstance(t, dict)]
            newest = max(
                tiers, key=lambda t: (t.get("tier") or {}).get("id", 0), default={}
            )
            result[prof["id"]] = {
                "name": (names or {}).get(prof["id"]) or prof.get("name"),
                "skill": newest.get("skill_points", entry.get("skill_points")),
                "max_skill": newest.get(
                    "max_skill_points", entry.get("max_skill_points")
                ),
                "tier": (tier_names or {}).get((newest.get("tier") or {}).get("id"))
                or name_of(newest.get("tier")),
            }
    return result


def collection_count(data: dict[str, Any] | None, key: str) -> int | None:
    items = (data or {}).get(key)
    return len(items) if isinstance(items, list) else None


def media_url(media: dict[str, Any] | None, key: str) -> str | None:
    assets = {
        a.get("key"): a.get("value")
        for a in (media or {}).get("assets") or []
        if isinstance(a, dict)
    }
    if key == "avatar":
        return assets.get("avatar")
    # Ganzkoerperbild mit Ausweichbildern wie homeassistant-wow-blizzard.
    return (
        assets.get("main-raw")
        or assets.get("main")
        or assets.get("inset")
        or assets.get("avatar")
    )


# Steuerzeichen des Spiels wie "|cffffffff...|r" (Farbe) oder "|A:...|a"
# (Symbol). Ob die API sie in Texten liefert, ist ungeprueft; ohne sie
# bleibt der Text unveraendert.
_GAME_MARKUP = re.compile(r"\|A:[^|]*\|a|\|c[0-9a-fA-F]{8}|\|c[nN][^:]*:|\|r")


def clean_text(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    return " ".join(_GAME_MARKUP.sub("", text).split()) or None


def equipment(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Platz (z. B. "HEAD") -> angelegtes Item mit den Angaben des Arsenals."""
    result: dict[str, dict[str, Any]] = {}
    for item in (data or {}).get("equipped_items") or []:
        if not isinstance(item, dict):
            continue
        slot = (item.get("slot") or {}).get("type")
        if not isinstance(slot, str):
            continue
        quality = item.get("quality") or {}
        result[slot] = {
            "name": item.get("name"),
            "slot_name": name_of(item.get("slot")),
            "item_id": (item.get("item") or {}).get("id"),
            "media_id": (item.get("media") or {}).get("id"),
            "level": (item.get("level") or {}).get("value"),
            "quality": quality.get("type"),
            "quality_name": quality.get("name"),
            "enchantments": [
                text
                for e in item.get("enchantments") or []
                if isinstance(e, dict) and (text := clean_text(e.get("display_string")))
            ],
            "sockets": [
                {
                    "type": (s.get("socket_type") or {}).get("type"),
                    "gem": name_of(s.get("item")),
                }
                for s in item.get("sockets") or []
                if isinstance(s, dict)
            ],
            "set": name_of((item.get("set") or {}).get("item_set")),
            "tooltip": tooltip(item),
        }
    return result


def _text(obj: Any, *keys: str) -> str | None:
    """display_string (bereinigt) aus einem verschachtelten Feld."""
    for key in keys:
        obj = obj.get(key) if isinstance(obj, dict) else None
    return clean_text(obj)


def tooltip(item: dict[str, Any]) -> dict[str, Any]:
    """Zeilen des Item-Tooltips im Spiel, ohne leere Angaben.

    Texte kommen fertig in der Sprache der Region (display_string); Farben,
    die das Spiel einer Zeile gibt, als "#rrggbb".
    """
    quality = item.get("quality") or {}
    subclass = (
        None if item.get("is_subclass_hidden") else name_of(item.get("item_subclass"))
    )
    stats = []
    for stat in item.get("stats") or []:
        if not isinstance(stat, dict) or not (
            text := _text(stat, "display", "display_string")
        ):
            continue
        stats.append(
            {
                "text": text,
                "color": color_hex((stat.get("display") or {}).get("color")),
                # Zweitwerte (Tempo, Meisterschaft ...) stehen im Spiel gruen
                "bonus": bool(stat.get("is_equip_bonus")),
                "negated": bool(stat.get("is_negated")),
            }
        )
    weapon = item.get("weapon") or {}
    item_set = item.get("set") or {}
    sell = (item.get("sell_price") or {}).get("display_strings") or {}
    data: dict[str, Any] = {
        "name": item.get("name"),
        "quality": quality.get("type"),
        "quality_name": quality.get("name"),
        "name_description": _text(item, "name_description", "display_string"),
        "level": _text(item, "level", "display_string"),
        "binding": name_of(item.get("binding")),
        "unique": clean_text(item.get("unique_equipped")),
        "slot": name_of(item.get("inventory_type")),
        "subclass": subclass,
        "armor": _text(item, "armor", "display", "display_string"),
        "damage": _text(weapon, "damage", "display_string"),
        "speed": _text(weapon, "attack_speed", "display_string"),
        "dps": _text(weapon, "dps", "display_string"),
        "stats": stats,
        "enchantments": [
            text
            for e in item.get("enchantments") or []
            if isinstance(e, dict) and (text := clean_text(e.get("display_string")))
        ],
        # Edelstein-Wirkung, sonst sein Name, sonst die Sockelart (leer)
        "sockets": [
            text
            for s in item.get("sockets") or []
            if isinstance(s, dict)
            and (
                text := clean_text(s.get("display_string"))
                or name_of(s.get("item"))
                or name_of(s.get("socket_type"))
            )
        ],
        "spells": [
            text
            for sp in item.get("spells") or []
            if isinstance(sp, dict) and (text := clean_text(sp.get("description")))
        ],
        "set": None,
        "description": clean_text(item.get("description")),
        "durability": _text(item, "durability", "display_string"),
        "requirements": [
            text
            for text in (
                _text(item, "requirements", "playable_classes", "display_string"),
                _text(item, "requirements", "level", "display_string"),
            )
            if text
        ],
        "sell_price": (
            {k: sell.get(k) for k in ("header", "gold", "silver", "copper")}
            if sell
            else None
        ),
    }
    if item_set:
        data["set"] = {
            "name": clean_text(item_set.get("display_string"))
            or name_of(item_set.get("item_set")),
            "items": [
                {"name": name_of(i.get("item")), "equipped": bool(i.get("is_equipped"))}
                for i in item_set.get("items") or []
                if isinstance(i, dict)
            ],
            "effects": [
                {
                    "text": clean_text(e.get("display_string")),
                    "active": bool(e.get("is_active")),
                    # Anzahl Teile fuer den Bonus; der Text nennt sie nicht immer.
                    "required": e.get("required_count"),
                }
                for e in item_set.get("effects") or []
                if isinstance(e, dict)
            ],
        }
    return {k: v for k, v in data.items() if v not in (None, [], "")}


def icon_url(media: dict[str, Any] | None) -> str | None:
    """Symbol aus der Medien-Antwort eines Items."""
    assets = [a for a in (media or {}).get("assets") or [] if isinstance(a, dict)]
    for asset in assets:
        if asset.get("key") == "icon":
            return asset.get("value")
    return assets[0].get("value") if assets else None


def reputations(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Fraktionen mit Stufe und Fortschritt, in der Reihenfolge der API."""
    result = []
    for rep in (data or {}).get("reputations") or []:
        if not isinstance(rep, dict):
            continue
        standing = rep.get("standing") or {}
        entry = {
            "faction": name_of(rep.get("faction")),
            # Namen sind nicht eindeutig (z. B. zwei Fraktionen gleichen Namens).
            "faction_id": (rep.get("faction") or {}).get("id"),
            "standing": standing.get("name"),
            "value": standing.get("value"),
            "max": standing.get("max"),
        }
        if standing.get("renown_level") is not None:
            entry["renown"] = standing["renown_level"]
        paragon = rep.get("paragon")
        if isinstance(paragon, dict):
            entry["paragon"] = {
                "value": paragon.get("value"),
                "max": paragon.get("max"),
            }
        result.append(entry)
    return result


def empty_sockets(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Sockel ohne Edelstein, je Sockel ein Eintrag."""
    return [
        {"slot": slot, "slot_name": item.get("slot_name"), "type": socket["type"]}
        for slot, item in items.items()
        for socket in item.get("sockets") or []
        if not socket.get("gem")
    ]


def enchanted_slots(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Verzauberte Plaetze. Welche Plaetze verzauberbar sind, sagt die API nicht."""
    return [
        {
            "slot": slot,
            "slot_name": item.get("slot_name"),
            "enchantments": item["enchantments"],
        }
        for slot, item in items.items()
        if item.get("enchantments")
    ]


def item_sets(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Angelegte Sets, das vollstaendigste zuerst.

    Jedes Item eines Sets traegt die ganze Set-Angabe; doppelte fallen weg.
    """
    sets: dict[str, dict[str, Any]] = {}
    for item in items.values():
        info = (item.get("tooltip") or {}).get("set")
        name = item.get("set")
        if not info or not name or name in sets:
            continue
        parts = info.get("items") or []
        sets[name] = {
            "name": name,
            "equipped": sum(1 for i in parts if i.get("equipped")),
            "total": len(parts),
            "items": parts,
            "effects": info.get("effects") or [],
        }
    return sorted(sets.values(), key=lambda s: -s["equipped"])


def achievement_categories(
    data: dict[str, Any] | None, roots: dict[int, str] | None = None
) -> list[dict[str, Any]]:
    """Anzahl und Punkte der Erfolge je Kategorie.

    roots: Hauptkategorien (ID -> Name) aus den statischen Spieldaten. Mit
    ihnen bleiben nur die Hauptkategorien, in deren Reihenfolge und mit deren
    Namen; ohne sie alle Kategorien der Antwort.
    """
    entries = {
        (c.get("category") or {}).get("id"): {
            "category": name_of(c.get("category")),
            "id": (c.get("category") or {}).get("id"),
            "quantity": c.get("quantity"),
            "points": c.get("points"),
        }
        for c in (data or {}).get("category_progress") or []
        if isinstance(c, dict)
    }
    if not roots:
        return list(entries.values())
    return [
        {**entries[root_id], "category": name}
        for root_id, name in roots.items()
        if root_id in entries
    ]


def specialization(data: dict[str, Any] | None) -> dict[str, Any]:
    """Aktive Spezialisierung mit Heldentalenten und Talent-Code."""
    data = data or {}
    active = data.get("active_specialization") or {}
    loadout: dict[str, Any] = {}
    for spec in data.get("specializations") or []:
        if not isinstance(spec, dict):
            continue
        if (spec.get("specialization") or {}).get("id") != active.get("id"):
            continue
        loadouts = [lo for lo in spec.get("loadouts") or [] if isinstance(lo, dict)]
        loadout = next((lo for lo in loadouts if lo.get("is_active")), {})
    return {
        "name": name_of(active),
        "id": active.get("id"),
        "hero_talents": name_of(data.get("active_hero_talent_tree"))
        or name_of(loadout.get("selected_hero_talent_tree")),
        # Code zum Importieren im Talentfenster des Spiels.
        "loadout_code": loadout.get("talent_loadout_code"),
        "specializations": [
            name
            for spec in data.get("specializations") or []
            if isinstance(spec, dict) and (name := name_of(spec.get("specialization")))
        ],
    }


def titles(data: dict[str, Any] | None) -> list[str]:
    return [name for t in (data or {}).get("titles") or [] if (name := name_of(t))]


def game_statistics(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Werte des Statistik-Fensters, flach mit Kategorie und Unterkategorie."""
    result = []

    def add(stats: Any, category: str | None) -> None:
        for stat in stats or []:
            if isinstance(stat, dict) and isinstance(stat.get("id"), int):
                result.append(
                    {
                        "id": stat["id"],
                        "name": stat.get("name"),
                        "category": category,
                        "quantity": stat.get("quantity"),
                    }
                )

    for cat in (data or {}).get("categories") or []:
        if not isinstance(cat, dict):
            continue
        add(cat.get("statistics"), cat.get("name"))
        for sub in cat.get("sub_categories") or []:
            if isinstance(sub, dict):
                add(sub.get("statistics"), f"{cat.get('name')} / {sub.get('name')}")
    return result


def raid_instances(raids: dict[str, Any] | None) -> dict[str, int]:
    """Raids der neuesten Erweiterung: Name -> ID der Journal-Instanz."""
    expansion = _current_expansion(raids) or {}
    result = {}
    for instance in expansion.get("instances") or []:
        info = (instance or {}).get("instance") or {}
        if isinstance(info.get("id"), int) and (name := name_of(info)):
            result[name] = info["id"]
    return result


# Sammlungen: Endpunkt -> (Liste in der Antwort, Feld mit Name und ID).
# Haustiere zaehlen je Exemplar (eigene "id"), Name und Art aus "species".
COLLECTIBLES = {
    "mounts": ("mounts", "mount"),
    "pets": ("pets", "species"),
    "toys": ("toys", "toy"),
    "titles": ("titles", None),
}


def collectibles(
    endpoint: str, data: dict[str, Any] | None
) -> dict[int, dict[str, Any]]:
    """Eintraege einer Sammlung nach eindeutiger ID, mit Name und ID des Objekts."""
    key, inner = COLLECTIBLES[endpoint]
    result = {}
    for entry in (data or {}).get(key) or []:
        if not isinstance(entry, dict):
            continue
        obj = entry.get(inner) if inner else entry
        if not isinstance(obj, dict):
            continue
        # Haustier-Exemplare haben eine eigene ID, sonst gilt die des Objekts.
        uid = entry.get("id") if endpoint == "pets" else obj.get("id")
        if isinstance(uid, int):
            result[uid] = {"name": name_of(obj), "id": obj.get("id")}
    return result


_GUILD_HREF = re.compile(r"/data/wow/guild/([^/?]+)/([^/?]+)")


def guild_path(profile: dict[str, Any] | None) -> str | None:
    """ "guild/<realm>/<gilde>" aus dem Link im Profil; None ohne Gilde."""
    href = (((profile or {}).get("guild") or {}).get("key") or {}).get("href") or ""
    match = _GUILD_HREF.search(href)
    return f"guild/{match.group(1)}/{match.group(2)}" if match else None


def guild_activities(
    data: dict[str, Any] | None, limit: int = 10
) -> list[dict[str, Any]]:
    """Neueste Aktivitaeten der Gilde: Erfolge von Mitgliedern und Bosskills."""
    result = []
    for entry in (data or {}).get("activities") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("timestamp"), int):
            continue
        item: dict[str, Any] = {
            "type": (entry.get("activity") or {}).get("type"),
            "timestamp": timestamp(entry["timestamp"]).isoformat(),
        }
        if achievement := entry.get("character_achievement"):
            item["character"] = name_of(achievement.get("character"))
            item["achievement"] = name_of(achievement.get("achievement"))
        if encounter := entry.get("encounter_completed"):
            item["boss"] = name_of(encounter.get("encounter"))
            item["difficulty"] = (encounter.get("mode") or {}).get("name")
        result.append(item)
    result.sort(key=lambda i: i["timestamp"], reverse=True)
    return result[:limit]


def hunter_pets(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Begleiter eines Jaegers in der Reihenfolge der API.

    Felder wie in den Typdefinitionen von @blizzard-api/wow und
    @blizzard-api/classic-wow; is_active und is_summoned sind dort optional.
    """
    result = []
    for pet in (data or {}).get("hunter_pets") or []:
        if not isinstance(pet, dict):
            continue
        creature = pet.get("creature") or {}
        result.append(
            {
                "name": pet.get("name"),
                "level": pet.get("level"),
                "creature": name_of(creature),
                "creature_id": creature.get("id"),
                "slot": pet.get("slot"),
                "active": bool(pet.get("is_active")),
                "summoned": bool(pet.get("is_summoned")),
            }
        )
    return result


def roster_class_ids(roster: dict[str, Any] | None) -> list[int]:
    """Klassen-IDs der Gildenmitglieder, jede einmal, sortiert."""
    ids = {
        class_id
        for member in (roster or {}).get("members") or []
        if isinstance(member, dict)
        and isinstance(
            class_id := (
                (member.get("character") or {}).get("playable_class") or {}
            ).get("id"),
            int,
        )
    }
    return sorted(ids)


def guild_members(
    roster: dict[str, Any] | None, class_names: dict[int, str] | None = None
) -> list[dict[str, Any]]:
    """Mitglieder nach Rang (0 zuerst) und Name.

    Felder wie in den Typdefinitionen von @blizzard-api/classic-wow 4.2.0 und
    @blizzard-api/wow 4.1.4: character mit name, level und playable_class (nur
    ID); rank als Zahl. Namen der Raenge liefert die API nicht.
    """
    class_names = class_names or {}
    result = []
    for member in (roster or {}).get("members") or []:
        if not isinstance(member, dict):
            continue
        character = member.get("character") or {}
        class_id = (character.get("playable_class") or {}).get("id")
        result.append(
            {
                "name": character.get("name"),
                "level": character.get("level"),
                "class": class_names.get(class_id),
                "class_id": class_id,
                "rank": member.get("rank"),
            }
        )
    result.sort(
        key=lambda m: (
            m["rank"] if isinstance(m["rank"], int) else 999,
            str(m["name"] or ""),
        )
    )
    return result


def pvp_bracket(data: dict[str, Any] | None) -> dict[str, Any]:
    """Wertung und Spiele eines PvP-Brackets.

    Felder wie in den Typdefinitionen von @blizzard-api/wow 4.1.4
    (CharacterPvpBracketStatisticsResponse); fuer Classic gibt es keine.
    """
    data = data or {}
    season = data.get("season_match_statistics") or {}
    weekly = data.get("weekly_match_statistics") or {}
    return {
        "rating": data.get("rating"),
        "season_played": season.get("played"),
        "season_won": season.get("won"),
        "season_lost": season.get("lost"),
        "weekly_played": weekly.get("played"),
        "weekly_won": weekly.get("won"),
        "weekly_lost": weekly.get("lost"),
        "season_id": (data.get("season") or {}).get("id"),
    }


def appearance(
    data: dict[str, Any] | None, names: dict[int, str] | None = None
) -> dict[str, Any]:
    """Geschlecht und Transmog aus dem Aussehen.

    Felder wie in den Typdefinitionen von @blizzard-api/wow 4.1.4
    (CharacterAppearanceResponse); fuer Classic gibt es keine. Die API nennt
    je Gegenstand Platz, ID und Verzauberung; den Namen nur aus names (siehe
    _lookup_transmog_names im Coordinator).
    """
    data = data or {}
    names = names or {}
    return {
        "gender": name_of(data.get("gender")),
        "transmog": [
            {
                "slot": (item.get("slot") or {}).get("type"),
                "slot_name": (item.get("slot") or {}).get("name"),
                "id": item.get("id"),
                "name": names.get(item.get("id")),
                "enchant": item.get("enchant"),
            }
            for item in data.get("items") or []
            if isinstance(item, dict)
        ],
    }
