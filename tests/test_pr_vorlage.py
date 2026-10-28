"""Tests fuer die Pruefung der PR-Vorlage (.github/scripts/pruefe_pr.py)."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
_spec = importlib.util.spec_from_file_location(
    "pruefe_pr", ROOT / ".github" / "scripts" / "pruefe_pr.py"
)
pruefe_pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pruefe_pr)

TEMPLATE = (ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")


def _filled(**replace: str) -> str:
    """Vorlage, vollstaendig ausgefuellt; replace ersetzt Textstellen."""
    body = (
        TEMPLATE.replace(
            "## Zusammenfassung\n", "## Zusammenfassung\n\nNeuer Sensor.\n"
        )
        .replace(
            "## Belege\n",
            "## Belege\n\n- https://community.developer.battle.net/documentation\n",
        )
        .replace("## Änderungen\n", "## Änderungen\n\n- `sensor.py`: neuer Sensor\n")
        .replace(
            "## Verhaltensänderungen\n",
            "## Verhaltensänderungen\n\n- Retail: neuer Sensor, sonst nichts\n",
        )
        .replace("- Automatische Tests:", "- Automatische Tests: 102, davon 8 neu")
        .replace("- Gegenprobe:", "- Gegenprobe: 6 entfernt, alle erkannt")
        .replace("- Live geprüft:", "- Live geprüft: nein (kein Jäger vorhanden)")
        .replace(
            "## Nicht geprüft / offen\n",
            "## Nicht geprüft / offen\n\n- Feldnamen nicht live bestätigt\n",
        )
        .replace("- [ ] ", "- [x] ")
    )
    for old, new in replace.items():
        assert old in body, old
        body = body.replace(old, new)
    return body


def test_filled_template_passes() -> None:
    assert pruefe_pr.pruefe_beschreibung(_filled()) == []


@pytest.mark.parametrize("body", [None, "", "Kurze Beschreibung ohne Vorlage"])
def test_missing_description_fails(body) -> None:
    errors = pruefe_pr.pruefe_beschreibung(body)
    assert "Abschnitt „Belege“ fehlt" in errors
    assert "Abschnitt „Checkliste“ fehlt" in errors


def test_missing_checklist_reported_once() -> None:
    body = _filled().split("## Checkliste")[0]
    assert pruefe_pr.pruefe_beschreibung(body) == ["Abschnitt „Checkliste“ fehlt"]


def test_removed_test_field_fails() -> None:
    """Freitext statt der Felder: "Live geprüft" darf nicht wegfallen."""
    body = _filled(
        **{"- Live geprüft: nein (kein Jäger vorhanden)\n": "- Alles getestet\n"}
    )
    assert pruefe_pr.pruefe_beschreibung(body) == ["„Tests“: Feld „Live geprüft“ fehlt"]


def test_unfilled_template_fails() -> None:
    errors = pruefe_pr.pruefe_beschreibung(TEMPLATE)
    assert "Abschnitt „Zusammenfassung“ ist leer" in errors
    assert "„Tests“: Feld „Live geprüft“ ist leer" in errors
    assert any(e.startswith("Checkliste: offen:") for e in errors)


def test_open_checkbox_fails() -> None:
    body = _filled(**{"- [x] `ruff check .`": "- [ ] `ruff check .`"})
    assert pruefe_pr.pruefe_beschreibung(body) == [
        "Checkliste: offen: `ruff check .` und `ruff format --check .` ohne Befund"
    ]


def test_not_applicable_needs_reason() -> None:
    item = "- [x] Lange Listen in `_unrecorded_attributes` und in der Diagnose gekürzt"
    ok = _filled(**{item: f"{item} – entfällt: keine Listen-Attribute"})
    assert pruefe_pr.pruefe_beschreibung(ok) == []
    bad = _filled(**{item: f"{item} – entfällt"})
    assert len(pruefe_pr.pruefe_beschreibung(bad)) == 1


def test_removed_checklist_item_fails() -> None:
    item = (
        "- [x] Keine Client-ID, kein Secret und keine echten Charakterdaten im Diff\n"
    )
    errors = pruefe_pr.pruefe_beschreibung(_filled(**{item: ""}))
    assert errors == [
        (
            "Checkliste: Punkt fehlt: Keine Client-ID, kein Secret und keine "
            "echten Charakterdaten im Diff"
        )
    ]


@pytest.mark.parametrize(
    "live", ["vielleicht", "ja", "nein ()", "nein, kein Jäger", "teilweise (EU)"]
)
def test_live_check_needs_yes_or_no_with_reason(live: str) -> None:
    body = _filled(
        **{"- Live geprüft: nein (kein Jäger vorhanden)": f"- Live geprüft: {live}"}
    )
    assert pruefe_pr.pruefe_beschreibung(body) == [
        "„Tests“: Live geprüft muss „ja (…)“ oder „nein (Grund)“ sein"
    ]


def test_test_count_needs_number() -> None:
    body = _filled(**{"102, davon 8 neu": "alle grün"})
    assert pruefe_pr.pruefe_beschreibung(body) == [
        "„Tests“: Automatische Tests ohne Anzahl"
    ]


def test_sources_need_link_or_reason() -> None:
    link = "- https://community.developer.battle.net/documentation\n"
    assert pruefe_pr.pruefe_beschreibung(_filled(**{link: "- siehe Doku\n"})) == [
        "„Belege“: mindestens ein Link oder „Keine: <Grund>“"
    ]
    reason = _filled(**{link: "Keine: nur README geändert\n"})
    assert pruefe_pr.pruefe_beschreibung(reason) == []


def test_comment_only_section_counts_as_empty() -> None:
    body = _filled(**{"Neuer Sensor.\n": "<!-- spaeter -->\n"})
    assert pruefe_pr.pruefe_beschreibung(body) == [
        "Abschnitt „Zusammenfassung“ ist leer"
    ]


SENSOR = ["custom_components/wow_character/sensor.py"]


@pytest.mark.parametrize(
    ("files", "old", "new", "notes", "expected"),
    [
        # Nur Doku oder Workflows: keine neue Version noetig
        (["README.md", ".github/workflows/x.yml"], "0.10.0", "0.10.0", set(), []),
        (
            SENSOR,
            "0.10.0",
            "0.10.0",
            {"v0.10.0.md"},
            ["Integration geändert, aber Version in manifest.json bleibt 0.10.0"],
        ),
        (SENSOR, "0.10.0", "0.11.0", set(), [".github/release-notes/v0.11.0.md fehlt"]),
        (SENSOR, "0.10.0", "0.11.0", {"v0.11.0.md"}, []),
    ],
)
def test_version_rule(files, old, new, notes, expected) -> None:
    assert pruefe_pr.pruefe_version(files, old, new, notes) == expected
