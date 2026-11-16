"""Aktion probe_namespaces: Namespaces fuer WoW Forever pruefen (seit 0.34.0).

Blizzard hat den Namespace fuer Forever nicht dokumentiert. Die Aktion fragt
je Region und Kandidat (GAME_VERSIONS["forever"]["namespaces"]) einen
Endpunkt im static- und einen im dynamic-Namespace ab, mit Charakter auch
Profilpfade im profile-Namespace, und meldet je Abfrage HTTP-Status, Schluessel
und wenige Beispielwerte. Sie liest nur und aendert keine Entitaeten.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import quote

from .api import BattleNetClient
from .const import GAME_VERSIONS

# Endpunkte ohne Charakter: Klassenliste (static) und Realm-Liste (dynamic).
STATIC_PATH = "/data/wow/playable-class/index"
DYNAMIC_PATH = "/data/wow/realm/index"
# Hoechstens so viele Realms aus einer Realm-Liste als Profilpfad probieren.
MAX_REALMS = 10
# Hoechstens so viele Schluessel und Listeneintraege je Antwort zeigen.
MAX_KEYS = 12
MAX_ITEMS = 3
MAX_TEXT = 80


def candidates() -> list[str]:
    """Namespace-Kandidaten fuer Forever, z. B. ["-forever", "-camelot"]."""
    return list(GAME_VERSIONS["forever"]["namespaces"])


def _label(value: Any) -> Any:
    """Kurzform eines Listeneintrags: id, name, slug oder die Schluessel."""
    if isinstance(value, dict):
        short = {
            key: _short(value[key])
            for key in ("id", "name", "slug", "type")
            if key in value and not isinstance(value[key], dict | list)
        }
        return short or {"keys": sorted(value)[:MAX_KEYS]}
    return _short(value)


def _short(value: Any) -> Any:
    if isinstance(value, list):
        return {
            "count": len(value),
            "first": [_label(item) for item in value[:MAX_ITEMS]],
        }
    if isinstance(value, dict):
        return _label(value)
    if isinstance(value, str):
        return value[:MAX_TEXT]
    return value


def sample(data: Any) -> dict[str, Any]:
    """Beispielwerte der obersten Ebene, ohne _links."""
    if not isinstance(data, dict):
        return {}
    keys = [key for key in data if key != "_links"][:MAX_KEYS]
    return {key: _short(data[key]) for key in keys}


async def _one(
    client: BattleNetClient, region: str, kind: str, suffix: str, path: str
) -> tuple[dict[str, Any], Any]:
    namespace = client.namespace(kind, suffix, region)
    status, data, error = await client.probe(region, path, namespace)
    ok = status == 200 and isinstance(data, dict)
    result = {
        "region": region,
        "namespace": namespace,
        "path": path,
        "status": status,
        "keys": sorted(key for key in data if key != "_links") if ok else [],
        "sample": sample(data) if ok else {},
        # Antworttext bei HTTP-Fehlern, z. B. {"code":404,...,"detail":...}
        "body": data if isinstance(data, str) and data else None,
        "error": error,
    }
    return result, data if ok else None


def _profile_paths(
    character: str, ruleset: str | None, realm_data: dict[str, Any] | None
) -> list[str]:
    name = quote(character.lower())
    paths = []
    if ruleset:
        paths.append(f"/profile/wow/character/{quote(ruleset.lower())}/{name}")
    paths.append(f"/profile/wow/character/{name}")
    realms = (realm_data or {}).get("realms") or []
    slugs = [r["slug"] for r in realms if isinstance(r, dict) and r.get("slug")]
    paths += [f"/profile/wow/character/{slug}/{name}" for slug in slugs[:MAX_REALMS]]
    return paths


async def probe_namespaces(
    client: BattleNetClient,
    regions: list[str],
    character: str | None = None,
    ruleset: str | None = None,
) -> dict[str, Any]:
    """Alle Abfragen nacheinander; Antwort fuer die Aktion."""
    results: list[dict[str, Any]] = []
    for region in regions:
        for suffix in candidates():
            static, _ = await _one(client, region, "static", suffix, STATIC_PATH)
            dynamic, realm_data = await _one(
                client, region, "dynamic", suffix, DYNAMIC_PATH
            )
            results += [static, dynamic]
            if not character:
                continue
            for path in _profile_paths(character, ruleset, realm_data):
                profile, _ = await _one(client, region, "profile", suffix, path)
                results.append(profile)
    counts = Counter(str(r["status"]) for r in results)
    return {
        "candidates": candidates(),
        "requests": len(results),
        "status_counts": dict(sorted(counts.items())),
        "found": [
            f"{r['namespace']} {r['path']}" for r in results if r["status"] == 200
        ],
        "results": results,
    }
