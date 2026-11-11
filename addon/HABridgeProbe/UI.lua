-- HA Bridge Probe: Fenster, Tests zum Anklicken, Einstellungsseite, AddOn-Menue
-- und Slash-Befehle (/habp).

local ADDON, ns = ...

local function now()
  if type(GetServerTime) == "function" then
    return GetServerTime()
  end
  return time()
end

local function tests()
  return HABridgeProbeDB.tests
end

-- Frame mit Vorlage; fehlt die Vorlage im Client, ohne Vorlage.
local function make(kind, name, parent, template)
  if template then
    local ok, frame = pcall(CreateFrame, kind, name, parent, template)
    if ok and frame then
      return frame, true
    end
  end
  return CreateFrame(kind, name, parent), false
end

local function background(frame, alpha)
  local tex = frame:CreateTexture(nil, "BACKGROUND")
  tex:SetAllPoints()
  tex:SetColorTexture(0, 0, 0, alpha)
  return tex
end

local function find(run, label)
  for _, e in ipairs(run.calls) do
    if e.label == label then
      return e
    end
  end
end

local function val(run, label, index)
  local e = run and find(run, label)
  if not e then
    return nil
  end
  if not e.available then
    return "fehlt"
  end
  if e.ok == false then
    return "Fehler"
  end
  local v = e.values and e.values[index or 1]
  if v == "<nil>" then
    return nil
  end
  return v
end

local function money(copper)
  if type(copper) ~= "number" then
    return tostring(copper or "?")
  end
  return string.format("%d g %d s %d k", math.floor(copper / 10000), math.floor(copper % 10000 / 100), copper % 100)
end

local function yesno(v)
  return v and "ja" or "nein"
end

local function text(v)
  if v == nil then
    return "-"
  end
  return tostring(v)
end

-- ---------------------------------------------------------------------------
-- Tests zum Anklicken
-- ---------------------------------------------------------------------------

function ns.reloadTest()
  tests().reload = { requestedAt = now() }
  ns.print("Speichere mit /reload ...")
  local ok, err = pcall(ReloadUI)
  if not ok then
    tests().reload.error = tostring(err)
    ns.print("ReloadUI fehlgeschlagen: " .. tostring(err))
  end
end

function ns.chatlogTest()
  local t = { at = now(), token = "HABP-" .. now() }
  local lc = ns.resolve("LoggingChat")
  t.available = type(lc) == "function"
  -- Ergebnis eines pcall: Wert (auch false) oder Fehlertext.
  local function result(ok, v)
    if ok then
      return ns.safe(v)
    end
    return "Fehler: " .. tostring(v)
  end
  if t.available then
    t.priorState = result(pcall(lc))
    local ok, res = pcall(lc, true)
    t.enableOk = ok
    t.enableResult = result(ok, res)
    t.stateAfter = result(pcall(lc))
  end
  tests().chatlog = t
  ns.print("Chat-Log-Marke " .. t.token .. " (print)")
  if DEFAULT_CHAT_FRAME then
    pcall(DEFAULT_CHAT_FRAME.AddMessage, DEFAULT_CHAT_FRAME, "HA Bridge Probe Chat-Log-Marke " .. t.token .. " (AddMessage)")
  end
  ns.print("Jetzt in Logs\\WoWChatLog.txt nach " .. t.token .. " suchen, vor und nach dem Ausloggen. Abschalten: /habp chatlog aus")
  if ns.refreshUI then
    ns.refreshUI()
  end
end

function ns.chatlogOff()
  local lc = ns.resolve("LoggingChat")
  if type(lc) == "function" then
    pcall(lc, false)
    ns.print("Chat-Log ausgeschaltet.")
  end
end

local function count(value, pattern)
  local _, n = value:gsub(pattern, "")
  return n
end

-- Leerzeichen, Tabulatoren und Zeilenumbrueche am Anfang und Ende entfernen.
local function trim(value)
  return (value:gsub("^%s+", ""):gsub("%s+$", ""))
end
ns.trim = trim

-- Erste Stelle, an der zwei Texte abweichen (nil, wenn gleich).
local function firstDiff(a, b)
  if a == b then
    return nil
  end
  for i = 1, math.max(#a, #b) do
    if a:sub(i, i) ~= b:sub(i, i) then
      return i
    end
  end
end

local function pasteChanged(box, userInput)
  local value = box:GetText() or ""
  -- Ein leeres Feld ist kein Einfuegen: Beim Anzeigen loest der Client ein
  -- solches Ereignis aus (im Spiel am 11.11.2026 gesehen), und ein frueheres
  -- Ergebnis in der Datei bliebe sonst nicht erhalten. Nach dem Leeren beginnt
  -- ein neuer Versuch.
  if value == "" then
    box.lastLen, box.largestJump = 0, 0
    return
  end
  local len = #value
  local jump = len - (box.lastLen or 0)
  box.lastLen = len
  box.largestJump = math.max(box.largestJump or 0, jump)
  local trimmed = trim(value)
  -- Der Text selbst wird nicht gespeichert: Ein echter Kopplungstext enthielte
  -- die Webhook-ID. Gespeichert werden nur Laengen, Zaehler und Vergleiche.
  tests().paste = {
    at = now(),
    length = len,
    matchesSample = value == ns.PASTE_SAMPLE,
    trimmedLength = #trimmed,
    matchesSampleTrimmed = trimmed == ns.PASTE_SAMPLE,
    firstDiffTrimmed = firstDiff(trimmed, ns.PASTE_SAMPLE),
    carriageReturns = count(value, "\r"),
    lineFeeds = count(value, "\n"),
    tabs = count(value, "\t"),
    spaces = count(value, " "),
    leadingWhitespace = #value - #(value:gsub("^%s+", "")),
    trailingWhitespace = #value - #(value:gsub("%s+$", "")),
    startsWithHAB1 = trimmed:sub(1, 5) == "HAB1|",
    largestJump = box.largestJump,
    userInput = userInput and true or false,
  }
  if ns.refreshUI then
    ns.refreshUI()
  end
end

-- ---------------------------------------------------------------------------
-- Fenster
-- ---------------------------------------------------------------------------

local win

local function button(parent, label, onClick)
  local b, templated = make("Button", nil, parent, "UIPanelButtonTemplate")
  b:SetSize(150, 24)
  if not templated then
    b:SetNormalFontObject("GameFontNormal")
    background(b, 0.6)
  end
  b:SetText(label)
  b:SetScript("OnClick", onClick)
  return b
end

local function buildUI()
  if win then
    return
  end
  local templated
  win, templated = make("Frame", "HABridgeProbeFrame", UIParent, "BasicFrameTemplateWithInset")
  win:SetSize(540, 660)
  win:SetPoint("CENTER")
  win:SetFrameStrata("DIALOG")
  win:SetMovable(true)
  win:EnableMouse(true)
  win:SetClampedToScreen(true)
  win:RegisterForDrag("LeftButton")
  win:SetScript("OnDragStart", win.StartMoving)
  win:SetScript("OnDragStop", win.StopMovingOrSizing)
  if not templated then
    background(win, 0.85)
    local close = make("Button", nil, win, "UIPanelCloseButton")
    close:SetSize(24, 24)
    close:SetPoint("TOPRIGHT", -4, -4)
    close:SetScript("OnClick", function()
      win:Hide()
    end)
  end
  if type(UISpecialFrames) == "table" then
    table.insert(UISpecialFrames, "HABridgeProbeFrame")
  end

  local title = win:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  title:SetPoint("TOP", 0, -5)
  title:SetText("HA Bridge Probe " .. ns.VERSION)

  win.summary = win:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  win.summary:SetPoint("TOPLEFT", 16, -34)
  win.summary:SetWidth(508)
  win.summary:SetJustifyH("LEFT")
  win.summary:SetJustifyV("TOP")

  local label = win:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  label:SetPoint("BOTTOMLEFT", 18, 112)
  label:SetWidth(500)
  label:SetJustifyH("LEFT")
  label:SetText("Einfüge-Test: Prüftext aus dem README hier mit Strg+V einfügen")

  local boxTemplated
  win.paste, boxTemplated = make("EditBox", nil, win, "InputBoxTemplate")
  win.paste:SetSize(496, 20)
  win.paste:SetPoint("BOTTOMLEFT", 22, 86)
  win.paste:SetAutoFocus(false)
  win.paste:SetMaxLetters(512)
  if not boxTemplated then
    win.paste:SetFontObject(ChatFontNormal or "GameFontHighlight")
    background(win.paste, 0.5)
  end
  win.paste:SetScript("OnTextChanged", pasteChanged)
  win.paste:SetScript("OnEscapePressed", win.paste.ClearFocus)
  win.paste:SetScript("OnEnterPressed", win.paste.ClearFocus)

  local b1 = button(win, "Erneut messen", function()
    ns.measure("button")
    ns.print("Messung wiederholt.")
  end)
  b1:SetPoint("BOTTOMLEFT", 16, 46)
  local b2 = button(win, "Chat-Log-Test", ns.chatlogTest)
  b2:SetPoint("LEFT", b1, "RIGHT", 12, 0)
  local b3 = button(win, "Speichern (/reload)", ns.reloadTest)
  b3:SetPoint("LEFT", b2, "RIGHT", 12, 0)

  local foot = win:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
  foot:SetPoint("BOTTOMLEFT", 18, 18)
  foot:SetWidth(504)
  foot:SetJustifyH("LEFT")
  foot:SetText("Ergebnis: WTF\\Account\\<Konto>\\SavedVariables\\HABridgeProbe.lua, geschrieben bei Logout oder /reload. Zum Teilen nur den Abschnitt [\"report\"] verwenden.")

  win:SetScript("OnShow", ns.refreshUI)
  win:Hide()
end

function ns.refreshUI()
  if not win or not win:IsShown() then
    return
  end
  local db = HABridgeProbeDB
  local s, run = ns.summary()
  local lines = {}
  local function add(fmt, ...)
    table.insert(lines, string.format(fmt, ...))
  end
  if not run then
    win.summary:SetText("Noch keine Messung. Sie startet 5 Sekunden nach dem Einloggen, oder: Erneut messen.")
    return
  end

  add("|cffffd100Client|r  %s (Build %s), Interface %s · Sprache %s",
    text(val(run, "GetBuildInfo", 1)), text(val(run, "GetBuildInfo", 2)),
    text(val(run, "GetBuildInfo", 4)), text(val(run, "GetLocale")))
  local projects = {}
  for k, v in pairs(run.projects or {}) do
    table.insert(projects, k:gsub("^WOW_PROJECT_", "") .. "=" .. v)
  end
  table.sort(projects)
  add("|cffffd100WOW_PROJECT_ID|r  %s  (%s)", text(_G.WOW_PROJECT_ID), table.concat(projects, ", "))
  add("|cffffd100Region|r  %s / %s", text(val(run, "GetCurrentRegion")), text(val(run, "GetCurrentRegionName")))

  -- Name und Realm: die zentrale Frage fuer den Charakterschluessel.
  local name, realm = val(run, "UnitFullName", 1), val(run, "UnitFullName", 2)
  add("|cffffd100UnitFullName|r  \"%s\" + \"%s\"  ->  Form \"%s\"", text(name), text(realm), text(ns.shape(name)))
  add("|cffffd100UnitPVPName|r  \"%s\" · |cffffd100GetUnitName|r  \"%s\"",
    text(val(run, "UnitPVPName")), text(val(run, "GetUnitName")))
  add("|cffffd100Realm|r  \"%s\" · normalisiert \"%s\" · ID %s",
    text(val(run, "GetRealmName")), text(val(run, "GetNormalizedRealmName")), text(val(run, "GetRealmID")))
  local guid = find(run, "UnitGUID")
  add("|cffffd100UnitGUID|r  %s%s", text(ns.maskGuid(val(run, "UnitGUID"))), guid and guid.secret and " (geheim)" or "")

  add(" ")
  add("|cffffd100Funktionen|r  %d von %d vorhanden, %d mit Fehler, %d mit geheimen Werten",
    s.available, s.total, s.failed, s.secret)
  if #s.missing > 0 then
    local shown = {}
    for i = 1, math.min(#s.missing, 6) do
      shown[i] = s.missing[i]
    end
    add("  fehlt: %s%s", table.concat(shown, ", "), #s.missing > 6 and " ..." or "")
  end
  local docHits = run.documentation and run.documentation.hits or {}
  add("|cffffd100Suche Nachname/Regelsatz|r  %d Treffer global (%s Fenster-Elemente übersprungen), %d in der API-Doku%s",
    #(run.scan or {}), text(run.scanSkippedWidgets), #docHits, run.documentation and run.documentation.error and (" (" .. run.documentation.error .. ")") or "")
  local preview = {}
  for i = 1, math.min(#docHits, 3) do
    preview[#preview + 1] = docHits[i]
  end
  for i = 1, math.min(#(run.scan or {}), 3) do
    preview[#preview + 1] = run.scan[i]
  end
  if #preview > 0 then
    add("  z. B. %s", table.concat(preview, ", "))
  end
  local json = run.json or {}
  add("|cffffd100SerializeJSON|r  %s", not json.available and "fehlt" or (json.ok and ("ok, Rückweg " .. yesno(json.roundtrip)) or "Fehler"))

  add(" ")
  local played = run.played
  add("|cffffd100Gold|r  %s · |cffffd100Stufe|r %s · |cffffd100Spielzeit|r %s",
    money(val(run, "GetMoney")), text(val(run, "UnitLevel")),
    played and type(played.total) == "number" and string.format("%.1f h", played.total / 3600) or "keine Antwort")
  add("|cffffd100Ort|r  %s / %s · Karte %s", text(val(run, "GetRealZoneText")), text(val(run, "GetSubZoneText")),
    text(val(run, "C_Map.GetBestMapForUnit")))
  local dura = find(run, "GetInventoryItemDurability (1-19)")
  add("|cffffd100Haltbarkeit|r  %s · |cffffd100Freie Plätze Rucksack|r %s · |cffffd100Sperren|r %s",
    dura and dura.min and string.format("%d %%", math.floor(dura.min * 100 + 0.5)) or "-",
    text(val(run, "C_Container.GetContainerNumFreeSlots(0)")), text(val(run, "GetNumSavedInstances")))

  add(" ")
  local t = db.tests
  local prev = ns.previous
  add("|cffffd100Sitzung|r  #%d · zuletzt gespeichert: %s", db.session.id,
    prev and string.format("#%d (sauber beendet: %s)", prev.id, yesno(prev.cleanExit)) or "keine")
  local r = t.reload
  add("|cffffd100/reload-Test|r  %s", not r and "nicht ausgeführt"
    or (r.ok and string.format("bestätigt (Logout %d s nach Klick)", r.secondsUntilLogout))
    or (r.confirmedAt and "nicht bestätigt") or "läuft")
  local p = t.paste
  if not p then
    add("|cffffd100Einfügen|r  nicht ausgeführt")
  else
    add("|cffffd100Einfügen|r  %d Zeichen, Prüftext %s, größter Sprung %d", p.length,
      p.matchesSample and "korrekt" or "abweichend", p.largestJump or 0)
    if p.trimmedLength and not p.matchesSample then
      add("  ohne Rand-Leerraum: %d Zeichen, Prüftext %s%s", p.trimmedLength,
        p.matchesSampleTrimmed and "korrekt" or "abweichend",
        p.firstDiffTrimmed and (" ab Zeichen " .. p.firstDiffTrimmed) or "")
      add("  Zeilenumbrüche CR %d, LF %d · Tabulatoren %d · Leerzeichen %d (Anfang %d, Ende %d)",
        p.carriageReturns, p.lineFeeds, p.tabs, p.spaces, p.leadingWhitespace, p.trailingWhitespace)
    end
  end
  local c = t.chatlog
  add("|cffffd100Chat-Log|r  %s", not c and "nicht ausgeführt"
    or string.format("Marke %s, Logging vorher %s, jetzt %s", c.token, text(c.priorState), text(c.stateAfter)))
  local st = t.settings
  add("|cffffd100Einstellungsseite|r  %s%s", st and (st.ok and "registriert" or ("Fehler: " .. text(st.error))) or "-",
    st and st.changed and " · Haken geändert" or "")
  local m = t.compartment
  local comp = run.compartment
  add("|cffffd100AddOn-Menü|r  %s · Objekt %s, sichtbar %s", m and m.clicked and "geklickt" or "noch nicht geklickt",
    comp and comp.exists and "vorhanden" or "fehlt", text(comp and comp.visible))
  local mb = t.minimap
  add("|cffffd100Minikarten-Knopf|r  %s", not mb and "-"
    or not mb.created and ("Fehler: " .. text(mb.error))
    or string.format("angelegt, %s, geklickt %s, verschoben %s", mb.shown and "sichtbar" or "ausgeblendet",
      yesno(mb.clicked), yesno(mb.dragged)))
  add("|cffffd100Nachname anzeigen|r  %s / %s · |cffffd100Voreinstellung|r  %s",
    text(val(run, "C_PlayerInfo.ShouldDisplaySurname")), text(val(run, "C_PlayerInfo.ShouldDisplaySurname(player)")),
    text(val(run, "C_GameRules.GetForeverExperiencePreset")))
  local s2 = db.session
  add("|cffffd100Zone bekannt|r  %s", s2.zoneReadyAt and s2.enteredWorldAt
    and string.format("%d s nach dem Betreten der Welt (%s)", s2.zoneReadyAt - s2.enteredWorldAt, text(s2.zoneAtEvent))
    or "noch kein Zonenwechsel-Ereignis")
  local lo = prev and prev.logout
  add("|cffffd100Beim letzten Logout|r  %s", not lo and "-"
    or string.format("%s / %s · Karte %s · %s", text(lo.zone), text(lo.subzone), text(lo.mapID), money(lo.money)))
  win.summary:SetText(table.concat(lines, "\n"))
end

function ns.showUI()
  buildUI()
  win:Show()
end

function ns.toggleUI()
  buildUI()
  if win:IsShown() then
    win:Hide()
  else
    win:Show()
  end
end

-- ---------------------------------------------------------------------------
-- Einstellungsseite (Settings API) und AddOn-Menue
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- Eigener Knopf an der Minikarte
-- ---------------------------------------------------------------------------

-- Im Spiel gab es AddonCompartmentFrame, aber keinen sichtbaren Knopf
-- (11.11.2026); ein anderes Addon zeigte einen eigenen Knopf ueber LibDBIcon.
-- Dieser Knopf kommt ohne Bibliothek aus: Kreisbahn um die Minikarte, Winkel
-- in den Optionen.
local minimapButton

local function minimapRadius()
  local ok, width = pcall(Minimap.GetWidth, Minimap)
  if ok and type(width) == "number" and width > 0 then
    return width / 2 + 5
  end
  return 80
end

local function placeMinimapButton(angle)
  local rad = math.rad(angle)
  local r = minimapRadius()
  minimapButton:ClearAllPoints()
  minimapButton:SetPoint("CENTER", Minimap, "CENTER", math.cos(rad) * r, math.sin(rad) * r)
end

local function dragMinimapButton()
  local mx, my = Minimap:GetCenter()
  local px, py = GetCursorPosition()
  local scale = Minimap:GetEffectiveScale()
  local angle = math.deg(math.atan2(py / scale - my, px / scale - mx))
  HABridgeProbeDB.options.minimapAngle = angle
  placeMinimapButton(angle)
end

function ns.updateMinimapButton()
  if not minimapButton then
    return
  end
  if HABridgeProbeDB.options.showMinimapButton then
    minimapButton:Show()
  else
    minimapButton:Hide()
  end
  local t = tests().minimap
  if t then
    t.shown = minimapButton:IsShown() and true or false
  end
end

local function createMinimapButton()
  local t = { at = now() }
  tests().minimap = t
  if type(Minimap) ~= "table" then
    t.error = "Minimap fehlt"
    return
  end
  local ok, err = pcall(function()
    local b = CreateFrame("Button", "HABridgeProbeMinimapButton", Minimap)
    minimapButton = b
    b:SetSize(31, 31)
    b:SetFrameStrata("MEDIUM")
    b:SetFrameLevel(8)
    b:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    b:RegisterForDrag("LeftButton")
    b:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
    local bg = b:CreateTexture(nil, "BACKGROUND")
    bg:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
    bg:SetSize(20, 20)
    bg:SetPoint("TOPLEFT", 7, -5)
    local icon = b:CreateTexture(nil, "ARTWORK")
    icon:SetTexture("Interface\\Icons\\INV_Misc_Spyglass_02")
    icon:SetSize(17, 17)
    icon:SetPoint("TOPLEFT", 7, -6)
    local border = b:CreateTexture(nil, "OVERLAY")
    border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    border:SetSize(53, 53)
    border:SetPoint("TOPLEFT")
    b:SetScript("OnClick", function(_, mouse)
      t.clicked = now()
      t.lastButton = tostring(mouse)
      if mouse == "RightButton" then
        ns.openSettings()
      else
        ns.toggleUI()
      end
      if ns.refreshUI then
        ns.refreshUI()
      end
    end)
    b:SetScript("OnDragStart", function(self)
      self:SetScript("OnUpdate", dragMinimapButton)
    end)
    b:SetScript("OnDragStop", function(self)
      self:SetScript("OnUpdate", nil)
      t.dragged = now()
      t.angle = math.floor(HABridgeProbeDB.options.minimapAngle + 0.5)
    end)
    b:SetScript("OnEnter", function(self)
      t.hovered = now()
      if GameTooltip then
        GameTooltip:SetOwner(self, "ANCHOR_LEFT")
        GameTooltip:SetText("HA Bridge Probe " .. ns.VERSION)
        GameTooltip:AddLine("Linksklick: Fenster zeigen oder verbergen", 1, 1, 1)
        GameTooltip:AddLine("Rechtsklick: Einstellungen", 1, 1, 1)
        GameTooltip:AddLine("Ziehen: um die Minikarte verschieben", 1, 1, 1)
        GameTooltip:Show()
      end
    end)
    b:SetScript("OnLeave", function()
      if GameTooltip then
        GameTooltip:Hide()
      end
    end)
    placeMinimapButton(HABridgeProbeDB.options.minimapAngle or 225)
  end)
  t.created = ok
  if not ok then
    t.error = tostring(err)
    return
  end
  ns.updateMinimapButton()
end

function ns.toggleMinimapButton()
  HABridgeProbeDB.options.showMinimapButton = not HABridgeProbeDB.options.showMinimapButton
  ns.updateMinimapButton()
  ns.print("Knopf an der Minikarte " .. (HABridgeProbeDB.options.showMinimapButton and "an." or "aus."))
end

local function registerSettings()
  local t = { at = now() }
  local ok, err = pcall(function()
    local category = Settings.RegisterVerticalLayoutCategory("HA Bridge Probe")
    local varType = (Settings.VarType and Settings.VarType.Boolean) or "boolean"
    local setting = Settings.RegisterAddOnSetting(category, "HABridgeProbe_ShowOnLogin", "showOnLogin",
      HABridgeProbeDB.options, varType, "Fenster nach dem Einloggen zeigen", true)
    Settings.CreateCheckbox(category, setting, "Zeigt das Fenster der Probe 5 Sekunden nach dem Einloggen.")
    local button = Settings.RegisterAddOnSetting(category, "HABridgeProbe_ShowMinimapButton",
      "showMinimapButton", HABridgeProbeDB.options, varType, "Knopf an der Minikarte zeigen", true)
    Settings.CreateCheckbox(category, button, "Eigener Knopf am Rand der Minikarte; mit der Maus verschiebbar.")
    Settings.RegisterAddOnCategory(category)
    ns.settingsCategory = category
    t.callbackAvailable = type(Settings.SetOnValueChangedCallback) == "function"
    if t.callbackAvailable then
      Settings.SetOnValueChangedCallback("HABridgeProbe_ShowOnLogin", function()
        tests().settings.changed = now()
        if ns.refreshUI then
          ns.refreshUI()
        end
      end)
      Settings.SetOnValueChangedCallback("HABridgeProbe_ShowMinimapButton", function()
        tests().settings.changed = now()
        ns.updateMinimapButton()
      end)
    end
  end)
  t.ok = ok
  if not ok then
    t.error = tostring(err)
  end
  tests().settings = t
end

function ns.openSettings()
  local category = ns.settingsCategory
  if not category then
    ns.print("Einstellungsseite nicht registriert (siehe Fenster).")
    return
  end
  local id = type(category.GetID) == "function" and category:GetID() or category
  if not pcall(Settings.OpenToCategory, id) then
    pcall(Settings.OpenToCategory, category)
  end
end

function HABridgeProbe_OnCompartmentClick(_, buttonName)
  local m = tests().compartment or {}
  m.clicked = now()
  m.button = tostring(buttonName)
  tests().compartment = m
  ns.toggleUI()
end

function HABridgeProbe_OnCompartmentEnter(_, owner)
  local m = tests().compartment or {}
  m.hovered = now()
  tests().compartment = m
  if not GameTooltip then
    return
  end
  if not pcall(GameTooltip.SetOwner, GameTooltip, owner, "ANCHOR_LEFT") then
    GameTooltip:SetOwner(UIParent, "ANCHOR_CURSOR")
  end
  GameTooltip:SetText("HA Bridge Probe")
  GameTooltip:AddLine("Klick: Fenster zeigen oder verbergen", 1, 1, 1)
  GameTooltip:Show()
end

function HABridgeProbe_OnCompartmentLeave()
  if GameTooltip then
    GameTooltip:Hide()
  end
end

-- ---------------------------------------------------------------------------
-- Slash-Befehle
-- ---------------------------------------------------------------------------

local HELP = {
  "/habp - Fenster zeigen oder verbergen",
  "/habp messen - Messung wiederholen",
  "/habp reload - /reload-Test (speichert die Datei)",
  "/habp chatlog - Chat-Log-Test, /habp chatlog aus - Chat-Log abschalten",
  "/habp optionen - Einstellungsseite öffnen",
  "/habp knopf - Knopf an der Minikarte ein- oder ausblenden",
  "/habp reset ja - alle Ergebnisse löschen",
}

SLASH_HABRIDGEPROBE1 = "/habp"
SlashCmdList.HABRIDGEPROBE = function(msg)
  msg = (msg or ""):lower():gsub("^%s+", ""):gsub("%s+$", "")
  if msg == "" then
    ns.toggleUI()
  elseif msg == "messen" then
    ns.measure("slash")
    ns.print("Messung wiederholt.")
  elseif msg == "reload" then
    ns.reloadTest()
  elseif msg == "chatlog" then
    ns.chatlogTest()
  elseif msg == "chatlog aus" then
    ns.chatlogOff()
  elseif msg == "knopf" then
    ns.toggleMinimapButton()
  elseif msg == "optionen" then
    ns.openSettings()
  elseif msg == "reset ja" then
    -- Danach sofort neu laden: Ohne Tabelle liefe das Addon nicht weiter.
    HABridgeProbeDB = nil
    ns.print("Ergebnisse gelöscht, lade neu ...")
    pcall(ReloadUI)
  else
    for _, line in ipairs(HELP) do
      ns.print(line)
    end
  end
end

function ns.onLoaded()
  registerSettings()
  buildUI()
  createMinimapButton()
end
