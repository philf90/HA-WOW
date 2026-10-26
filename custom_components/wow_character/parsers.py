"""Auswertung der API-Antworten in Sensorwerte.

Die Feldnamen stammen aus den Typdefinitionen von @blizzard-api/wow und aus
homeassistant-wow-blizzard, das sie nach eigener Angabe live geprueft hat.
Fehlende Felder ergeben None statt eines Fehlers.
"""

from __future__ import annotations

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
            events.append(
                {
                    "achievement": name_of(event.get("achievement")),
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
    data: dict[str, Any] | None, names: dict[int, str] | None = None
) -> dict[int, dict[str, Any]]:
    """Beruf-ID -> Name, Skill und Stufe der neuesten Erweiterungsstufe.

    names: nachgeschlagene Namen, die den englischen Namen der Antwort ersetzen.
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
                "tier": name_of(newest.get("tier")),
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
