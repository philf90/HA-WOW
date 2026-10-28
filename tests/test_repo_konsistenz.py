"""Konsistenz von Version, Doku, Uebersetzungen und Endpunkt-Verdrahtung.

Diese Regeln standen bisher nur in der Gewohnheit; jede Abweichung faellt hier
auf, bevor ein Release entsteht.
"""

import json
import re
from pathlib import Path

import pytest

from custom_components.wow_character import const, coordinator

ROOT = Path(__file__).parents[1]
BASE = ROOT / "custom_components" / "wow_character"
README = (ROOT / "README.md").read_text(encoding="utf-8")
VERSION = json.loads((BASE / "manifest.json").read_text())["version"]
MINOR = ".".join(VERSION.split(".")[:2])


def test_version_in_readme_and_release_notes() -> None:
    assert f"Version {VERSION}." in README, "README nennt die Version nicht"
    notes = ROOT / ".github" / "release-notes" / f"v{VERSION}.md"
    assert notes.is_file(), f"{notes.name} fehlt"
    text = notes.read_text(encoding="utf-8")
    assert "## Neu" in text or "## Behoben" in text or "## Geändert" in text
    assert "## Teststand" in text, f"{notes.name}: Abschnitt Teststand fehlt"


def test_readme_test_count_matches(request: pytest.FixtureRequest) -> None:
    """Die Zahl im Teststand muss stimmen; nur beim vollen Lauf pruefbar."""
    items = request.session.items
    if len({Path(str(i.fspath)).name for i in items}) < len(
        list((ROOT / "tests").glob("test_*.py"))
    ):
        pytest.skip("nur beim Lauf aller Testdateien")
    match = re.search(
        rf"\*\*{re.escape(MINOR)}\.x:\*\* (\d+) automatische Tests", README
    )
    assert match, f"Teststand fuer {MINOR}.x fehlt im README"
    assert int(match.group(1)) == len(items), (
        f"README nennt {match.group(1)} Tests, gesammelt sind {len(items)}"
    )


def _flatten(data, prefix=""):
    if isinstance(data, dict):
        for key, value in data.items():
            yield from _flatten(value, f"{prefix}{key}.")
    else:
        yield prefix.rstrip("."), data


def test_translation_files_match() -> None:
    """strings.json = en.json; de.json hat dieselben Schluessel und Platzhalter."""
    strings = json.loads((BASE / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((BASE / "translations/en.json").read_text(encoding="utf-8"))
    de = dict(_flatten(json.loads((BASE / "translations/de.json").read_text())))
    assert strings == en, "strings.json und en.json weichen ab"
    en_flat = dict(_flatten(en))
    assert set(en_flat) == set(de), set(en_flat) ^ set(de)
    for key, text in en_flat.items():
        wanted = set(re.findall(r"\{(\w+)\}", text))
        assert wanted == set(re.findall(r"\{(\w+)\}", de[key])), key


def test_game_versions_complete() -> None:
    fields = {"namespaces", "mythic_plus", "label", "endpoints", "static"}
    suffixes = []
    for name, version in const.GAME_VERSIONS.items():
        assert set(version) == fields, name
        suffixes += version["namespaces"]
        for path in ("strings.json", "translations/en.json", "translations/de.json"):
            options = json.loads((BASE / path).read_text(encoding="utf-8"))["selector"][
                "game_version"
            ]["options"]
            assert name in options, f"{path}: {name}"
    assert len(suffixes) == len(set(suffixes)), "Namespace doppelt vergeben"


def test_endpoint_wiring() -> None:
    """Jeder Endpunkt hat eine Entitaet, jede Entitaet einen Endpunkt."""
    endpoints = set(const.DETAIL_ENDPOINTS)
    used = set(coordinator.DETAIL_KEYS.values())
    used |= {e for extra in coordinator.EXTRA_ENDPOINTS.values() for e in extra}
    used |= {
        coordinator.endpoint_for_key(f"{coordinator.PROFESSION_PREFIX}1"),
        coordinator.endpoint_for_key(f"{coordinator.EQUIPMENT_PREFIX}head"),
        coordinator.endpoint_for_key(f"{coordinator.PVP_BRACKET_PREFIX}3v3"),
    }
    assert used <= endpoints, used - endpoints
    assert endpoints <= used, f"abgefragt, aber ohne Entitaet: {endpoints - used}"
    for version in const.GAME_VERSIONS.values():
        assert set(version["endpoints"] or ()) <= endpoints


def test_every_endpoint_documented_and_mocked() -> None:
    """Neuer Endpunkt: im README genannt und in den Test-Antworten nachgebaut."""
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    for resource, _minutes in const.DETAIL_ENDPOINTS.values():
        if "{" in resource:
            continue
        assert f"`{resource}`" in README or f"`{resource.split('/')[0]}" in README, (
            f"README nennt {resource} nicht"
        )
        assert f'"/{resource}"' in conftest, f"conftest baut {resource} nicht nach"


def test_unrecorded_attributes_documented() -> None:
    """Was nicht in die Datenbank geht, steht im README-Abschnitt dazu."""
    section = README.split("### Nicht in der Datenbank", 1)[1].split("\n## ", 1)[0]
    names = set()
    for path in BASE.glob("*.py"):
        # frozenset({...}), auch ueber mehrere Zeilen, oder Erweiterung einer
        # Elternklasse: ... | {...}
        for group in re.findall(
            r"_unrecorded_attributes = (?:frozenset\(\s*|\S+ \| )\{([^}]*)\}",
            path.read_text(),
        ):
            names |= set(re.findall(r'"(\w+)"', group))
    assert names, "keine _unrecorded_attributes gefunden"
    missing = {n for n in names if f"`{n}`" not in section}
    assert not missing, f"README nennt nicht: {missing}"
