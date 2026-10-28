"""Prueft einen Pull Request gegen die Pflichtvorlage.

1. Beschreibung: alle Abschnitte der Vorlage, keiner leer, Felder ausgefuellt,
   jedes Kaestchen angekreuzt (oder mit "entfällt: <Grund>").
2. Version: Aendert der PR die Integration, muss manifest.json eine neue
   Version nennen und es Versionshinweise dazu geben.

Im Workflow: PR_BODY und BASE_SHA kommen als Umgebungsvariablen, nie als Text
im Skript, damit eine Beschreibung keinen Shell-Code einschleusen kann.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
MANIFEST = "custom_components/wow_character/manifest.json"
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_BOX = re.compile(r"^- \[( |x|X)\] (.+?)\s*$", re.MULTILINE)
_FIELD = re.compile(r"^- ([^\[\]:\n]+):[ \t]*(.*)$", re.MULTILINE)


def _sections(text: str) -> dict[str, str]:
    text = _COMMENT.sub("", text.replace("\r\n", "\n"))
    parts = _HEADING.split(text)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts), 2)}


def _template() -> dict[str, str]:
    return _sections(TEMPLATE.read_text(encoding="utf-8"))


def pruefe_beschreibung(
    body: str | None, template: dict[str, str] | None = None
) -> list[str]:
    """Fehler in der Beschreibung; leere Liste, wenn alles passt."""
    template = template if template is not None else _template()
    have = _sections(body or "")
    errors = [f"Abschnitt „{name}“ fehlt" for name in template if name not in have]
    for name, text in have.items():
        if name not in template:
            continue
        if not text:
            errors.append(f"Abschnitt „{name}“ ist leer")
        fields = {label.strip(): value for label, value in _FIELD.findall(text)}
        for label, value in fields.items():
            if not value.strip():
                errors.append(f"„{name}“: Feld „{label}“ ist leer")
        # Felder der Vorlage (z. B. "Live geprüft:") duerfen nicht fehlen.
        for label, _value in _FIELD.findall(template[name]):
            if label.strip() not in fields:
                errors.append(f"„{name}“: Feld „{label.strip()}“ fehlt")
    errors += _pruefe_belege(have.get("Belege", ""))
    errors += _pruefe_tests(have.get("Tests", ""))
    # Fehlt die Checkliste ganz, reicht die Meldung oben.
    if "Checkliste" in have:
        errors += _pruefe_checkliste(have["Checkliste"], template["Checkliste"])
    return errors


def _pruefe_belege(text: str) -> list[str]:
    if (
        not text
        or re.search(r"https?://", text)
        # "Keine: <Grund>" am Zeilenanfang, auch als Listenpunkt "- Keine: ..."
        or re.search(r"^(?:[-*] )?Keine: \S.{2,}", text, re.MULTILINE)
    ):
        return []
    return ["„Belege“: mindestens ein Link oder „Keine: <Grund>“"]


def _pruefe_tests(text: str) -> list[str]:
    fields = {label.strip(): value.strip() for label, value in _FIELD.findall(text)}
    errors = []
    if (count := fields.get("Automatische Tests")) and not re.search(r"\d", count):
        errors.append("„Tests“: Automatische Tests ohne Anzahl")
    live = fields.get("Live geprüft")
    if live and not re.fullmatch(r"(ja|nein) \(.{3,}\)", live):
        errors.append("„Tests“: Live geprüft muss „ja (…)“ oder „nein (Grund)“ sein")
    return errors


def _pruefe_checkliste(text: str, template: str) -> list[str]:
    boxes = {item: mark for mark, item in _BOX.findall(text)}
    errors = []
    for _mark, item in _BOX.findall(template):
        found = next((b for b in boxes if b.startswith(item)), None)
        if found is None:
            errors.append(f"Checkliste: Punkt fehlt: {item}")
        elif boxes[found] == " ":
            errors.append(f"Checkliste: offen: {item}")
        elif "entfällt" in found and not re.search(r"entfällt: \S.{2,}", found):
            errors.append(f"Checkliste: „entfällt“ ohne Grund: {item}")
    return errors


def pruefe_version(
    geaendert: list[str], alte: str | None, neue: str | None, hinweise: set[str]
) -> list[str]:
    """Aendert der PR die Integration, braucht er eine neue Version mit Hinweisen."""
    if not any(f.startswith("custom_components/") for f in geaendert):
        return []
    if neue is None or neue == alte:
        return [f"Integration geändert, aber Version in manifest.json bleibt {alte}"]
    if f"v{neue}.md" not in hinweise:
        return [f".github/release-notes/v{neue}.md fehlt"]
    return []


def _version(ref: str | None) -> str | None:
    if ref is None:
        text = (ROOT / MANIFEST).read_text(encoding="utf-8")
    else:
        text = subprocess.run(
            ["git", "show", f"{ref}:{MANIFEST}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    return json.loads(text)["version"]


def main() -> int:
    errors = pruefe_beschreibung(os.environ.get("PR_BODY"))
    if base := os.environ.get("BASE_SHA"):
        geaendert = subprocess.run(
            ["git", "diff", "--name-only", base, "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        hinweise = {p.name for p in (ROOT / ".github" / "release-notes").glob("v*.md")}
        errors += pruefe_version(geaendert, _version(base), _version(None), hinweise)
    for error in errors:
        print(f"::error::{error}")
    if not errors:
        print("PR erfüllt die Vorlage.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
