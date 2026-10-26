"""Diagnose: API-Antworten ohne Zugangsdaten, zum Pruefen der Feldnamen."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from .coordinator import WowConfigEntry

TO_REDACT = {CONF_CLIENT_ID, CONF_CLIENT_SECRET}


def _shrink(endpoint: str, data: Any) -> Any:
    """Grosse Listen kuerzen; fuer die Pruefung reichen Aufbau und Anzahl."""
    if not isinstance(data, dict):
        return data
    if endpoint == "achievements":
        return {
            "total_points": data.get("total_points"),
            "total_quantity": data.get("total_quantity"),
            "recent_events": (data.get("recent_events") or [])[:5],
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
    if endpoint in ("mounts", "pets", "toys"):
        items = data.get(endpoint) or []
        return {"count": len(items), "first": items[:2]}
    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WowConfigEntry
) -> dict[str, Any]:
    runtime = entry.runtime_data
    characters = {}
    for subentry_id, coordinator in runtime.coordinators.items():
        detail = runtime.details[subentry_id]
        characters[coordinator.subentry.title] = {
            "game_version": coordinator.game_version,
            "profile": coordinator.data,
            "details": {
                endpoint: _shrink(endpoint, value)
                for endpoint, value in (detail.data or {}).items()
            },
            "needed_endpoints": sorted(detail.needed_endpoints()),
        }
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "characters": characters,
        "worlds": {
            f"{region}{suffix}": world.data
            for (region, suffix), world in runtime.worlds.items()
        },
    }
