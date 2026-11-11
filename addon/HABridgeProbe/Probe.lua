-- HA Bridge Probe: Test-Addon fuer WoW Forever.
--
-- Prueft im echten Client, welche Spieldaten ein Addon lesen kann, und legt
-- alles in der SavedVariables-Datei ab:
--   WTF\Account\<Konto>\SavedVariables\HABridgeProbe.lua
-- Es sendet nichts und schreibt keine anderen Dateien (das kann ein Addon auch
-- gar nicht). Grundlage ist die Machbarkeitsstudie zur Addon-Bruecke; jede
-- offene Frage dort hat hier eine Messung.
--
-- Abschnitte in HABridgeProbeDB:
--   runs      letzte Messlaeufe mit Rohwerten (nur auf dem eigenen PC)
--   report    dieselben Daten mit unkenntlich gemachten Namen, zum Teilen
--   sessions  Sitzungsprotokoll (Absturz- und /reload-Test)
--   tests     Einfuegen (Strg+V), /reload, Chat-Log, Einstellungsseite, Menue

local ADDON, ns = ...

ns.VERSION = "0.1.1"
ns.SCHEMA = 1
local MAX_RUNS = 5
local MAX_SESSIONS = 10
local MAX_LIST = 60
local MAX_SCAN = 200

-- Pruefzeile fuer den Einfuege-Test (steht auch im README). 94 Zeichen, so lang
-- wie ein echter Kopplungstext mit 64-stelliger Webhook-ID.
ns.PASTE_SAMPLE = "HAB1|http://192.168.0.10:8123|" .. string.rep("0123456789abcdef", 4)

-- Suchbegriffe fuer unbekannte Forever-Funktionen (Nachname, Regelsatz, ...).
local SCAN_PATTERNS = {
  "surname", "lastname", "familyname", "ruleset", "forever", "camelot", "skyborne",
}

-- Ereignisse, die die Bruecke nutzen wuerde; das Addon prueft, ob der Client
-- sie kennt, und zaehlt, wie oft sie in einer Sitzung kommen.
local EVENTS = {
  "ADDON_LOADED", "PLAYER_ENTERING_WORLD", "PLAYER_LOGOUT", "TIME_PLAYED_MSG",
  "PLAYER_MONEY", "PLAYER_XP_UPDATE", "PLAYER_LEVEL_UP", "ZONE_CHANGED",
  "ZONE_CHANGED_NEW_AREA", "UPDATE_INSTANCE_INFO", "CURRENCY_DISPLAY_UPDATE",
  "BAG_UPDATE_DELAYED", "UPDATE_INVENTORY_DURABILITY", "QUEST_LOG_UPDATE",
  "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED", "ADDON_RESTRICTION_STATE_CHANGED",
}

-- ---------------------------------------------------------------------------
-- Hilfsfunktionen
-- ---------------------------------------------------------------------------

local function now()
  if type(GetServerTime) == "function" then
    return GetServerTime()
  end
  return time()
end

function ns.print(msg)
  print("|cff33ccff[HA Bridge Probe]|r " .. msg)
end

-- Secret Values (Midnight-Regeln) duerfen nicht ausgewertet werden; sie
-- werden durch eine Markierung ersetzt.
local function isSecret(v)
  if type(issecretvalue) ~= "function" then
    return false
  end
  local ok, res = pcall(issecretvalue, v)
  return ok and res == true
end

local function safe(v, depth)
  depth = depth or 0
  if isSecret(v) then
    return "<secret>"
  end
  local t = type(v)
  if t == "nil" then
    return "<nil>"
  elseif t == "string" or t == "number" or t == "boolean" then
    return v
  elseif t == "table" then
    if depth >= 3 then
      return "<table>"
    end
    if type(issecrettable) == "function" then
      local ok, res = pcall(issecrettable, v)
      if ok and res then
        return "<secret table>"
      end
    end
    local out, n = {}, 0
    local ok = pcall(function()
      for k, val in pairs(v) do
        n = n + 1
        if n > MAX_LIST then
          out["<more>"] = true
          break
        end
        local key = k
        if isSecret(k) or (type(k) ~= "string" and type(k) ~= "number") then
          key = "<key " .. n .. ">"
        end
        out[key] = safe(val, depth + 1)
      end
    end)
    if not ok then
      return "<forbidden table>"
    end
    return out
  end
  return "<" .. t .. ">"
end
ns.safe = safe

local function resolve(path)
  local obj = _G
  for part in string.gmatch(path, "[^%.]+") do
    if type(obj) ~= "table" then
      return nil
    end
    local ok, val = pcall(function()
      return obj[part]
    end)
    if not ok then
      return nil
    end
    obj = val
  end
  return obj
end
ns.resolve = resolve

local function pack(...)
  return { n = select("#", ...), ... }
end

-- Ruft eine Funktion geschuetzt auf und haelt fest: vorhanden, Fehler, Werte.
local function call(label, path, ...)
  local entry = { label = label, fn = path }
  local fn = resolve(path)
  if type(fn) ~= "function" then
    entry.available = false
    return entry
  end
  entry.available = true
  local r = pack(pcall(fn, ...))
  entry.ok = r[1]
  if not r[1] then
    entry.error = tostring(r[2])
    return entry
  end
  entry.values = {}
  for i = 2, r.n do
    local value = safe(r[i])
    entry.values[i - 1] = value
    if value == "<secret>" then
      entry.secret = true
    end
  end
  entry.count = r.n - 1
  return entry
end
ns.call = call

local function first(entry)
  if entry.ok and entry.values then
    local v = entry.values[1]
    if v ~= "<nil>" and v ~= "<secret>" then
      return v
    end
  end
  return nil
end

-- Name unkenntlich machen, Aufbau behalten: "Mara Sturmwind" -> "Aaaa Aaaaaaaaa".
function ns.shape(s)
  if type(s) ~= "string" then
    return s
  end
  s = s:gsub("[\192-\255][\128-\191]*", "a")
  s = s:gsub("%u", "A")
  s = s:gsub("%l", "a")
  s = s:gsub("%d", "0")
  return s
end

-- GUID kuerzen: Typ und Server-ID bleiben, der Rest wird ersetzt.
function ns.maskGuid(g)
  if type(g) ~= "string" then
    return g
  end
  local head, rest = g:match("^([^%-]+%-[^%-]+%-)(.*)$")
  if head then
    return head .. string.rep("x", #rest)
  end
  return string.rep("x", #g)
end

local function after(seconds, fn)
  if C_Timer and type(C_Timer.After) == "function" then
    C_Timer.After(seconds, fn)
    return
  end
  local frame, elapsed = CreateFrame("Frame"), 0
  frame:SetScript("OnUpdate", function(self, delta)
    elapsed = elapsed + delta
    if elapsed >= seconds then
      self:SetScript("OnUpdate", nil)
      fn()
    end
  end)
end
ns.after = after

-- ---------------------------------------------------------------------------
-- Messungen
-- ---------------------------------------------------------------------------

-- Rueckgabewerte mit Namen oder Kennungen (Position je Funktion); im Bericht
-- unkenntlich. Realm bzw. Regelsatz bleiben lesbar, sie sind die Frage.
local PERSONAL = {
  UnitName = { [1] = "shape" },
  UnitFullName = { [1] = "shape" },
  UnitNameUnmodified = { [1] = "shape" },
  GetUnitName = { [1] = "shape" },
  UnitPVPName = { [1] = "shape" },
  GetGuildInfo = { [1] = "shape", [2] = "shape" },
  UnitGUID = { [1] = "guid" },
}

local function measureEnvironment(calls)
  local add = function(...)
    table.insert(calls, call(...))
  end
  add("GetBuildInfo", "GetBuildInfo")
  add("GetLocale", "GetLocale")
  add("GetCurrentRegion", "GetCurrentRegion")
  add("GetCurrentRegionName", "GetCurrentRegionName")
  add("GetRealmName", "GetRealmName")
  add("GetNormalizedRealmName", "GetNormalizedRealmName")
  add("GetRealmID", "GetRealmID")
  add("UnitName", "UnitName", "player")
  add("UnitFullName", "UnitFullName", "player")
  add("UnitNameUnmodified", "UnitNameUnmodified", "player")
  add("GetUnitName", "GetUnitName", "player", true)
  add("UnitPVPName", "UnitPVPName", "player")
  add("UnitGUID", "UnitGUID", "player")
  add("IsTrialAccount", "IsTrialAccount")
  add("IsVeteranTrialAccount", "IsVeteranTrialAccount")
  add("InCombatLockdown", "InCombatLockdown")
  add("C_AddOns.GetAddOnMetadata(Version)", "C_AddOns.GetAddOnMetadata", ADDON, "Version")
  add("LoggingChat (Zustand)", "LoggingChat")
end

local function measureCharacter(calls)
  local add = function(...)
    local entry = call(...)
    table.insert(calls, entry)
    return entry
  end
  add("UnitLevel", "UnitLevel", "player")
  add("UnitClass", "UnitClass", "player")
  add("UnitRace", "UnitRace", "player")
  add("UnitSex", "UnitSex", "player")
  add("UnitFactionGroup", "UnitFactionGroup", "player")
  add("GetMaxPlayerLevel", "GetMaxPlayerLevel")
  add("GetMoney", "GetMoney")
  add("UnitXP", "UnitXP", "player")
  add("UnitXPMax", "UnitXPMax", "player")
  add("GetXPExhaustion", "GetXPExhaustion")
  add("GetRestState", "GetRestState")
  add("GetRealZoneText", "GetRealZoneText")
  add("GetZoneText", "GetZoneText")
  add("GetSubZoneText", "GetSubZoneText")
  add("GetMinimapZoneText", "GetMinimapZoneText")
  add("IsInInstance", "IsInInstance")
  add("GetInstanceInfo", "GetInstanceInfo")
  local map = add("C_Map.GetBestMapForUnit", "C_Map.GetBestMapForUnit", "player")
  local mapID = first(map)
  if type(mapID) == "number" then
    add("C_Map.GetMapInfo", "C_Map.GetMapInfo", mapID)
    -- Koordinaten werden nie gespeichert, nur ob ein Wert kam.
    local pos = call("C_Map.GetPlayerMapPosition", "C_Map.GetPlayerMapPosition", mapID, "player")
    if pos.values then
      local v = pos.values[1]
      pos.values = { (v == "<nil>" or v == "<secret>") and v or "<Wert vorhanden>" }
    end
    table.insert(calls, pos)
  end
  add("GetAverageItemLevel", "GetAverageItemLevel")
  add("GetGuildInfo", "GetGuildInfo", "player")
  add("GetProfessions", "GetProfessions")
  add("GetNumSkillLines", "GetNumSkillLines")

  -- Haltbarkeit: niedrigster Wert ueber alle Plaetze (1-19).
  local dura = { label = "GetInventoryItemDurability (1-19)", fn = "GetInventoryItemDurability" }
  if type(GetInventoryItemDurability) == "function" then
    dura.available, dura.ok, dura.slots, dura.min = true, true, 0, nil
    for slot = 1, 19 do
      local ok, cur, max = pcall(GetInventoryItemDurability, slot)
      if not ok then
        dura.ok, dura.error = false, tostring(cur)
        break
      end
      if isSecret(cur) or isSecret(max) then
        dura.secret = true
      elseif type(cur) == "number" and type(max) == "number" and max > 0 then
        dura.slots = dura.slots + 1
        local pct = cur / max
        if not dura.min or pct < dura.min then
          dura.min = pct
        end
      end
    end
  else
    dura.available = false
  end
  table.insert(calls, dura)

  -- Taschen 0-5 (5 = Reagenzientasche in Retail).
  for bag = 0, 5 do
    add("C_Container.GetContainerNumFreeSlots(" .. bag .. ")", "C_Container.GetContainerNumFreeSlots", bag)
    add("C_Container.GetContainerNumSlots(" .. bag .. ")", "C_Container.GetContainerNumSlots", bag)
  end

  -- Instanz-Sperren.
  local num = add("GetNumSavedInstances", "GetNumSavedInstances")
  local count = first(num)
  if type(count) == "number" then
    for i = 1, math.min(count, 20) do
      add("GetSavedInstanceInfo(" .. i .. ")", "GetSavedInstanceInfo", i)
    end
  end

  -- Waehrungen aus der Waehrungsliste, mit ID.
  local size = first(add("C_CurrencyInfo.GetCurrencyListSize", "C_CurrencyInfo.GetCurrencyListSize"))
  if type(size) == "number" then
    for i = 1, math.min(size, MAX_LIST) do
      local info = add("C_CurrencyInfo.GetCurrencyListInfo(" .. i .. ")", "C_CurrencyInfo.GetCurrencyListInfo", i)
      local link = first(call("link", "C_CurrencyInfo.GetCurrencyListLink", i))
      if type(link) == "string" then
        info.currencyID = first(call("id", "C_CurrencyInfo.GetCurrencyIDFromLink", link))
      end
    end
  end

  add("C_QuestLog.GetNumQuestLogEntries", "C_QuestLog.GetNumQuestLogEntries")
  add("GetNumQuestLogEntries", "GetNumQuestLogEntries")
  add("C_DateAndTime.GetSecondsUntilWeeklyReset", "C_DateAndTime.GetSecondsUntilWeeklyReset")
  add("C_DateAndTime.GetSecondsUntilDailyReset", "C_DateAndTime.GetSecondsUntilDailyReset")
  add("GetServerTime", "GetServerTime")
  add("time", "time")
end

-- Welche Funktionen und Objekte gibt es ueberhaupt (ohne Aufruf)?
local function measureAvailability()
  local names = {
    "issecretvalue", "canaccessvalue", "issecrettable", "canaccesstable",
    "C_RestrictedActions.IsAddOnRestrictionActive", "C_RestrictedActions.GetAddOnRestrictionState",
    "RequestTimePlayed", "RequestRaidInfo", "ReloadUI", "LoggingChat", "LoggingCombat",
    "Screenshot", "C_ChatInfo.SendAddonMessage", "C_ChatInfo.SendChatMessage", "SendChatMessage",
    "BNSendWhisper", "C_BattleNet.SendWhisper",
    "C_EncodingUtil.SerializeJSON", "C_EncodingUtil.DeserializeJSON",
    "Settings.RegisterVerticalLayoutCategory", "Settings.RegisterCanvasLayoutCategory",
    "Settings.RegisterAddOnSetting", "Settings.CreateCheckbox", "Settings.RegisterAddOnCategory",
    "Settings.OpenToCategory", "AddonCompartmentFrame", "C_Timer.After", "C_AddOns.LoadAddOn",
    "GetCurrentRegion", "GetCurrentRegionName",
  }
  local out = {}
  for _, name in ipairs(names) do
    out[name] = type(resolve(name))
  end
  -- Spielversionen als Konstanten (WOW_PROJECT_*).
  local projects = {}
  for k, v in pairs(_G) do
    if type(k) == "string" and k:find("^WOW_PROJECT_") and type(v) == "number" then
      projects[k] = v
    end
  end
  return out, projects
end

-- JSON im Client (Grundlage fuer die Bruecke).
local function measureJSON()
  local res = {}
  local fn = resolve("C_EncodingUtil.SerializeJSON")
  res.available = type(fn) == "function"
  if not res.available then
    return res
  end
  local sample = { zahl = 1834520, text = "Ein Täst", liste = { 1, 2, 3 }, wahr = true }
  local ok, out = pcall(fn, sample)
  res.ok = ok
  if ok then
    res.output = safe(out)
  else
    res.output = tostring(out)
  end
  local back = resolve("C_EncodingUtil.DeserializeJSON")
  if ok and type(back) == "function" then
    local ok2, parsed = pcall(back, out)
    res.roundtrip = ok2 and type(parsed) == "table" and parsed.zahl == 1834520
  end
  return res
end

-- Globale Namen und C_-Namensraeume nach Suchbegriffen durchsuchen.
local function scanGlobals()
  local hits, total = {}, 0
  local function check(name, kind)
    if total >= MAX_SCAN then
      return
    end
    local lower = name:lower()
    for _, p in ipairs(SCAN_PATTERNS) do
      if lower:find(p, 1, true) then
        total = total + 1
        table.insert(hits, name .. " (" .. kind .. ")")
        return
      end
    end
  end
  for k, v in pairs(_G) do
    if type(k) == "string" then
      check(k, type(v))
      if k:find("^C_") and type(v) == "table" then
        pcall(function()
          for fk, fv in pairs(v) do
            if type(fk) == "string" then
              check(k .. "." .. fk, type(fv))
            end
          end
        end)
      end
    end
  end
  table.sort(hits)
  return hits
end

-- Blizzards API-Dokumentation im Client nach denselben Begriffen durchsuchen
-- (Funktionen, Rueckgabefelder, Ereignisse, Tabellenfelder).
local function scanDocumentation()
  local res = { hits = {} }
  local load = resolve("C_AddOns.LoadAddOn") or resolve("LoadAddOn")
  if type(load) ~= "function" then
    res.error = "LoadAddOn fehlt"
    return res
  end
  local ok, loaded, reason = pcall(load, "Blizzard_APIDocumentationGenerated")
  if ok then
    res.loaded, res.reason = safe(loaded), safe(reason)
  else
    res.loaded, res.reason = false, tostring(loaded)
  end
  local doc = resolve("APIDocumentation")
  if type(doc) ~= "table" then
    res.error = "APIDocumentation fehlt"
    return res
  end
  local seen, nodes, total = {}, 0, 0
  local function walk(t, path, depth)
    if seen[t] or depth > 7 or nodes > 300000 or total >= MAX_SCAN then
      return
    end
    seen[t] = true
    local name = rawget(t, "Name")
    if type(name) == "string" then
      path = path == "" and name or (path .. "." .. name)
      local lower = name:lower()
      for _, p in ipairs(SCAN_PATTERNS) do
        if lower:find(p, 1, true) then
          total = total + 1
          table.insert(res.hits, path)
          break
        end
      end
    end
    for _, v in pairs(t) do
      nodes = nodes + 1
      if type(v) == "table" then
        walk(v, path, depth + 1)
      end
    end
  end
  local okWalk, err = pcall(walk, rawget(doc, "systems") or doc, "", 0)
  if not okWalk then
    res.error = tostring(err)
  end
  res.nodes = nodes
  table.sort(res.hits)
  return res
end

-- ---------------------------------------------------------------------------
-- Messlauf, Bericht, Sitzungen
-- ---------------------------------------------------------------------------

local function buildReport(run)
  local report = {
    probe = ns.VERSION,
    at = run.at,
    trigger = run.trigger,
    availability = run.availability,
    projects = run.projects,
    json = run.json,
    scan = run.scan,
    documentation = run.documentation and {
      loaded = run.documentation.loaded,
      error = run.documentation.error,
      hits = run.documentation.hits,
    },
    calls = {},
  }
  for _, entry in ipairs(run.calls) do
    local copy = {}
    for k, v in pairs(entry) do
      copy[k] = v
    end
    local modes = PERSONAL[entry.fn]
    if modes and entry.values then
      copy.values = {}
      for i, v in ipairs(entry.values) do
        local mode = modes[i]
        if mode == "guid" then
          v = ns.maskGuid(v)
        elseif mode == "shape" then
          v = ns.shape(v)
        end
        copy.values[i] = v
      end
    end
    table.insert(report.calls, copy)
  end
  local sessions = {}
  for i, s in ipairs(HABridgeProbeDB.sessions or {}) do
    sessions[i] = {
      id = s.id, startedAt = s.startedAt, heartbeat = s.heartbeat,
      cleanExit = s.cleanExit, guid = ns.maskGuid(s.guid), reloads = s.reloads,
    }
  end
  report.sessions = sessions
  report.tests = HABridgeProbeDB.tests
  report.events = HABridgeProbeDB.session and HABridgeProbeDB.session.events
  return report
end

function ns.measure(trigger)
  local db = HABridgeProbeDB
  if type(InCombatLockdown) == "function" and InCombatLockdown() then
    ns.pendingMeasure = trigger
    ns.print("Im Kampf: Messung folgt nach dem Kampf.")
    return
  end
  local run = { at = now(), trigger = trigger, calls = {} }
  local okAll, err = pcall(function()
    measureEnvironment(run.calls)
    measureCharacter(run.calls)
    run.availability, run.projects = measureAvailability()
    run.json = measureJSON()
    -- Suche nur einmal je Sitzung, sie ist aufwendig.
    ns.scanCache = ns.scanCache or { scan = scanGlobals(), documentation = scanDocumentation() }
    run.scan = ns.scanCache.scan
    run.documentation = ns.scanCache.documentation
  end)
  if not okAll then
    run.error = tostring(err)
  end
  run.played = ns.played
  table.insert(db.runs, 1, run)
  while #db.runs > MAX_RUNS do
    table.remove(db.runs)
  end
  db.report = buildReport(run)
  if ns.refreshUI then
    ns.refreshUI()
  end
  return run
end

function ns.summary()
  local run = HABridgeProbeDB.runs[1]
  if not run then
    return nil
  end
  local s = { total = 0, available = 0, failed = 0, secret = 0, missing = {} }
  for _, e in ipairs(run.calls) do
    s.total = s.total + 1
    if e.available then
      s.available = s.available + 1
      if e.ok == false then
        s.failed = s.failed + 1
      end
      if e.secret then
        s.secret = s.secret + 1
      end
    else
      table.insert(s.missing, e.label)
    end
  end
  return s, run
end

local function startSession()
  local db = HABridgeProbeDB
  db.sessions = db.sessions or {}
  -- Die zuletzt gespeicherte Sitzung: Hat der Client die Datei ohne Logout
  -- geschrieben (Absturz), steht dort cleanExit = false.
  ns.previous = db.sessions[1]
  db.sessionCounter = (db.sessionCounter or 0) + 1
  db.session = {
    id = db.sessionCounter, startedAt = now(), heartbeat = now(),
    cleanExit = false, events = {}, reloads = 0,
  }
  table.insert(db.sessions, 1, db.session)
  while #db.sessions > MAX_SESSIONS do
    table.remove(db.sessions)
  end
  -- /reload-Test: Der Knopf merkt sich den Zeitpunkt, die neue Sitzung
  -- bestaetigt ihn. Kommt die Markierung hier an, hat /reload die Datei
  -- geschrieben.
  -- Gilt nur, wenn die vorige Sitzung kurz nach dem Klick endete; sonst kam
  -- die Markierung erst mit einem spaeteren normalen Logout an.
  local reload = db.tests.reload
  if reload and reload.requestedAt and not reload.confirmedAt then
    reload.confirmedAt = now()
    local ended = ns.previous and ns.previous.loggedOutAt
    reload.secondsUntilLogout = ended and (ended - reload.requestedAt) or nil
    reload.ok = reload.secondsUntilLogout ~= nil and reload.secondsUntilLogout <= 10
    if ns.previous then
      ns.previous.reloads = (ns.previous.reloads or 0) + 1
    end
  end
end

local function heartbeat()
  if HABridgeProbeDB and HABridgeProbeDB.session then
    HABridgeProbeDB.session.heartbeat = now()
  end
  after(30, heartbeat)
end

-- ---------------------------------------------------------------------------
-- Ereignisse
-- ---------------------------------------------------------------------------

local frame = CreateFrame("Frame")
ns.frame = frame
ns.eventSupport = {}
for _, ev in ipairs(EVENTS) do
  local ok, err = pcall(frame.RegisterEvent, frame, ev)
  ns.eventSupport[ev] = ok and true or tostring(err)
end

frame:SetScript("OnEvent", function(_, event, arg1, arg2)
  local db = HABridgeProbeDB
  if db and db.session then
    db.session.events[event] = (db.session.events[event] or 0) + 1
  end

  if event == "ADDON_LOADED" and arg1 == ADDON then
    HABridgeProbeDB = HABridgeProbeDB or {}
    db = HABridgeProbeDB
    db.schema = ns.SCHEMA
    db.probe = ns.VERSION
    db.runs = db.runs or {}
    db.tests = db.tests or {}
    db.options = db.options or { showOnLogin = true }
    db.eventSupport = ns.eventSupport
    startSession()
    db.session.events[event] = 1
    if ns.onLoaded then
      ns.onLoaded()
    end
  elseif event == "PLAYER_ENTERING_WORLD" then
    local isLogin, isReload = arg1, arg2
    if isLogin or isReload or not ns.started then
      ns.started = true
      -- Sperren und Spielzeit anfordern; gemessen wird 5 s spaeter, wenn die
      -- Antworten da sind.
      if type(RequestRaidInfo) == "function" then
        pcall(RequestRaidInfo)
      end
      if type(RequestTimePlayed) == "function" then
        pcall(RequestTimePlayed)
      end
      heartbeat()
      after(5, function()
        ns.measure(isReload and "reload" or "login")
        local s = ns.summary()
        if s then
          ns.print(string.format(
            "Messung fertig: %d von %d Funktionen vorhanden, %d mit Fehler. /habp zeigt das Fenster.",
            s.available, s.total, s.failed
          ))
        end
        if db.options.showOnLogin and ns.showUI then
          ns.showUI()
        end
      end)
    end
  elseif event == "TIME_PLAYED_MSG" then
    ns.played = { total = safe(arg1), level = safe(arg2), at = now() }
    if db and db.runs and db.runs[1] then
      db.runs[1].played = ns.played
    end
    if ns.refreshUI then
      ns.refreshUI()
    end
  elseif event == "PLAYER_REGEN_ENABLED" and ns.pendingMeasure then
    local trigger = ns.pendingMeasure
    ns.pendingMeasure = nil
    ns.measure(trigger)
  elseif event == "PLAYER_LOGOUT" then
    -- Letztes Ereignis, bevor der Client die Datei schreibt (Logout, /reload,
    -- Beenden). Fehlt cleanExit = true in der Datei, wurde ohne Logout
    -- gespeichert.
    if db and db.session then
      db.session.cleanExit = true
      db.session.heartbeat = now()
      db.session.loggedOutAt = now()
    end
  end
end)
