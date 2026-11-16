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


def test_only_glyphs_the_game_font_shows() -> None:
    """Nur Sonderzeichen, die im Spiel nachweislich dargestellt wurden.

    Screenshot vom 11.11.2026 (Forever, deDE): ä, ö, ü, ß und · erscheinen,
    der Pfeil → erschien als Kästchen. Kommentare zählen nicht.
    """
    allowed = set("äöüß·")
    for name in LUA_FILES:
        code = re.sub(r"--[^\n]*", "", (ADDON / name).read_text(encoding="utf-8"))
        unknown = {c for c in code if ord(c) > 127} - allowed
        assert not unknown, f"{name}: {sorted(unknown)}"


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


def _paste(s: Session, text: str, user_input: bool = True) -> None:
    s.lua.eval(
        "function(text, user) local b = EDITBOXES[1]; b.text = text;"
        " b.scripts.OnTextChanged(b, user) end"
    )(text, user_input)


def test_paste_with_line_break() -> None:
    """Zeilenumbruch mitkopiert (im Spiel: 96 statt 94 Zeichen): Das Fenster
    zeigt Länge ohne Rand-Leerraum und zählt CR und LF, ohne den Text zu
    speichern."""
    s = Session("full")
    assert s.lua.eval("HABridgeProbeFrame:IsShown()")  # nach dem Login offen
    _paste(s, SAMPLE + "\r\n")
    paste = s.db.tests.paste
    assert paste.length == 96 and paste.largestJump == 96
    assert paste.matchesSample is False
    assert paste.trimmedLength == 94 and paste.matchesSampleTrimmed is True
    assert paste.firstDiffTrimmed is None
    assert (paste.carriageReturns, paste.lineFeeds) == (1, 1)
    assert (paste.leadingWhitespace, paste.trailingWhitespace) == (0, 2)
    text = s.window()
    assert "96 Zeichen, Prüftext abweichend, größter Sprung 96" in text
    assert "ohne Rand-Leerraum: 94 Zeichen, Prüftext korrekt" in text
    assert "Zeilenumbrüche CR 1, LF 1" in text
    _paste(s, "")
    _paste(s, " HAB1|falsch")
    paste = s.db.tests.paste
    assert paste.largestJump == 12  # neuer Versuch nach dem Leeren
    assert paste.leadingWhitespace == 1 and paste.firstDiffTrimmed == 6
    assert SAMPLE not in s.saved() and "falsch" not in s.saved()


def test_empty_field_is_not_a_paste() -> None:
    """Beim Anzeigen meldet der Client ein leeres Feld (im Spiel gesehen):
    kein Ergebnis und kein Überschreiben eines früheren."""
    s = Session("full")
    assert s.lua.eval("HABridgeProbeFrame:IsShown()")  # nach dem Login offen
    _paste(s, "", user_input=False)
    assert s.db.tests.paste is None
    assert "Einfügen|r  nicht ausgeführt" in s.window()
    _paste(s, SAMPLE)
    _paste(s, "", user_input=False)
    assert s.db.tests.paste.length == 94
    assert s.db.tests.paste.matchesSample is True


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
        "HABridgeProbeMinimapButton",
        "HABridgeProbe_OnCompartmentClick",
        "HABridgeProbe_OnCompartmentEnter",
        "HABridgeProbe_OnCompartmentLeave",
        "SLASH_HABRIDGEPROBE1",
    }


def test_minimap_button() -> None:
    """Eigener Knopf (im Spiel kein Knopf fürs AddOn-Menü sichtbar):
    Kreisbahn um die Minikarte, Klick, Rechtsklick, Ziehen, Ausblenden."""
    s = Session("full")
    button = s.g.HABridgeProbeMinimapButton
    assert s.lua.eval("HABridgeProbeMinimapButton.parent == Minimap")
    # Vorgabe 225 Grad, Radius 140 / 2 + 5 = 75: links unten.
    point = list(button.point.values())
    assert point[0] == "CENTER" and point[2] == "CENTER"
    assert point[3] == pytest.approx(-53.033, abs=0.01)
    assert point[4] == pytest.approx(-53.033, abs=0.01)
    t = s.db.tests.minimap
    assert t.created and t.shown
    click = s.lua.eval("function(b, m) b.scripts.OnClick(b, m) end")
    assert s.lua.eval("HABridgeProbeFrame:IsShown()")
    click(button, "LeftButton")
    assert not s.lua.eval("HABridgeProbeFrame:IsShown()")
    assert t.clicked and t.lastButton == "LeftButton"
    click(button, "RightButton")
    assert s.g.OPENED
    # Ziehen: Cursor genau über der Mitte -> 90 Grad, Knopf oben.
    s.lua.execute(
        "local b = HABridgeProbeMinimapButton; b.scripts.OnDragStart(b);"
        " b.scripts.OnUpdate(b, 0.1); b.scripts.OnDragStop(b)"
    )
    assert s.db.options.minimapAngle == pytest.approx(90)
    assert t.dragged and t.angle == 90 and button.scripts.OnUpdate is None
    point = list(button.point.values())
    assert point[3] == pytest.approx(0, abs=1e-9) and point[4] == pytest.approx(75)
    s.slash("knopf")
    assert not button.shown and s.db.options.showMinimapButton is False
    s.slash("")  # Fenster wieder öffnen
    assert "Minikarten-Knopf|r  angelegt, ausgeblendet" in s.window()
    s.lua.execute("SETTINGCB()")  # Haken "Knopf zeigen" in den Optionen
    assert s.db.tests.settings.changed and s.db.tests.settings.callbackAvailable


def test_minimap_button_without_minimap() -> None:
    """Ohne Minikarte kein Abbruch, nur ein Vermerk."""
    s = Session("minimal")
    assert s.db.tests.minimap.error == "Minimap fehlt"
    assert s.db.runs[1].compartment.exists is False
    s.saved()


def test_logout_snapshot_and_fresh_report() -> None:
    """Werte beim Logout (dort nimmt die Brücke ihren Stand) und Sitzungen im
    Bericht mit dem Stand vom Logout, nicht von der Messung (Fehler in 0.1.1)."""
    first = Session("full")
    assert first.db.report.sessions[1].cleanExit is False
    first.fire("ZONE_CHANGED_NEW_AREA")
    first.fire("PLAYER_LOGOUT")
    session = first.db.report.sessions[1]
    assert session.cleanExit is True and session.loggedOutAt
    assert session.logout.zone == "Steinkrallengebirge"
    assert session.logout.money == 1834520 and session.logout.mapID == 1442
    assert session.zoneAtEvent == "Steinkrallengebirge"
    assert session.guid == "Player-4455-xxxxxxxx"
    second = Session("full", first.saved())
    second.slash("")
    second.slash("")
    text = second.window()
    assert "Beim letzten Logout|r  Steinkrallengebirge / Sonnenfels" in text
    assert "183 g 45 s 20 k" in text


def test_scan_without_widgets_and_new_forever_functions() -> None:
    """Fenster-Elemente zählen nicht als Treffer; die im Spiel gefundenen
    Forever-Funktionen werden aufgerufen und ihre Namensräume aufgelistet."""
    s = Session("full")
    run = s.db.runs[1]
    hits = list(run.scan.values())
    assert "C_PlayerInfo.ShouldDisplaySurname (function)" in hits
    assert "C_GameRules.GetForeverExperiencePreset (function)" in hits
    assert not any(h.startswith("ForeverDungeonJournalTestFrame") for h in hits)
    assert run.scanSkippedWidgets >= 3
    calls = s.calls()
    assert calls["C_PlayerInfo.ShouldDisplaySurname(player)"]["values"][1] is True
    assert calls["C_GameRules.GetForeverExperiencePreset"]["values"][1] == 1
    assert "GetForeverExperiencePreset" in list(run.namespaces.C_GameRules.values())
    assert "GetPlayerSurname" in list(run.namespaces.C_PlayerInfo.values())
    comp = run.compartment
    assert comp.exists and comp.visible is False and comp.registered == 2
    assert comp.parent == "Minimap"
    assert s.db.report.compartment.visible is False


def test_game_mode_read_only() -> None:
    """Spielmodus und Regelsatz: nur lesende Funktionen, nie Set...- oder
    AutoConnect...-Funktionen; Enum.GameMode zum Deuten."""
    s = Session("full")
    calls = s.calls()
    assert calls["C_GameRules.GetActiveGameMode"]["values"][1] == 3
    assert calls["C_GameRules.GetCurrentGameModeRecordID"]["values"][1] == 42
    by_id = calls["C_GameRules.GetGameModeDisplayInfoByRecordID"]
    assert by_id["values"][1].recordID == 42
    assert calls["C_GameRules.IsHardcoreActive"]["values"][1] is False
    assert calls["C_GameRules.IsWoWHack"].available is False  # im Nachbau nicht da
    assert calls["C_PlayerInfo.IsSelfFoundActive"]["values"][1] is False
    assert s.db.runs[1].enums.GameMode.Forever == 3
    assert s.g.SET_CALLED is None
    text = s.window()
    assert "Spielmodus|r  aktiv 3 · Record 42 · Standard false · Hardcore false" in text
    assert "Voreinstellung|r  1 (Erweitert)" in text


def test_timing_with_gettime() -> None:
    """Abstände über GetTime (Sekunden mit Nachkommastellen) statt über die
    Serverzeit, die kurz nach dem Login springt."""
    s = Session("full")  # Betreten der Welt und Messung bei GetTime 1000
    assert s.db.session.enteredWorldClock == 1000
    assert s.db.runs[1].secondsAfterEnteringWorld == 0
    s.g.TIMEF = 1004.24
    s.fire("ZONE_CHANGED_NEW_AREA")
    assert s.db.session.zoneReadySeconds == pytest.approx(4.2)
    s.ns.measure("button")
    assert s.db.runs[1].secondsAfterEnteringWorld == pytest.approx(4.2)
    assert (
        "Zone bekannt|r  4.2 s nach dem Betreten der Welt (Steinkrallengebirge)"
        in s.window()
    )


def test_live_state_survives_logout_zeros() -> None:
    """Laufender Stand aus Ereignissen; beim Logout liefert der Client im
    Spiel Gold und Erfahrung als 0, der laufende Stand bleibt richtig."""
    s = Session("full")
    s.lua.execute("GetMoney = function() return 99999 end")
    s.fire("PLAYER_MONEY")
    live = s.db.session.live
    assert live.money == 99999 and live.reason == "PLAYER_MONEY"
    # Leere Zone und fehlende Karte überschreiben nichts.
    s.lua.execute(
        "GetRealZoneText = function() return '' end;"
        " C_Map.GetBestMapForUnit = function() return nil end"
    )
    s.fire("ZONE_CHANGED")
    assert live.zone == "Steinkrallengebirge" and live.mapID == 1442
    # Logout wie im Spiel: Gold, Erfahrung und Karte weg.
    s.lua.execute(
        "GetMoney = function() return 0 end; UnitXP = function() return 0 end;"
        " GetRealZoneText = function() return 'Steinkrallengebirge' end"
    )
    s.fire("PLAYER_LOGOUT")
    session = s.db.report.sessions[1]
    assert session.logout.money == 0 and session.logout.xp == 0
    assert session.live.money == 99999 and session.live.xp == 21480
    second = Session("full", s.saved())
    second.slash("")
    second.slash("")
    text = second.window()
    logout_line = "Steinkrallengebirge / Sonnenfels · Karte <nil> · 0 g 0 s 0 k · EP 0"
    assert "Beim letzten Logout|r  " + logout_line in text
    assert (
        "Laufender Stand davor|r  Steinkrallengebirge / Sonnenfels · Karte 1442 · 9 g 99 s 99 k · EP 21480"
        in text
    )


def test_paste_unescaped_and_compartment_position() -> None:
    """Prüfzeile mit maskierten Strichen (im Spiel: 96 Zeichen): ohne
    Maskierung korrekt. Lage des AddOn-Menü-Knopfs wird gemessen."""
    s = Session("full")
    _paste(s, SAMPLE.replace("|", "||"))
    paste = s.db.tests.paste
    assert paste.length == 96 and paste.firstDiffTrimmed == 6
    assert paste.doubledPipes == 2 and paste.matchesSampleUnescaped is True
    assert "doppelte Striche: 2 · ohne Maskierung: Prüftext korrekt" in s.window()
    _paste(s, "")
    _paste(s, SAMPLE)
    assert s.db.tests.paste.doubledPipes == 0
    comp = s.db.runs[1].compartment
    assert list(comp.point.values()) == ["TOPRIGHT", "UIParent", "TOPRIGHT", -10, -5]
    assert list(comp.rect.values()) == [1890, 1050, 20, 20]
    assert comp.strata == "MEDIUM" and list(comp.screen.values()) == [1920, 1080]
    assert "Lage: TOPRIGHT an UIParent/TOPRIGHT" in s.window()
