# WoW Charakter

[![Erstellt mit Claude Code](https://img.shields.io/badge/erstellt%20mit-Claude%20Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)
[![KI-generiert](https://img.shields.io/badge/Code%20%26%20Doku-KI--generiert-6A2BB0)](#ki-hinweis)

Home-Assistant-Integration für World-of-Warcraft-Charaktere. Liest die Profildaten
über die offizielle Battle.net API. Version 0.3.2.

> **KI-Hinweis:** Dieses Projekt ist mit Claude Code entstanden. Code, Tests und
> Dokumentation wurden von der KI geschrieben und mit automatischen Tests sowie in
> einer echten Home-Assistant-Instanz geprüft; Details im Abschnitt
> [KI-Hinweis](#ki-hinweis).

## Aufbau

- **Haupteintrag „Battle.net API“**: Client-ID und Secret eines API-Clients, einmalig.
- **Untereintrag je Charakter**: Region, Spielversion, Realm und Name. Jeder Charakter
  ist ein eigenes Gerät mit eigenen Sensoren. Beliebig viele Charaktere je API-Client,
  auch aus verschiedenen Regionen und Spielversionen.

Fällt die Abfrage eines Charakters aus, sind nur seine Sensoren nicht verfügbar; die
anderen laufen weiter.

## Funktionsumfang

### Je Charakter

| Wert | Typ | Takt | Endpunkt, Feld |
|---|---|---|---|
| Level | Sensor | 15 min | Profil, `level` |
| Itemlevel (angelegt, Durchschnitt) | Sensoren | 15 min | Profil, `equipped_item_level`, `average_item_level` |
| Erfahrungspunkte | Sensor | 15 min | Profil, `experience` |
| Erfolgspunkte | Sensor | 15 min | Profil, `achievement_points` |
| Letzter Login | Zeitstempel | 15 min | Profil, `last_login_timestamp` |
| Mythic+-Wertung der aktuellen Season, Farbe und Season als Attribut | Sensor | 15 min | Mythic+-Profil, `current_mythic_rating` |
| Raid-Fortschritt LFR, Normal, Heroisch, Mythisch | Sensoren | 1 h | `encounters/raids`, neueste Erweiterung |
| Boss besiegt | Ereignis | 1 h | `encounters/raids`, `last_kill_timestamp` |
| Höchster Mythic+-Schlüssel, Läufe in Zeit | Sensoren | 1 h | `mythic-keystone-profile/season/{aktuelle Season}` |
| Ehrenstufe, ehrenhafte Siege | Sensoren | 1 h | `pvp-summary` |
| Leben, Primärwert, Krit, Tempo, Meisterschaft, Vielseitigkeit | Sensoren, **standardmäßig deaktiviert** | 1 h | `statistics` |
| Neuer Erfolg | Ereignis | 1 h | `achievements`, `recent_events` |
| Beruf (je Beruf) | Sensor | 6 h | `professions`, Skill der neuesten Stufe; Name aus `profession/{id}` |
| Reittiere, Haustiere, Spielzeuge | Sensoren | 6 h | `collections/*`, Anzahl |
| Avatar, Ganzkörperbild | Bilder | 6 h | `character-media` |

Klasse, Spezialisierung, Volk, Fraktion, Gilde, Realm und aktiver Titel stehen als
Attribute am Level-Sensor. Mythic+-Werte gibt es nur für Retail. Hat der Charakter in
der aktuellen Season noch nicht gespielt, ist die Mythic+-Wertung „unbekannt“.

Die Berufe-Seite eines Charakters liefert Namen auf Englisch, auch mit deutscher
Spracheinstellung. Die Integration schlägt die Namen deshalb einmalig in den
statischen Spieldaten nach; klappt das nicht, bleibt der englische Name. Raidnamen
kommen ebenfalls auf Englisch.

Ein Endpunkt wird nur abgefragt, wenn mindestens eine seiner Entitäten aktiviert ist.
Ereignisse lösen nur für Einträge aus, die nach dem Start von Home Assistant dazukommen.
Berufs-Sensoren entstehen aus der ersten Antwort; ein neu gelernter Beruf erscheint
nach dem nächsten Neuladen der Integration.

### Spielwelt (je Region, eigenes Gerät „WoW-Spielwelt EU“)

| Wert | Typ | Takt | Endpunkt, Feld |
|---|---|---|---|
| WoW-Marke | Sensor (Gold) | 1 h | `token/index`, `price` ÷ 10.000 |
| Wöchentlicher Reset | Zeitstempel | 1 h | `mythic-keystone/period/{aktuell}`, `end_timestamp` + 1 s |
| Server je Realm | Ein/Aus | 15 min | `connected-realm/{id}`, `status.type` |
| Warteschlange je Realm | Ein/Aus | 15 min | `connected-realm/{id}`, `has_queue` |
| Bevölkerung je Realm | Sensor | 15 min | `connected-realm/{id}`, `population.name` |

### WoW Forever

Für Forever-Charaktere legt die Integration nur Entitäten an, deren Endpunkt beim
Start Daten liefert.

### Diagnose

Einstellungen → Geräte & Dienste → WoW Charakter → ⋮ → **Diagnose herunterladen**
liefert die API-Antworten ohne Client-ID und Secret. Damit lassen sich Feldnamen
prüfen, wenn ein Wert fehlt.

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
- 0.3.x: 32 automatische Tests gegen Home Assistant 2026.2.3. 0.3.0 am 26.10.2026
  live mit zwei Retail-Charakteren geprüft: alle Entitäten angelegt, keine Fehler,
  Titel und Mythic+-Farbe an echten Antworten bestätigt. Erfahrungspunkte waren bei
  beiden 0 (Höchststufe beim letzten Login); das Verhalten beim Leveln ist ungeprüft.
  0.3.1 live geprüft: Die statischen Spieldaten liefern deutsche Berufsnamen, die
  Mythic+-Wertung ist ohne Lauf in der aktuellen Season „unbekannt“, die Diagnose
  schrumpfte von 119 KB auf 64 KB.
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

## KI-Hinweis

Dieses Projekt wurde mit [Claude Code](https://claude.com/claude-code) entwickelt,
einem KI-Assistenten von Anthropic. Recherche, Code, Tests und Dokumentation hat die
KI im Auftrag und unter Anleitung des Repo-Inhabers erstellt. Geprüft wurde so:

- automatische Tests (`pytest`, siehe Abschnitt „Tests“) und Code-Prüfung mit `ruff`
- Gegenproben mit absichtlich eingebauten Fehlern, um zu sehen, ob die Tests sie finden
- Betrieb in einer echten Home-Assistant-Instanz mit Abgleich gegen das Arsenal
  (Stand im Abschnitt „Teststand“)

Feldnamen der Battle.net API stammen aus öffentlichen Bibliotheken und dem Projekt
homeassistant-wow-blizzard, weil die offizielle Doku bei der Entwicklung nicht
erreichbar war. Nicht live geprüfte Punkte sind im Abschnitt „Teststand“ genannt.

## Lizenz

MIT, siehe `LICENSE`.
