# WoW Charakter

Home-Assistant-Integration für World-of-Warcraft-Charaktere. Liest die Profildaten
über die offizielle Battle.net API. Version 0.2.1.

## Aufbau

- **Haupteintrag „Battle.net API“**: Client-ID und Secret eines API-Clients, einmalig.
- **Untereintrag je Charakter**: Region, Spielversion, Realm und Name. Jeder Charakter
  ist ein eigenes Gerät mit eigenen Sensoren. Beliebig viele Charaktere je API-Client,
  auch aus verschiedenen Regionen und Spielversionen.

Fällt die Abfrage eines Charakters aus, sind nur seine Sensoren nicht verfügbar; die
anderen laufen weiter.

## Funktionsumfang

| Sensor | Retail | WoW Forever | Quelle (Feld der API) |
|---|---|---|---|
| Level | ja | ja | `level` |
| Itemlevel | ja | ja, falls die API ihn liefert | `equipped_item_level` |
| Erfolgspunkte | ja | ja, falls die API sie liefert | `achievement_points` |
| Letzter Login | ja | ja | `last_login_timestamp` (ms) |
| Mythic+-Wertung | ja | – (Sensor wird nicht angelegt) | `current_mythic_rating.rating` |

Klasse, Spezialisierung, Volk, Fraktion, Gilde und Realm stehen als Attribute am
Level-Sensor.

## Installation

1. Kostenlosen API-Client auf <https://develop.battle.net> anlegen, Client-ID und
   Secret notieren.
2. Über HACS: ⋮ → Benutzerdefinierte Repositories → `https://github.com/philf90/HA-WOW`,
   Typ „Integration“, dann „WoW Charakter“ herunterladen. Ohne HACS: Ordner
   `custom_components/wow_character` nach `config/custom_components/` kopieren.
   Danach Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → „WoW Charakter“:
   Client-ID und Secret eingeben.
4. Am Eintrag „Battle.net API“ **Charakter hinzufügen**:
   - Schritt 1: Region und Spielversion. Dabei wird die Realm-Liste geladen
     (`/data/wow/realm/index`).
   - Schritt 2: Realm aus der Liste wählen, Charakternamen eingeben.

Neues Secret: am Eintrag „Battle.net API“ ⋮ → **Neu konfigurieren**. Lehnt Blizzard
die Zugangsdaten ab, fragt Home Assistant von selbst nach neuen.

## Update von 0.1.x

Beim ersten Start übernimmt 0.2.0 die bisherigen Einträge (einer je Charakter)
automatisch: Einträge mit derselben Client-ID werden zu einem Eintrag „Battle.net API“
zusammengefasst, jeder Charakter wird ein Untereintrag. Geräte, Entitäts-IDs, eigene
Anpassungen und Verlauf bleiben erhalten.

**Vorher ein Backup anlegen.** Nach dem Umbau kann 0.1.x die Einträge nicht mehr
lesen; ein Zurückgehen geht nur über das Backup.

## Teststand

- 0.2.x: 20 automatische Tests gegen Home Assistant 2026.2.3, darunter die Übernahme
  von 0.1.x-Einträgen. Am 26.10.2026 live unter Home Assistant 2026.10.4 geprüft: Ein
  0.1.x-Eintrag wurde übernommen, Gerät, Entitäts-IDs und Werte blieben erhalten, der
  globale Token-Endpunkt liefert Daten. Ein zweiter Retail-Charakter wurde über
  „Charakter hinzufügen“ angelegt; die Werte beider Charaktere stimmen mit dem Arsenal
  überein, auch ein Charakter ohne Mythic+-Wertung. Erneutes Anmelden und der Ausfall
  einzelner Charaktere sind nur automatisch getestet.
- 0.1.x: am 26.10.2026 mit einem Retail-Charakter unter Home Assistant 2026.10.4 live
  geprüft: Realm-Liste, Profil, Mythic+-Profil und die Abfrage alle 15 Minuten.
- WoW Forever ist ungetestet.

Seit 0.2.0 holt die Integration das Token über den globalen Endpunkt
`https://oauth.battle.net/token` statt über einen Endpunkt je Region, wie die
Bibliotheken `@blizzard-api/core` und `blizzard.js`.

## WoW Forever

Blizzard hat den API-Namespace für Forever noch nicht dokumentiert (Start
04.11.2026). Beim Hinzufügen eines Forever-Charakters probiert die Integration die
Kandidaten aus `const.py` (`GAME_VERSIONS["forever"]["namespaces"]`) der Reihe nach:
Der erste, unter dem die API eine Realm-Liste liefert, wird gespeichert. Die
Kandidaten sind **unbestätigt**. Sobald Blizzard den Namespace nennt, dort eintragen;
schlägt das Hinzufügen fehl, ist das die wahrscheinlichste Ursache.

## Grenzen

- Profildaten aktualisiert Blizzard erst, wenn sich der Charakter ausloggt.
  Abfrage alle 15 Minuten.
- Die Region China wird nicht unterstützt.

## Tests

```bash
pip install pytest-homeassistant-custom-component==0.13.316
pytest tests   # pytest.ini setzt asyncio_mode = auto
```

## Lizenz

MIT, siehe `LICENSE`.
