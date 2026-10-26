# WoW Charakter

[![Erstellt mit Claude Code](https://img.shields.io/badge/erstellt%20mit-Claude%20Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)
[![KI-generiert](https://img.shields.io/badge/Code%20%26%20Doku-KI--generiert-6A2BB0)](#ki-hinweis)

Home-Assistant-Integration für World-of-Warcraft-Charaktere. Liest die Profildaten
über die offizielle Battle.net API. Version 0.5.0.

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
| Ausrüstung, 18 Plätze (Kopf bis Schildhand) | Sensoren, Itemlevel; Symbol als Bild | 1 h | `equipment`; Symbol aus `media/item/{id}` |
| Ruf: Anzahl der Fraktionen, je Fraktion Stufe und Fortschritt als Attribut | Sensor | 6 h | `reputations` |

Klasse, Spezialisierung, Volk, Fraktion, Gilde, Realm und aktiver Titel stehen als
Attribute am Level-Sensor. Mythic+-Werte gibt es nur für Retail. Hat der Charakter in
der aktuellen Season noch nicht gespielt, ist die Mythic+-Wertung „unbekannt“. Das
Attribut `api_rating` enthält den Wert der API ohne diese Prüfung; diesen Wert zeigt
auch das Arsenal im Kopf der Charakterseite.

Die Ausrüstungs-Sensoren gibt es für alle Plätze, auch leere, damit Karten feste
Entitäten haben. Attribute: `name`, `item_id`, `quality` (z. B. `EPIC`),
`quality_name`, `enchantments`, `sockets`, `set` und `tooltip`. Das Symbol
schlägt die Integration einmal je Item nach. `tooltip` enthält die Zeilen des
Item-Tooltips im Spiel, fertig übersetzt: Stufe, Bindung, Platz und Art,
Rüstung bzw. Waffenschaden, Werte (`stats` mit `text`, `color` und `bonus` für
Zweitwerte), Verzauberungen, Sockel, Effekte, Set mit Teilen und Boni,
Haltbarkeit, Anforderungen und Verkaufspreis. Leere Angaben fehlen. Wie die
Fraktionsliste wird `tooltip` nicht in der Datenbank gespeichert. Die Fraktionsliste des Ruf-Sensors kann sehr lang
sein und wird deshalb nicht in der Datenbank gespeichert; sie folgt der Reihenfolge
der API, ohne Gruppierung nach Erweiterung. Jeder Eintrag hat `faction`, `faction_id`,
`standing`, `value` und `max`, bei Bedarf `renown` und `paragon`. Die ID braucht es,
weil Namen nicht eindeutig sind: Die API liefert z. B. zwei Fraktionen
„Bilgewasserkartell“.

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
  schrumpfte von 119 KB auf 64 KB. 0.3.2 (nur README) über HACS ohne Fehler
  installiert; Avatar und Ganzkörperbild werden in Home Assistant angezeigt.
- 0.5.x: 40 automatische Tests gegen Home Assistant 2026.2.3. Die Inhalte der
  Tooltip-Felder sind live noch ungeprüft.
- 0.4.x: 38 automatische Tests gegen Home Assistant 2026.2.3. 0.4.0 am 26.10.2026
  über HACS installiert und live mit zwei Retail-Charakteren geprüft: keine Fehler,
  je Charakter 18 Ausrüstungs-Sensoren und ein Ruf-Sensor (75 bzw. 74 Fraktionen).
  Feldnamen und Platz-Bezeichner stimmen mit den echten Antworten überein. Name,
  Itemlevel, Verzauberung und Sockel der 12 im Arsenal lesbaren Plätze stimmen
  überein, ebenso der Wert 170 aus `api_rating`. Die API liefert Verzauberungstexte
  mit Steuerzeichen wie `|A:…|a`; die Integration entfernt sie. Item-Symbole,
  Set-Namen, Renommee und Paragon kommen an.
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

Feldnamen der Battle.net API stammen aus öffentlichen Bibliotheken, dem Projekt
homeassistant-wow-blizzard und dem Arsenal-Import von SimulationCraft. Die offizielle
Doku war bis 0.3.x nicht erreichbar; sie nennt Endpunkte und Parameter, aber keine
Antwortfelder. Nicht live geprüfte Punkte sind im Abschnitt „Teststand“ genannt.

## Lizenz

MIT, siehe `LICENSE`.
