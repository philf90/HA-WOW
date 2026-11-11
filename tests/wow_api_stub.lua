-- Nachbau der WoW-API fuer tests/test_testaddon.py (Lua 5.1, ueber lupa).
-- MODE: "full", "minimal" (viele Funktionen und Vorlagen fehlen), "secret".
-- Alle Werte sind erfunden, nach dem Muster eines Forever-Charakters.
local MODE = MODE or "full"
OUT = {}
TIMERS = {}
FRAMES = {}
BUTTONS = {}
EDITBOXES = {}
CLOCK = 1794426840

local function noop() end
local Widget = {}
-- Unbekannte Methoden (gross geschrieben, wie in WoW) tun nichts; unbekannte
-- Felder sind nil wie bei echten Frames.
Widget.__index = function(t, k)
  local v = rawget(Widget, k)
  if v then return v end
  if type(k) == "string" and k:find("^%u") then return noop end
  return nil
end
local function widget(kind, name)
  local w = setmetatable({ kind = kind, scripts = {}, shown = true, text = "" }, Widget)
  if name then _G[name] = w end
  return w
end
function Widget:RegisterEvent(ev)
  if ev == "ADDON_RESTRICTION_STATE_CHANGED" and MODE == "minimal" then
    error("Attempt to register unknown event \"" .. ev .. "\"")
  end
  self.events = self.events or {}
  self.events[ev] = true
end
function Widget:SetScript(name, fn) self.scripts[name] = fn end
function Widget:GetScript(name) return self.scripts[name] end
function Widget:CreateFontString() return widget("FontString") end
function Widget:CreateTexture() return widget("Texture") end
function Widget:SetText(t) self.text = t end
function Widget:GetText() return self.text end
function Widget:Show() self.shown = true; if self.scripts.OnShow then self.scripts.OnShow(self) end end
function Widget:Hide() self.shown = false end
function Widget:IsShown() return self.shown end
function Widget:GetID() return 42 end

local MISSING_TEMPLATES = { BasicFrameTemplateWithInset = true, UIPanelButtonTemplate = true, InputBoxTemplate = true, UIPanelCloseButton = true }
function CreateFrame(kind, name, parent, template)
  if template and MODE == "minimal" and MISSING_TEMPLATES[template] then
    error("Couldn't find inherited node \"" .. template .. "\"")
  end
  local w = widget(kind, name)
  table.insert(FRAMES, w)
  if kind == "Button" then table.insert(BUTTONS, w) end
  if kind == "EditBox" then table.insert(EDITBOXES, w) end
  return w
end
UIParent = widget("Frame")
UISpecialFrames = {}
DEFAULT_CHAT_FRAME = widget("Frame")
function DEFAULT_CHAT_FRAME:AddMessage(m) table.insert(OUT, "CHAT:" .. m) end
GameTooltip = widget("GameTooltip")
function print(...) local t = {} for i = 1, select("#", ...) do t[i] = tostring(select(i, ...)) end table.insert(OUT, table.concat(t, " ")) end
SlashCmdList = {}
C_Timer = { After = function(s, fn) table.insert(TIMERS, fn) end }
function GetServerTime() return CLOCK end
time = os.time
date = os.date
function RunTimers() local n = 0 while #TIMERS > 0 and n < 50 do n = n + 1; local fn = table.remove(TIMERS, 1); fn() end end

-- Werte nach dem Muster eines Forever-Charakters (erfunden).
SECRET = setmetatable({}, { __tostring = function() return "SECRET" end })
function issecretvalue(v) return v == SECRET end
function GetBuildInfo() return "1.60.1", "69913", "Nov 1 2026", 16001 end
function GetLocale() return "deDE" end
function GetCurrentRegion() return 3 end
function GetCurrentRegionName() return "EU" end
function GetRealmName() return "Normal" end
function GetNormalizedRealmName() return "Normal" end
function UnitName() return "Mara Sturmwind" end
function UnitFullName() return "Mara Sturmwind", "Normal" end
function UnitNameUnmodified() return "Mara Sturmwind" end
function GetUnitName() return "Mara Sturmwind-Normal" end
function UnitPVPName() return "Mara Sturmwind" end
function UnitGUID() if MODE == "secret" then return SECRET end return "Player-4455-0A1B2C3D" end
function IsTrialAccount() return false end
function InCombatLockdown() return false end
C_AddOns = { GetAddOnMetadata = function(a, f) return "0.1.0" end, LoadAddOn = function(n)
  APIDocumentation = { systems = { { Name = "PlayerInfo", Namespace = "C_PlayerInfo", Functions = { { Name = "GetSurname", Returns = { { Name = "surname" } } } } } } }
  return true, nil end }
function LoggingChat(v) if v ~= nil then CHATLOG = v end return CHATLOG or false end
function UnitLevel() return 34 end
function UnitClass() return "Priester", "PRIEST", 5 end
function UnitRace() return "Himmelsgeborene", "Skyborne", 99 end
function UnitSex() return 3 end
function UnitFactionGroup() return "Alliance", "Allianz" end
function GetMaxPlayerLevel() return 60 end
function GetMoney() return 1834520 end
function UnitXP() return 21480 end
function UnitXPMax() return 38400 end
function GetXPExhaustion() return 12900 end
function GetRestState() return 1, "Ausgeruht", 2 end
function GetRealZoneText() return "Steinkrallengebirge" end
function GetZoneText() return "Steinkrallengebirge" end
function GetSubZoneText() return "Sonnenfels" end
function GetMinimapZoneText() return "Sonnenfels" end
function IsInInstance() return false, "none" end
function GetInstanceInfo() return "Kalimdor", "none", 0, "", 5, 0, false, 1, 0, nil end
C_Map = { GetBestMapForUnit = function() return 1442 end, GetMapInfo = function(id) return { mapID = id, name = "Steinkrallengebirge", mapType = 3, parentMapID = 1414 } end, GetPlayerMapPosition = function() return { x = 0.5, y = 0.6 } end }
function GetAverageItemLevel() return 31.4, 30.9, 30.9 end
function GetGuildInfo() return "Die Wanderer", "Mitglied", 4, nil end
function GetInventoryItemDurability(s) if s == 5 then return 31, 50 end if s == 7 then return 40, 40 end return nil end
C_Container = { GetContainerNumFreeSlots = function(b) return 7, 0 end, GetContainerNumSlots = function(b) return 16 end }
function GetNumSavedInstances() return 1 end
function GetSavedInstanceInfo(i) return "Ragefireabgrund", 123, 3600, 1, true, false, 0, false, 5, "Normal", 4, 2, false, 389 end
C_CurrencyInfo = { GetCurrencyListSize = function() return 2 end,
  GetCurrencyListInfo = function(i) return { name = i == 1 and "Allgemein" or "Vermächtnismarke", isHeader = i == 1, quantity = 12 } end,
  GetCurrencyListLink = function(i) if i == 2 then return "|Hcurrency:3001|h[x]|h" end end,
  GetCurrencyIDFromLink = function(l) return 3001 end }
C_QuestLog = { GetNumQuestLogEntries = function() return 14, 11 end }
C_DateAndTime = { GetSecondsUntilWeeklyReset = function() return 200000 end, GetSecondsUntilDailyReset = function() return 30000 end }
C_EncodingUtil = { SerializeJSON = function(t) return '{"zahl":1834520}' end, DeserializeJSON = function(s) return { zahl = 1834520 } end }
function RequestTimePlayed() end
function RequestRaidInfo() end
function ReloadUI() RELOADED = true end
Settings = { VarType = { Boolean = "boolean" },
  RegisterVerticalLayoutCategory = function(n) return widget("Category") end,
  RegisterAddOnSetting = function(...) return { args = { ... } } end,
  CreateCheckbox = function() end, RegisterAddOnCategory = function() end,
  OpenToCategory = function() OPENED = true end,
  SetOnValueChangedCallback = function(v, cb) SETTINGCB = cb end }
AddonCompartmentFrame = {}
WOW_PROJECT_ID = 19
WOW_PROJECT_MAINLINE = 1
WOW_PROJECT_CLASSIC = 2
WOW_PROJECT_FOREVER = 19
ChatFontNormal = "ChatFontNormal"

if MODE == "minimal" then
  GetCurrentRegion, GetCurrentRegionName, GetRealmID = nil, nil, nil
  C_EncodingUtil, Settings, C_Timer, UnitPVPName, issecretvalue = nil, nil, nil, nil, nil
  C_CurrencyInfo, GetNumSavedInstances, C_DateAndTime = nil, nil, nil
  C_AddOns.LoadAddOn = nil
  function GetMoney() error("boom") end
end

-- Serialisierung wie SavedVariables (nur Grundtypen); Fehler bei anderem.
function Serialize(v, indent)
  indent = indent or ""
  local t = type(v)
  if t == "string" then return string.format("%q", v) end
  if t == "number" or t == "boolean" then return tostring(v) end
  if t == "nil" then return "nil" end
  if t ~= "table" then error("nicht speicherbar: " .. t) end
  local parts = {}
  for k, val in pairs(v) do
    local key = type(k) == "string" and string.format("[%q]", k) or "[" .. tostring(k) .. "]"
    table.insert(parts, indent .. "  " .. key .. " = " .. Serialize(val, indent .. "  "))
  end
  table.sort(parts)
  return "{\n" .. table.concat(parts, ",\n") .. "\n" .. indent .. "}"
end
