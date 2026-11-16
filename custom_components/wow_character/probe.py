"""Aktion probe_namespaces: Namespaces fuer WoW Forever pruefen (seit 0.34.0).

Blizzard hat den Namespace fuer Forever nicht dokumentiert. Die Aktion fragt
je Region und Kandidat (GAME_VERSIONS["forever"]["namespaces"]) einen
Endpunkt im static- und einen im dynamic-Namespace ab, mit Charakter auch
Profilpfade im profile-Namespace, und meldet je Abfrage HTTP-Status, Schluessel
und wenige Beispielwerte. Liefert ein Profilpfad eine Antwort, folgt sie den
verlinkten Unterseiten (seit 0.34.1). Sie liest nur und aendert keine
Entitaeten.

Live am 16.11.2026 (0.34.0): static-forever-{eu,us,kr,tw} lieferten die
Klassenliste, dynamic-forever-* 404, alle -camelot-Namespaces 403, und das
Profil kam unter /profile/wow/character/{vorname-nachname} ohne Realm.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from .api import BattleNetClient
from .const import GAME_VERSIONS, REGIONS

# Endpunkte ohne Charakter: Klassenliste (static) und Realm-Liste (dynamic).
STATIC_PATH = "/data/wow/playable-class/index"
DYNAMIC_PATH = "/data/wow/realm/index"
# Hoechstens so viele Realms aus einer Realm-Liste als Profilpfad probieren.
MAX_REALMS = 10
# Verlinkte Unterseiten eines gefundenen Profils: hoechstens so viele
# Abfragen und so viele Ebenen (1: Links im Profil, 2: Links darin, z. B.
# collections -> mounts).
MAX_LINKS = 40
MAX_DEPTH = 2
# Hoechstens so viele Schluessel und Listeneintraege je Antwort zeigen; 40
# reicht fuer alle 31 Schluessel des Forever-Profils vom 16.11.2026.
MAX_KEYS = 40
MAX_ITEMS = 3
MAX_TEXT = 80


def candidates() -> list[str]:
    """Namespace-Kandidaten fuer Forever; seit 0.35.0 nur ["-forever"]."""
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
    return await _request(client, region, client.namespace(kind, suffix, region), path)


async def _request(
    client: BattleNetClient,
    region: str,
    namespace: str,
    path: str,
    via: str | None = None,
) -> tuple[dict[str, Any], Any]:
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
    if via is not None:
        # Schluessel, ueber den die Unterseite verlinkt war, z. B.
        # "collections.mounts"
        result["via"] = via
    return result, data if ok else None


def _links(data: dict[str, Any]) -> list[tuple[str, str]]:
    """Schluessel mit reinem Link als Wert, z. B. ("equipment", "https://...")."""
    return [
        (key, value["href"])
        for key, value in data.items()
        if isinstance(value, dict)
        and set(value) == {"href"}
        and isinstance(value["href"], str)
    ]


def _link_target(region: str, href: str, namespace: str) -> tuple[str, str] | None:
    """(Pfad, Namespace) eines Links, nur zum API-Host der Region.

    Jede Abfrage traegt das Token; ein Link zu einem anderen Host wird deshalb
    nie abgefragt, nur gemeldet.
    """
    parts = urlsplit(href)
    if f"{parts.scheme}://{parts.netloc}" != REGIONS[region]["api"]:
        return None
    if not parts.path.startswith(("/profile/", "/data/wow/")):
        return None
    linked = parse_qs(parts.query).get("namespace")
    return parts.path, linked[0] if linked else namespace


async def _follow(
    client: BattleNetClient,
    region: str,
    namespace: str,
    profile: dict[str, Any],
    skipped: list[str],
) -> list[dict[str, Any]]:
    """Verlinkte Unterseiten eines gefundenen Profils, Ebene fuer Ebene."""
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    level = [("", profile)]
    for _depth in range(MAX_DEPTH):
        following = []
        for prefix, data in level:
            for key, href in _links(data):
                via = f"{prefix}{key}"
                target = _link_target(region, href, namespace)
                if target is None:
                    skipped.append(f"{via}: {urlsplit(href).netloc or href[:80]}")
                    continue
                if target in seen or len(results) >= MAX_LINKS:
                    continue
                seen.add(target)
                result, linked = await _request(
                    client, region, target[1], target[0], via
                )
                results.append(result)
                if linked is not None:
                    following.append((f"{via}.", linked))
        level = following
    return results


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
    skipped: list[str] = []
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
                profile, data = await _one(client, region, "profile", suffix, path)
                results.append(profile)
                if data is not None:
                    results += await _follow(
                        client, region, profile["namespace"], data, skipped
                    )
    counts = Counter(str(r["status"]) for r in results)
    return {
        "candidates": candidates(),
        "requests": len(results),
        "status_counts": dict(sorted(counts.items())),
        "found": [
            f"{r['namespace']} {r['path']}" for r in results if r["status"] == 200
        ],
        # Links zu fremden Hosts oder ausserhalb der API, nicht abgefragt
        "skipped_links": skipped,
        "results": results,
    }
