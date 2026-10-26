"""Jeder Fehler- und Abbruch-Schluessel der Dialoge muss uebersetzt sein."""

import json
import re
from pathlib import Path

import pytest

BASE = Path(__file__).parents[1] / "custom_components" / "wow_character"
FILES = ["strings.json", "translations/en.json", "translations/de.json"]
# Von Home Assistant selbst vergebene Abbruchgruende des Hauptdialogs.
BUILTIN_ABORTS = {"already_in_progress"}


def _used_keys(source: str) -> tuple[set[str], set[str]]:
    errors = set(re.findall(r'errors\["base"\] = "(\w+)"', source))
    errors |= set(re.findall(r'return "(\w+)"', source))
    aborts = set(re.findall(r'async_abort\(reason="(\w+)"\)', source))
    if "_abort_if_unique_id_configured" in source:
        aborts.add("already_configured")
    if "async_update_reload_and_abort" in source:
        aborts |= {"reauth_successful", "reconfigure_successful"}
    return errors, aborts


@pytest.mark.parametrize("path", FILES)
def test_flow_keys_translated(path: str) -> None:
    source = (BASE / "config_flow.py").read_text()
    main_src, sub_src = source.split("class CharacterSubentryFlow")
    strings = json.loads((BASE / path).read_text())

    main_errors, main_aborts = _used_keys(main_src)
    sub_errors, sub_aborts = _used_keys(sub_src)
    assert main_errors and sub_errors, "keine Schluessel gefunden"

    main = strings["config"]
    sub = strings["config_subentries"]["character"]
    assert main_errors <= set(main["error"]), (
        f"{path}: {main_errors - set(main['error'])}"
    )
    assert main_aborts - BUILTIN_ABORTS <= set(main["abort"])
    assert sub_errors <= set(sub["error"]), f"{path}: {sub_errors - set(sub['error'])}"
    assert sub_aborts <= set(sub["abort"]), f"{path}: {sub_aborts - set(sub['abort'])}"


def test_entity_keys_translated() -> None:
    from custom_components.wow_character import sensor

    keys = {
        "sensor": {
            d.translation_key for d in (*sensor.PROFILE_SENSORS, *sensor.DETAIL_SENSORS)
        },
        "binary_sensor": {"realm_status", "realm_queue"},
        "event": {"boss_killed", "new_achievement"},
        "image": {"avatar", "full_body"},
    }
    # Ein Sensor je Ausruestungsplatz
    from custom_components.wow_character.const import EQUIPMENT_SLOTS

    keys["sensor"] |= {f"equipment_{slot.lower()}" for slot in EQUIPMENT_SLOTS}
    # Sensoren mit eigener Klasse
    keys["sensor"] |= set(
        re.findall(r'_attr_translation_key = "(\w+)"', (BASE / "sensor.py").read_text())
    )
    assert re.findall(
        r'_attr_translation_key = "(\w+)"', (BASE / "binary_sensor.py").read_text()
    ) == ["realm_status", "realm_queue"]
    for path in FILES:
        entity = json.loads((BASE / path).read_text())["entity"]
        for platform, wanted in keys.items():
            missing = wanted - set(entity.get(platform, {}))
            assert not missing, f"{path} {platform}: {missing}"
        assert "world" in json.loads((BASE / path).read_text())["device"]
