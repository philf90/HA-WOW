"""Konstanten fuer die Integration WoW Charakter."""

from datetime import timedelta

DOMAIN = "wow_character"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_REGION = "region"
CONF_GAME_VERSION = "game_version"
# Slug aus der Realm-Liste der API, z. B. "die-aldor".
CONF_REALM = "realm"
CONF_CHARACTER = "character"
# Wird beim Einrichten ermittelt und gespeichert, z. B. "" (Retail) oder "-forever".
CONF_NAMESPACE_SUFFIX = "namespace_suffix"
# ID des Charakters bei Blizzard. Blizzard empfiehlt, sie zu speichern und mit
# der Antwort zu vergleichen: Weicht sie ab, traegt jetzt ein anderer Charakter
# diesen Namen (z. B. nach Umbenennung oder Transfer).
CONF_CHARACTER_ID = "character_id"

# Ein Haupteintrag je API-Client, darunter ein Untereintrag je Charakter.
SUBENTRY_CHARACTER = "character"
MAIN_TITLE = "Battle.net API"

# Globaler Token-Endpunkt; das Token gilt fuer alle Regionen ausser China.
TOKEN_URL = "https://oauth.battle.net/token"
# Battle.net-Login (Authorization Code Flow, Blizzard-Doku "Using OAuth").
# Der Scope gibt die Charakterliste des Kontos frei (/profile/user/wow).
# Blizzard liefert dazu kein Refresh-Token, auch nicht mit offline_access
# (getestet 29.10.2026); das Login-Token dient nur der Suche nach Charakteren
# und wird nicht gespeichert.
AUTHORIZE_URL = "https://oauth.battle.net/authorize"
LOGIN_SCOPE = "wow.profile"
# Feld der Auswahlliste nach dem Login.
CONF_CHARACTERS = "characters"

# Takt der Spielwelt (Realms, WoW-Marke, Reset). Die Takte der Charaktere
# stehen in INTERVAL_OPTIONS.
WORLD_INTERVAL = timedelta(minutes=15)
# Abstand der Pruefung ueber den Status-Endpunkt (is_valid und ID).
STATUS_INTERVAL = timedelta(hours=24)
# Erst nach so vielen 404 in Folge gilt ein Charakter als nicht gefunden
# (bei 15 Minuten Takt etwa 45 Minuten), damit kurze API-Aussetzer keinen
# Reparaturhinweis ausloesen.
NOT_FOUND_LIMIT = 3

# Detail-Endpunkte je Charakter: Unterseite und Mindestabstand in Minuten.
# Ein Endpunkt wird nur abgefragt, wenn mindestens eine seiner Entitaeten
# aktiviert ist (oder noch gar nicht angelegt wurde).
DETAIL_ENDPOINTS: dict[str, tuple[str, int]] = {
    "raids": ("encounters/raids", 60),
    "mythic_season": ("mythic-keystone-profile/season/{season}", 60),
    "pvp": ("pvp-summary", 60),
    "statistics": ("statistics", 60),
    "achievements": ("achievements", 60),
    "professions": ("professions", 360),
    "mounts": ("collections/mounts", 360),
    "pets": ("collections/pets", 360),
    "toys": ("collections/toys", 360),
    "media": ("character-media", 360),
    "equipment": ("equipment", 60),
    "reputations": ("reputations", 360),
    "specializations": ("specializations", 60),
    "titles": ("titles", 360),
    # Statistik-Fenster des Spiels; grosse Antwort, deshalb selten.
    "game_statistics": ("achievements/statistics", 360),
    # Liste aller abgeschlossenen Quests; grosse Antwort, deshalb selten.
    "quests": ("quests/completed", 360),
    # Gilde des Charakters; {guild} steht fuer "<realm>/<gilde>" aus dem Profil.
    # Ohne Gilde wird nichts abgefragt.
    "guild": ("{guild}", 360),
    "guild_activity": ("{guild}/activity", 60),
    # Mitgliederliste der Gilde; Klassen nur als ID, Namen aus playable-class.
    "guild_roster": ("{guild}/roster", 360),
    # Aussehen: Geschlecht und Transmog als Attribute am Level-Sensor.
    "appearance": ("appearance", 360),
    # Wertung je PvP-Bracket; {bracket} aus PVP_BRACKETS, je Bracket eine Abfrage.
    "pvp_brackets": ("pvp-bracket/{bracket}", 60),
    # Nur Jaeger; fuer andere Klassen meldet die API laut Doku 404.
    "hunter_pets": ("hunter-pets", 360),
}
# Mindestabstand in Minuten fuer Endpunkte ohne Entitaet (z. B. Berufe ohne
# Beruf, PvP-Brackets ohne Wertung, Erfolge in Classic Era) und fuer die
# WoW-Marke ohne Sensor: Liefern sie spaeter Daten, entsteht die Entitaet ohne
# Neuladen. Endpunkte, deren Entitaeten alle deaktiviert sind, bleiben aus.
# Vorgabe; die Option "Seltene Details" aendert ihn (seit 0.20.0).
DISCOVERY_MINUTES = 360

# Takte als Optionen des Haupteintrags (seit 0.20.0), in Minuten: Vorgabe,
# kleinster und groesster Wert. Profil: Blizzard aktualisiert es erst nach dem
# Ausloggen, haeufiger als alle 15 Minuten bringt selten etwas. "detail" gilt
# fuer die Endpunkte, die
# DETAIL_ENDPOINTS mit 60 Minuten fuehrt, "rare" fuer die mit 360 Minuten und
# fuer Endpunkte ohne Entitaet.
CONF_PROFILE_MINUTES = "profile_minutes"
CONF_DETAIL_MINUTES = "detail_minutes"
CONF_RARE_MINUTES = "rare_minutes"
INTERVAL_OPTIONS: dict[str, tuple[int, int, int]] = {
    CONF_PROFILE_MINUTES: (15, 5, 120),
    CONF_DETAIL_MINUTES: (60, 15, 720),
    CONF_RARE_MINUTES: (DISCOVERY_MINUTES, 60, 1440),
}
# Abschaltbare Gruppen von Detail-Endpunkten. Ausgeschaltet: keine Abfrage
# und keine Entitaeten dieser Endpunkte; vorhandene bleiben in der Registry
# (Entitaets-ID, Verlauf) und kommen beim Einschalten zurueck.
CONF_DISABLED_GROUPS = "disabled_groups"
ENDPOINT_GROUPS: dict[str, tuple[str, ...]] = {
    "guild": ("guild", "guild_activity", "guild_roster"),
    # Titel gehoeren zum Ereignis "Neu gesammelt".
    "collections": ("mounts", "pets", "toys", "titles"),
    "achievements": ("achievements",),
    "game_statistics": ("game_statistics",),
    "quests": ("quests",),
    "reputations": ("reputations",),
    "professions": ("professions",),
    "raids": ("raids",),
    "pvp": ("pvp", "pvp_brackets"),
}
# Endpunkte, bei denen ein 404 laut Blizzard-Doku etwas Dauerhaftes ueber den
# Charakter sagt. hunter-pets: "If the character is a hunter, returns a summary
# of the character's hunter pets. Otherwise, returns an HTTP 404 Not Found
# error." Die Klasse aendert sich nie; nach dem ersten 404 wird der Endpunkt bis
# zum Neuladen nicht mehr abgefragt. Eine Klassen-ID nennt die Doku nicht.
NOT_FOUND_IS_FINAL = ("hunter_pets",)

# Bracket-Bezeichner fuer pvp-bracket/{bracket}, nur belegte: "3v3" ist das
# Beispiel der Classic-Doku, "2v2", "3v3" und "rbg" nennen die Typdefinitionen
# von @blizzard-api/wow 4.1.4. Sensoren entstehen nur fuer Brackets, die beim
# Start Daten liefern.
PVP_BRACKETS = ("2v2", "3v3", "rbg")

# Ausruestungsplaetze in der Reihenfolge des Arsenals (links, rechts, Waffen).
# Bezeichner wie im Feld "slot.type" der Ausruestungs-Seite; dieselbe Liste
# nutzt der Arsenal-Import von SimulationCraft.
EQUIPMENT_SLOTS = (
    "HEAD",
    "NECK",
    "SHOULDER",
    "BACK",
    "CHEST",
    "SHIRT",
    "TABARD",
    "WRIST",
    "HANDS",
    "WAIST",
    "LEGS",
    "FEET",
    "FINGER_1",
    "FINGER_2",
    "TRINKET_1",
    "TRINKET_2",
    "MAIN_HAND",
    "OFF_HAND",
)
REQUEST_TIMEOUT = 15

# Sprache der Texte aus der API (Option am Haupteintrag). "region": je Region
# die Sprache aus REGIONS wie vor 0.19.0; "home_assistant": die Sprache von
# Home Assistant; sonst eine Sprache aus LANGUAGES.
CONF_LANGUAGE = "language"
LANGUAGE_REGION = "region"
LANGUAGE_HOME_ASSISTANT = "home_assistant"
# Sprache -> Locale je Region. Nur Locales, die sowohl @blizzard-api/core 4.2.0
# (_regionLocaleMap) als auch blizzard.js 5.0.0 (endpoints) fuer die Region
# nennen (geprueft 29.10.2026). pt_PT fuer EU nennt nur blizzard.js und fehlt
# deshalb. Kennt eine Region die Sprache nicht, gilt die Sprache der Region.
LANGUAGES: dict[str, dict[str, str]] = {
    "de": {"eu": "de_DE"},
    "en": {"eu": "en_GB", "us": "en_US", "kr": "en_US", "tw": "en_US"},
    "es": {"eu": "es_ES", "us": "es_MX"},
    "fr": {"eu": "fr_FR"},
    "it": {"eu": "it_IT"},
    "pt": {"us": "pt_BR"},
    "ru": {"eu": "ru_RU"},
    "ko": {"kr": "ko_KR"},
    "zh": {"tw": "zh_TW"},
}

REGIONS = {
    "eu": {
        "api": "https://eu.api.blizzard.com",
        "locale": "de_DE",
    },
    "us": {
        "api": "https://us.api.blizzard.com",
        "locale": "en_US",
    },
    "kr": {
        "api": "https://kr.api.blizzard.com",
        "locale": "ko_KR",
    },
    "tw": {
        "api": "https://tw.api.blizzard.com",
        "locale": "zh_TW",
    },
}

# Detail-Endpunkte, die Blizzard fuer die Profil-API von WoW Classic nennt
# (Doku "World of Warcraft Classic Profile APIs", Stand 28.10.2026). Raids,
# Mythic+, Berufe, Sammlungen, Ruf, Titel und Quests fehlen dort.
CLASSIC_ENDPOINTS = (
    "pvp",
    "statistics",
    "achievements",
    "media",
    "equipment",
    "specializations",
    "game_statistics",
    "guild",
    "guild_activity",
    "guild_roster",
    "hunter_pets",
    "appearance",
    "pvp_brackets",
)
# Statische Spieldaten, die die Integration nachschlaegt und die Blizzard fuer
# Classic nennt (Doku "World of Warcraft Classic Game Data APIs");
# playable-class liefert die Klassennamen der Gildenmitglieder, item die Namen
# der Transmog-Gegenstaende. Symbole von
# Spezialisierungen, Berufen, Raids und Erfolgen sowie Erfolgskategorien
# fehlen dort.
CLASSIC_STATIC = ("media/playable-class", "media/item", "playable-class", "item")

# Namespaces: "dynamic{suffix}-{region}" fuer die Realm-Liste,
# "profile{suffix}-{region}" fuer Charaktere, z. B. "profile-eu".
# Bei mehreren Kandidaten wird beim Einrichten der Reihe nach probiert, welcher
# eine Realm-Liste liefert; der erste Treffer wird gespeichert.
# label: Zusatz im Namen des Spielwelt-Geraets, z. B. "WoW-Spielwelt EU Forever".
# endpoints/static: was die Version kennt; None heisst ohne Einschraenkung.
GAME_VERSIONS = {
    "retail": {
        "namespaces": [""],
        "mythic_plus": True,
        "label": "",
        "endpoints": None,
        "static": None,
    },
    # WoW Forever startet am 04.11.2026. Blizzard hat den Namespace noch nicht
    # dokumentiert. Die Kandidaten stammen aus homeassistant-wow-blizzard und
    # sind NICHT bestaetigt; nach dem Start hier eintragen, was Blizzard nennt.
    "forever": {
        "namespaces": ["-forever", "-camelot"],
        "mythic_plus": False,
        "label": " Forever",
        "endpoints": None,
        "static": None,
    },
    # Classic: Namespaces laut Blizzard-Doku "World of Warcraft Classic
    # Namespaces" (Stand 28.10.2026). Die Erweiterung hinter Progression und
    # Anniversary wechselt mit der Zeit, der Namespace bleibt.
    "classic_era": {
        "namespaces": ["-classic1x"],
        "mythic_plus": False,
        "label": " Classic Era",
        "endpoints": CLASSIC_ENDPOINTS,
        "static": CLASSIC_STATIC,
    },
    "classic_progression": {
        "namespaces": ["-classic"],
        "mythic_plus": False,
        "label": " Classic Progression",
        "endpoints": CLASSIC_ENDPOINTS,
        "static": CLASSIC_STATIC,
    },
    "classic_anniversary": {
        "namespaces": ["-classicann"],
        "mythic_plus": False,
        "label": " Classic Anniversary",
        "endpoints": CLASSIC_ENDPOINTS,
        "static": CLASSIC_STATIC,
    },
}
