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

# Ein Haupteintrag je API-Client, darunter ein Untereintrag je Charakter.
SUBENTRY_CHARACTER = "character"
MAIN_TITLE = "Battle.net API"

# Globaler Token-Endpunkt; das Token gilt fuer alle Regionen ausser China.
TOKEN_URL = "https://oauth.battle.net/token"

# Profildaten aktualisiert Blizzard erst nach dem Ausloggen; haeufiger
# abzufragen bringt nichts.
UPDATE_INTERVAL = timedelta(minutes=15)
# Takt fuer Detail-Endpunkte je Charakter und fuer die Spielwelt.
DETAIL_INTERVAL = timedelta(minutes=60)
WORLD_INTERVAL = timedelta(minutes=15)

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
}

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

# Namespaces: "dynamic{suffix}-{region}" fuer die Realm-Liste,
# "profile{suffix}-{region}" fuer Charaktere, z. B. "profile-eu".
# Bei mehreren Kandidaten wird beim Einrichten der Reihe nach probiert, welcher
# eine Realm-Liste liefert; der erste Treffer wird gespeichert.
GAME_VERSIONS = {
    "retail": {
        "namespaces": [""],
        "mythic_plus": True,
    },
    # WoW Forever startet am 04.11.2026. Blizzard hat den Namespace noch nicht
    # dokumentiert. Die Kandidaten stammen aus homeassistant-wow-blizzard und
    # sind NICHT bestaetigt; nach dem Start hier eintragen, was Blizzard nennt.
    "forever": {
        "namespaces": ["-forever", "-camelot"],
        "mythic_plus": False,
    },
}
