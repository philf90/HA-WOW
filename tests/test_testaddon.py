"""Test-Addon fuer WoW Forever (addon/HABridgeProbe).

Statische Pruefungen der TOC und der Lua-Dateien, dazu ein Durchlauf unter
Lua 5.1 (wie im WoW-Client) gegen einen Nachbau der WoW-API
(tests/wow_api_stub.lua). Der Nachbau ersetzt keinen Test im echten Client; er
zeigt, dass das Addon ohne Lua-Fehler laeuft, fehlende Funktionen und geheime
Werte uebersteht und eine speicherbare Datei hinterlaesst.
"""

import re
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")
from lupa import lua51

ROOT = Path(__file__).parents[1]
ADDON = ROOT / "addon" / "HABridgeProbe"
TOC = (ADDON / "HABridgeProbe.toc").read_text(encoding="utf-8")
STUB = (Path(__file__).parent / "wow_api_stub.lua").read_text(encoding="utf-8")
LUA_FILES = ("Probe.lua", "UI.lua")
SAMPLE = "HAB1|http://192.168.0.10:8123|" + "0123456789abcdef" * 4


def _toc(field: str) -> str:
    match = re.search(rf"^## {field}: (.+)$", TOC, re.MULTILINE)
    assert match, f"TOC ohne {field}"
    return match.group(1).strip()


def test_toc_metadata() -> None:
    """Forever-Interface, SavedVariables und Version wie im Code."""
    interfaces = [v.strip() for v in _toc("Interface").split(",")]
    assert "16001" in interfaces
    assert _toc("SavedVariables") == "HABridgeProbeDB"
    probe = (ADDON / "Probe.lua").read_text(encoding="utf-8")
    assert f'ns.VERSION = "{_toc("Version")}"' in probe


def test_toc_lists_all_lua_files() -> None:
    """Ordner und TOC heissen gleich; jede Lua-Datei steht in der TOC."""
    assert ADDON.name == "HABridgeProbe"
    listed = [
        line.strip()
        for line in TOC.splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert listed == list(LUA_FILES)
    assert sorted(p.name for p in ADDON.glob("*.lua")) == sorted(LUA_FILES)


def test_compartment_functions_defined() -> None:
    ui = (ADDON / "UI.lua").read_text(encoding="utf-8")
    for field in (
        "AddonCompartmentFunc",
        "AddonCompartmentFuncOnEnter",
        "AddonCompartmentFuncOnLeave",
    ):
        assert f"function {_toc(field)}(" in ui, field


def test_no_libraries_missing_in_wow() -> None:
    """WoW-Lua hat keine Datei- und Betriebssystem-Bibliotheken."""
    for name in LUA_FILES:
        code = (ADDON / name).read_text(encoding="utf-8")
        code = re.sub(r"--[^\n]*", "", code)
        for forbidden in (r"\bio\.", r"\bos\.", r"\b(require|loadstring|dofile)\("):
            assert not re.search(forbidden, code), f"{name}: {forbidden}"


def test_paste_sample_in_readme() -> None:
    """Die Pruefzeile im README ist die, die das Addon erwartet."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert SAMPLE in readme
    assert len(SAMPLE) == 94


# ---------------------------------------------------------------------------
# Durchlauf unter Lua 5.1
# ---------------------------------------------------------------------------


class Session:
    """Eine Spielsitzung: Laden, Einloggen, Messung, Spielzeit."""

    def __init__(self, mode: str, saved: str | None = None) -> None:
        self.lua = lua51.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.g.MODE = mode
        self.lua.execute(STUB)
        if saved:
            self.lua.execute("HABridgeProbeDB = " + saved)
            self.lua.execute("CLOCK = CLOCK + 100")
        self.lua.execute(
            "NEWG = {} setmetatable(_G, {__newindex = function(t, k, v)"
            " NEWG[#NEWG + 1] = tostring(k) rawset(t, k, v) end})"
        )
        self.ns = self.lua.table()
        compile_ = self.lua.eval(
            "function(src, name) local f, e = loadstring(src, name)"
            " if not f then error(e) end return f end"
        )
        for name in LUA_FILES:
            compile_((ADDON / name).read_text(encoding="utf-8"), name)(
                "HABridgeProbe", self.ns
            )
        self._fire = self.lua.eval(
            "function(ns, ...) ns.frame.scripts.OnEvent(ns.frame, ...) end"
        )
        self.fire("ADDON_LOADED", "HABridgeProbe")
        self.fire("PLAYER_ENTERING_WORLD", True, False)
        # Ohne C_Timer wartet das Addon ueber OnUpdate.
        self.lua.execute(
            "for _, f in ipairs(FRAMES) do"
            " if f.scripts.OnUpdate then f.scripts.OnUpdate(f, 10) end end"
            " RunTimers()"
        )
        self.fire("TIME_PLAYED_MSG", 312840, 9000)

    def fire(self, *args) -> None:
        self._fire(self.ns, *args)

    def slash(self, msg: str) -> None:
        self.g.SlashCmdList.HABRIDGEPROBE(msg)

    @property
    def db(self):
        return self.g.HABridgeProbeDB

    def calls(self, section: str = "run") -> dict:
        table = self.db.runs[1] if section == "run" else self.db.report
        return {e.label: e for e in table["calls"].values()}

    def saved(self) -> str:
        """Die Tabelle so, wie der Client sie schreibt; Fehler bei Funktionen."""
        return self.lua.eval("Serialize(HABridgeProbeDB)")

    def window(self) -> str:
        return self.lua.eval("_G.HABridgeProbeFrame.summary.text")


def test_measurement_and_report() -> None:
    """Werte gemessen, Bericht ohne Namen, keine Koordinaten gespeichert."""
    s = Session("full")
    run = s.db.runs[1]
    assert run.error is None
    calls = s.calls()
    assert calls["GetMoney"]["values"][1] == 1834520
    assert calls["UnitFullName"]["values"][1] == "Mara Sturmwind"
    assert calls["UnitFullName"]["values"][2] == "Normal"
    assert calls["C_Map.GetPlayerMapPosition"]["values"][1] == "<Wert vorhanden>"
    assert calls["GetInventoryItemDurability (1-19)"].min == pytest.approx(0.62)
    assert calls["C_CurrencyInfo.GetCurrencyListInfo(2)"].currencyID == 3001
    assert run.played.total == 312840
    assert run.json.ok and run.json.roundtrip
    assert dict(run.projects.items())["WOW_PROJECT_FOREVER"] == 19
    assert "PlayerInfo.GetSurname" in list(run.documentation["hits"].values())
    report = s.calls("report")
    assert report["UnitFullName"]["values"][1] == "Aaaa Aaaaaaaaa"
    assert report["UnitFullName"]["values"][2] == "Normal"
    assert report["UnitGUID"]["values"][1] == "Player-4455-xxxxxxxx"
    assert report["GetGuildInfo"]["values"][1] == "Aaa Aaaaaaaa"
    assert report["GetGuildInfo"]["values"][2] == "Aaaaaaaa"
    saved = s.saved()
    shared = saved.split('["report"]')[1].split('["runs"]')[0]
    for private in ("Mara Sturmwind", "Die Wanderer", "0A1B2C3D"):
        assert private not in shared, private
    assert '["x"]' not in saved  # Koordinaten aus dem Nachbau


def test_tests_in_the_window() -> None:
    """Einfuegen, Chat-Log, AddOn-Menue, Einstellungsseite, Fenstertext."""
    s = Session("full")
    s.slash("")
    s.lua.eval(
        "function(text) local b = EDITBOXES[1]; b.text = text;"
        " b.scripts.OnTextChanged(b, true) end"
    )(SAMPLE)
    paste = s.db.tests.paste
    assert paste.matchesSample and paste.length == 94 and paste.largestJump == 94
    assert SAMPLE not in s.saved()  # der eingefuegte Text wird nicht gespeichert
    s.slash("chatlog")
    assert s.db.tests.chatlog.priorState is False
    assert s.db.tests.chatlog.stateAfter is True
    assert any("HABP-" in str(line) for line in s.g.OUT.values())
    s.lua.execute(
        "HABridgeProbe_OnCompartmentEnter('HABridgeProbe', UIParent)"
        " HABridgeProbe_OnCompartmentClick('HABridgeProbe', 'LeftButton')"
    )
    assert s.db.tests.compartment.clicked
    assert s.db.tests.settings.ok
    s.lua.execute("SETTINGCB()")
    assert s.db.tests.settings.changed
    s.slash("optionen")
    assert s.g.OPENED
    text = s.window()
    assert '"Mara Sturmwind" + "Normal"' in text
    assert "94 Zeichen, Prüftext korrekt" in text
    assert "183 g 45 s 20 k" in text


def test_reload_and_crash_detection() -> None:
    """/reload wird in der naechsten Sitzung bestaetigt; ohne Logout
    geschriebene Datei faellt als nicht sauber beendet auf."""
    first = Session("full")
    first.slash("reload")
    assert first.g.RELOADED
    first.fire("PLAYER_LOGOUT")
    second = Session("full", first.saved())
    assert second.db.session.id == 2
    assert second.db.tests.reload.ok
    assert second.db.sessions[2].cleanExit is True
    second.slash("")
    assert "bestätigt (Logout 0 s nach Klick)" in second.window()
    # Datei ohne PLAYER_LOGOUT (Absturz, falls der Client dann schreibt).
    third = Session("full", second.saved())
    assert third.db.sessions[2].cleanExit is False
    third.slash("")
    assert "zuletzt gespeichert: #2 (sauber beendet: nein)" in third.window()


def test_missing_functions_and_templates() -> None:
    """Fehlt etwas im Client, wird es festgehalten statt abzubrechen."""
    s = Session("minimal")
    assert s.db.runs[1].error is None
    calls = s.calls()
    assert calls["GetMoney"].ok is False and "boom" in calls["GetMoney"].error
    assert calls["GetCurrentRegion"].available is False
    assert s.db.tests.settings.ok is False
    assert s.db.runs[1].json.available is False
    assert s.db.eventSupport["ADDON_RESTRICTION_STATE_CHANGED"] is not True
    s.slash("")
    assert "fehlt: GetCurrentRegion" in s.window()
    s.saved()


def test_secret_values_and_combat() -> None:
    """Geheime Werte werden markiert; im Kampf wird nicht gemessen."""
    s = Session("secret")
    guid = s.calls()["UnitGUID"]
    assert guid["values"][1] == "<secret>" and guid.secret
    s.saved()
    s.lua.execute("InCombatLockdown = function() return true end")
    s.ns.measure("kampf")
    assert s.ns.pendingMeasure == "kampf"
    s.lua.execute("InCombatLockdown = function() return false end")
    s.fire("PLAYER_REGEN_ENABLED")
    assert s.db.runs[1].trigger == "kampf"


def test_no_stray_globals() -> None:
    """Alle Addons teilen sich _G; das Addon legt nur seine eigenen Namen an."""
    s = Session("full")
    s.slash("chatlog")
    names = set(s.lua.eval("NEWG").values())
    names -= {"APIDocumentation", "CHATLOG", "SETTINGCB"}  # aus dem Nachbau
    assert names == {
        "HABridgeProbeDB",
        "HABridgeProbeFrame",
        "HABridgeProbe_OnCompartmentClick",
        "HABridgeProbe_OnCompartmentEnter",
        "HABridgeProbe_OnCompartmentLeave",
        "SLASH_HABRIDGEPROBE1",
    }
