"""Jeder Fehler-Schluessel aus dem Einrichtungsdialog muss uebersetzt sein."""

import json
import re
from pathlib import Path

import pytest

BASE = Path(__file__).parents[1] / "custom_components" / "wow_character"


@pytest.mark.parametrize(
    "path", ["strings.json", "translations/en.json", "translations/de.json"]
)
def test_flow_errors_translated(path: str) -> None:
    used = set(
        re.findall(r'errors\["base"\] = "(\w+)"', (BASE / "config_flow.py").read_text())
    )
    assert used, "keine Fehler-Schluessel gefunden"
    known = set(json.loads((BASE / path).read_text())["config"]["error"])
    assert used <= known, f"fehlt in {path}: {used - known}"
