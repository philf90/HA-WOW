<p align="center">
  <img src="https://raw.githubusercontent.com/philf90/HA-WOW/main/assets/banner.png" alt="WoW Charakter – World of Warcraft für Home Assistant" width="100%">
</p>

# WoW Charakter

[![Erstellt mit Claude Code](https://img.shields.io/badge/erstellt%20mit-Claude%20Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)
[![KI-generiert](https://img.shields.io/badge/Code%20%26%20Doku-KI--generiert-6A2BB0)](#ki-hinweis)

Home-Assistant-Integration für World-of-Warcraft-Charaktere: Level, Itemlevel,
Ausrüstung, Raid- und Mythic+-Fortschritt, Berufe, Ruf, Erfolge und mehr als
Sensoren, dazu WoW-Marke, wöchentlicher Reset und Serverstatus. Die Daten kommen
aus der offiziellen Battle.net API. Version 0.8.0.

> **KI-Hinweis:** Dieses Projekt ist mit Claude Code entstanden. Code, Tests und
> Dokumentation wurden von der KI geschrieben und mit automatischen Tests sowie in
> einer echten Home-Assistant-Instanz geprüft; Details im Abschnitt
> [KI-Hinweis](#ki-hinweis).

## Voraussetzungen

- **Home Assistant 2026.2.3 oder neuer** (live geprüft mit 2026.10.4)
- **[HACS](https://hacs.xyz)** für die Installation per Klick (ohne HACS geht es
  auch, siehe unten)
- **Battle.net-API-Client** (kostenlos): Client-ID und Secret, angelegt mit einem
  Blizzard-Konto auf <https://develop.battle.net>
- Charaktere in den Regionen **EU, US, KR oder TW** (China wird nicht unterstützt)

## Installation

[![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=philf90&repository=HA-WOW&category=integration)
[![Integration hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=wow_character)

1. **API-Client anlegen:** auf <https://develop.battle.net> anmelden, einen Client
   erstellen, Client-ID und Secret notieren.
2. **Integration herunterladen:** Erste Schaltfläche oben → HACS fragt, ob das
   Repository hinzugefügt werden soll → **Hinzufügen** → **Herunterladen**.
   Von Hand: HACS → ⋮ → **Benutzerdefinierte Repositories** →
   `https://github.com/philf90/HA-WOW`, Typ „Integration“ → „WoW Charakter“
   herunterladen.
   Ohne HACS: Ordner `custom_components/wow_character` nach
   `config/custom_components/` kopieren.
3. **Home Assistant neu starten.**
4. **Einrichten:** Zweite Schaltfläche oben, oder Einstellungen → Geräte & Dienste
   → Integration hinzufügen → „WoW Charakter“. Client-ID und Secret eingeben.
5. **Charakter hinzufügen:** Am neuen Eintrag „Battle.net API“ →
   **Charakter hinzufügen**: zuerst Region und Spielversion, dann Realm aus der
   Liste wählen und Charakternamen eingeben. Für weitere Charaktere diesen Schritt
   wiederholen.

Danach ist jeder Charakter ein eigenes Gerät mit seinen Sensoren; die Werte für
Region und Realm stehen im Gerät „WoW-Spielwelt EU“ (bzw. US, KR, TW).

**Gut zu wissen:**

- Blizzard aktualisiert die Profildaten erst, wenn sich der Charakter im Spiel
  ausloggt.
- Einige Sensoren sind zunächst ausgeschaltet (Charakterwerte, Spielstatistik).
  Einschalten unter Einstellungen → Geräte & Dienste → WoW Charakter → Charakter
  → Entitäten.
- Passende Dashboard-Karten: siehe [Dashboard-Karten](#dashboard-karten).

## Inhalt

- [Aktualisieren](#aktualisieren)
- [Aufbau](#aufbau)
- [Entitäten je Charakter](#entitäten-je-charakter)
- [Entitäten der Spielwelt](#entitäten-der-spielwelt)
- [Attribute im Detail](#attribute-im-detail)
- [Abfragen und Takte](#abfragen-und-takte)
- [Dashboard-Karten](#dashboard-karten)
- [Ändern, Hinweise und Diagnose](#ändern-hinweise-und-diagnose)
- [WoW Forever](#wow-forever)
- [Grenzen](#grenzen)
- [Teststand](#teststand)
- [Tests](#tests)
- [KI-Hinweis](#ki-hinweis)
- [Lizenz](#lizenz)

## Aktualisieren

HACS zeigt neue Versionen als Update an. Nach dem Herunterladen Home Assistant
neu starten. Was sich je Version ändert, steht in den
[Release-Notes](https://github.com/philf90/HA-WOW/releases).

**Update von 0.1.x:** Beim ersten Start übernimmt die Integration (ab 0.2.0) die
bisherigen Einträge (einer je Charakter) automatisch: Einträge mit derselben
Client-ID werden zu einem Eintrag „Battle.net API“ zusammengefasst, jeder Charakter
wird ein Untereintrag. Geräte, Entitäts-IDs, eigene Anpassungen und Verlauf bleiben
erhalten. **Vorher ein Backup anlegen:** Nach dem Umbau kann 0.1.x die Einträge
nicht mehr lesen; zurück geht es nur über das Backup.

## Aufbau

- **Haupteintrag „Battle.net API“:** Client-ID und Secret eines API-Clients,
  einmalig.
- **Untereintrag je Charakter:** Region, Spielversion, Realm und Name. Jeder
  Charakter ist ein eigenes Gerät mit eigenen Entitäten. Beliebig viele Charaktere
  je API-Client, auch aus verschiedenen Regionen und Spielversionen.
- **Gerät „WoW-Spielwelt“ je Region:** WoW-Marke, Reset und Server der Realms, auf
  denen Charaktere angelegt sind.

Fällt die Abfrage eines Charakters aus, sind nur seine Entitäten nicht verfügbar;
die anderen laufen weiter.

## Entitäten je Charakter

| Wert | Typ | Takt | Quelle (Endpunkt, Feld) |
|---|---|---|---|
| **Profil** | | | |
| Level (Klasse, Spezialisierung, Volk, Fraktion, Gilde, Realm, Titel als Attribute) | Sensor | 15 min | Profil, `level` |
| Itemlevel (angelegt, Durchschnitt) | Sensoren | 15 min | Profil, `equipped_item_level`, `average_item_level` |
| Erfahrungspunkte | Sensor | 15 min | Profil, `experience` |
| Erfolgspunkte | Sensor | 15 min | Profil, `achievement_points` |
| Letzter Login | Zeitstempel | 15 min | Profil, `last_login_timestamp` |
| Avatar, Ganzkörperbild | Bilder | 6 h | `character-media` |
| Spezialisierung mit Heldentalenten und Talent-Code | Sensor | 1 h | `specializations` |
| Titel (Anzahl, Liste als Attribut) | Sensor | 6 h | `titles` |
| Level gestiegen | Ereignis | 15 min | Profil, `level` |
| Gilde (Mitglieder; Name, Erfolgspunkte, Aktivitäten als Attribute), nur in einer Gilde | Sensor | 6 h, Aktivitäten 1 h | `/data/wow/guild/{realm}/{gilde}` und `…/activity` |
| **Ausrüstung** | | | |
| Ausrüstung, 18 Plätze (Kopf bis Schildhand) | Sensoren, Itemlevel; Symbol als Bild | 1 h | `equipment`; Symbol aus `media/item/{id}` |
| Leere Sockel, Verzauberungen, Set-Fortschritt | Sensoren | 1 h | `equipment`, ausgewertet |
| Leben, Primärwert, Krit, Tempo, Meisterschaft, Vielseitigkeit | Sensoren, **zunächst aus** | 1 h | `statistics` |
| **Fortschritt** | | | |
| Raid-Fortschritt LFR, Normal, Heroisch, Mythisch | Sensoren | 1 h | `encounters/raids`, neueste Erweiterung |
| Boss besiegt | Ereignis | 1 h | `encounters/raids`, `last_kill_timestamp` |
| Mythic+-Wertung der aktuellen Season (Farbe, Season, `api_rating` als Attribute) | Sensor | 15 min | Mythic+-Profil, `current_mythic_rating` |
| Höchster Mythic+-Schlüssel (beste Läufe als Attribut), Läufe in Zeit | Sensoren | 1 h | `mythic-keystone-profile/season/{aktuelle Season}` |
| Ehrenstufe, ehrenhafte Siege | Sensoren | 1 h | `pvp-summary` |
| Beruf (je Beruf, Stufe als Attribut) | Sensor | 6 h | `professions`; Namen aus `profession/{id}` |
| Ruf (Anzahl der Fraktionen, je Fraktion Stufe und Fortschritt als Attribut) | Sensor | 6 h | `reputations` |
| **Erfolge und Sammlungen** | | | |
| Erfolge (Anzahl, Punkte je Hauptkategorie als Attribut) | Sensor | 1 h | `achievements`; Kategorien aus `achievement-category/index` |
| Neuer Erfolg | Ereignis | 1 h | `achievements`, `recent_events` |
| Reittiere, Haustiere, Spielzeuge | Sensoren | 6 h | `collections/*`, Anzahl |
| Neu gesammelt (Reittier, Haustier, Spielzeug, Titel) | Ereignis | 6 h | `collections/*`, `titles`, Vergleich zweier Abfragen |
| Abgeschlossene Quests | Sensor | 6 h | `quests/completed`, Anzahl |
| Spielstatistik (Werte des Statistik-Fensters) | Sensor, **zunächst aus** | 6 h | `achievements/statistics` |

Mythic+-Werte gibt es nur für Retail. Hat der Charakter in der aktuellen Season
noch nicht gespielt, ist die Mythic+-Wertung „unbekannt“; das Attribut
`api_rating` enthält den Wert der API ohne diese Prüfung, wie ihn das Arsenal im
Kopf der Charakterseite zeigt.

## Entitäten der Spielwelt

Je Region ein Gerät „WoW-Spielwelt EU“ (bzw. US, KR, TW):

| Wert | Typ | Takt | Quelle (Endpunkt, Feld) |
|---|---|---|---|
| WoW-Marke | Sensor (Gold) | 1 h | `token/index`, `price` ÷ 10.000 |
| Wöchentlicher Reset | Zeitstempel | 1 h | `mythic-keystone/period/{aktuell}`, `end_timestamp` + 1 s |
| Server je Realm | Ein/Aus | 15 min | `connected-realm/{id}`, `status.type` |
| Warteschlange je Realm | Ein/Aus | 15 min | `connected-realm/{id}`, `has_queue` |
| Bevölkerung je Realm | Sensor | 15 min | `connected-realm/{id}`, `population.name` |

## Attribute im Detail

### Ausrüstung

Die Ausrüstungs-Sensoren gibt es für alle Plätze, auch leere, damit Karten feste
Entitäten haben. Attribute: `name`, `item_id`, `quality` (z. B. `EPIC`),
`quality_name`, `enchantments`, `sockets` (je Sockel `type` und `gem`, leer ohne
Edelstein), `set` und `tooltip`. Das Symbol schlägt die Integration einmal je Item
nach.

`tooltip` enthält die Zeilen des Item-Tooltips im Spiel, fertig übersetzt: Stufe,
Bindung, Platz und Art, Rüstung bzw. Waffenschaden, Werte (`stats` mit `text`,
`color` und `bonus` für Zweitwerte), Verzauberungen, Sockel, Effekte, Set mit
Teilen und Boni (je Bonus `active` und `required`), Haltbarkeit, Anforderungen und
Verkaufspreis. Leere Angaben fehlen. Steuerzeichen des Spiels (z. B. `|A:…|a`)
entfernt die Integration.

Auswertungen der Ausrüstung, ohne zusätzliche Abfrage:

- **Leere Sockel:** Anzahl der Sockel ohne Edelstein; `sockets` nennt je Sockel
  Platz (`slot`, `slot_name`) und Sockelart (`type`).
- **Verzauberungen:** Anzahl der verzauberten Plätze; `slots` nennt je Platz die
  Verzauberungen. Welche Plätze verzauberbar sind, liefert die API nicht; eine
  fehlende Verzauberung lässt sich daraus also nicht ableiten.
- **Set-Fortschritt:** angelegte Teile des vollständigsten Sets; `name`, `total`,
  `items` (mit `equipped`) und `effects` (mit `active` und `required`, der Anzahl
  Teile). Ohne Set ist der Wert 0; weitere Sets stehen in `other_sets`.

### Ruf

`factions` folgt der Reihenfolge der API, ohne Gruppierung nach Erweiterung. Jeder
Eintrag hat `faction`, `faction_id`, `standing`, `value` und `max`, bei Bedarf
`renown` und `paragon`. Die ID braucht es, weil Namen nicht eindeutig sind: Die API
liefert z. B. zwei Fraktionen „Bilgewasserkartell“.

### Erfolge, Titel, Spielstatistik

- **Erfolge:** `total_points` und `categories` (je Hauptkategorie `category`,
  `id`, `quantity`, `points`). Die Antwort der API mischt Haupt- und
  Unterkategorien und nennt sie auf Englisch; die Integration schlägt deshalb
  einmalig die Hauptkategorien in den statischen Spieldaten nach und nimmt deren
  Namen. Klappt das nicht, stehen alle Kategorien der Antwort drin.
- **Titel:** `active` und `titles` (Namen).
- **Spielstatistik:** `statistics` mit `id`, `name`, `category` (bei
  Unterkategorien „Kategorie / Unterkategorie“) und `quantity`. Einzelne Werte
  lassen sich in Karten oder Templates über die `id` auswählen, z. B. 98 (Quests
  abgeschlossen) oder 60 (Tode insgesamt).

### Ereignisse

Ereignisse lösen nur für Neues seit dem Start von Home Assistant aus.

- **Boss besiegt:** `boss`, `raid`, `difficulty`, `timestamp`.
- **Neuer Erfolg:** `achievement`, `id`, `timestamp`, `icon` (Symbol des Erfolgs).
- **Neu gesammelt:** Ereignistyp `mount`, `pet`, `toy` oder `title`, dazu `name`
  und `id`. Die Integration vergleicht die Sammlungen zweier Abfragen (alle 6 h).
  Reittiere und Spielzeuge gelten für den ganzen Account; sind mehrere
  Charaktere eingerichtet, meldet jeder sie einmal.
- **Level gestiegen:** `level` und `previous`.

Kommen in einer Abfrage mehrere neue Einträge, löst jeder ein eigenes Ereignis aus.

### Gilde

Den Sensor gibt es nur für Charaktere, die beim Start von Home Assistant in einer
Gilde sind. Zustand ist die Zahl der Mitglieder; Attribute `name`, `realm`,
`faction`, `achievement_points`, `created` und `activities` (die zehn neuesten
Einträge: Erfolge von Mitgliedern mit `character` und `achievement`, Bosskills
mit `boss` und `difficulty`, je mit `type` und `timestamp`).

### Symbole für Karten

Aus den statischen Spieldaten, je Objekt einmal nachgeschlagen:

- Level-Sensor: `class_icon` und `spec_icon`.
- Beruf: Symbol des Berufs als Bild der Entität.
- Raid-Fortschritt: `images` mit einem Bild je Raid.
- Ereignis „Neuer Erfolg“: `icon`.

### Spezialisierung und Mythic+

- **Spezialisierung:** Zustand ist die aktive Spezialisierung; `id`,
  `hero_talents` (aktiver Heldentalentbaum), `loadout_code` (Talent-Code des
  aktiven Loadouts zum Importieren im Spiel) und `specializations` (alle der
  Klasse).
- **Mythic+-Läufe:** Der Sensor „Höchster Mythic+-Schlüssel“ hat `best_runs`
  (Kurzform je Dungeon) und `runs`: je Lauf `dungeon`, `dungeon_id`, `level`,
  `timed`, `duration` (Sekunden), `completed`, `rating`, `color`, `affixes` und
  `members` (Name, Realm, Spezialisierung, Itemlevel). Die Einheit von `duration`
  in der API ist nicht belegt; die Integration erkennt Sekunden und Millisekunden
  an der Größe.

### Sprache

Texte kommen in der Sprache der Region (EU: Deutsch). Ausnahmen: Die Berufe-Seite
und die Erfolge-Seite eines Charakters liefern Namen auf Englisch, auch mit
deutscher Spracheinstellung. Die Integration schlägt Berufe, Berufsstufen und
Erfolgskategorien deshalb einmalig in den statischen Spieldaten nach; klappt das
nicht, bleibt der englische Name. Raidnamen kommen weiterhin auf Englisch.

### Nicht in der Datenbank

Lange Attribute speichert Home Assistant nicht im Verlauf: `tooltip`, `factions`,
`runs`, `titles`, `statistics` und `activities`. Die Werte stehen trotzdem im aktuellen Zustand.

## Abfragen und Takte

- Ein Endpunkt wird nur abgefragt, wenn mindestens eine seiner Entitäten
  aktiviert ist.
- Ereignisse lösen nur für Einträge aus, die nach dem Start von Home Assistant
  dazukommen.
- Berufs-Sensoren entstehen aus der ersten Antwort; ein neu gelernter Beruf
  erscheint nach dem nächsten Neuladen der Integration.
- Das Token holt die Integration über den globalen Endpunkt
  `https://oauth.battle.net/token` (seit 0.2.0), wie die Bibliotheken
  `@blizzard-api/core` und `blizzard.js`.
- Einmal am Tag je Charakter der Status-Endpunkt (`…/status`, Feld `is_valid`),
  siehe [Ändern, Hinweise und Diagnose](#ändern-hinweise-und-diagnose).
- Spielwelt: WoW-Marke, Reset, Season und jeder Realm werden einzeln abgefragt.
  Fällt eine Abfrage aus, behält ihr Wert den letzten Stand; nicht verfügbar wird
  die Spielwelt erst, wenn alle ausfallen.
- Die Realm-Liste beim Hinzufügen zeigt keine internen Realms von Blizzard (z. B.
  „EU1A Account Realm“, „EU4A1-INST“, „RDB EU“).

## Dashboard-Karten

Karten im Owlet-Stil für diese Integration liegen im Repository
[philf90/home-assistant](https://github.com/philf90/home-assistant) unter
`dashboard/sonstiges/`: die Arsenal-Karte (`wow-arsenal-karte.yaml` mit
`wow-templates.yaml`) und acht einzeln nutzbare Karten (`wow-*-karte.yaml`) für
Charaktere, Spielwelt, Raids, Mythic+, Berufe, Ruf, Sammlungen und Werte.
Alle brauchen `custom:button-card`; weitere Voraussetzungen (z. B. browser_mod
für das Arsenal-Popup) stehen im Kopf jeder Datei.

## Ändern, Hinweise und Diagnose

- **Neues Secret:** am Eintrag „Battle.net API“ ⋮ → **Neu konfigurieren**. Lehnt
  Blizzard die Zugangsdaten ab, fragt Home Assistant von selbst nach neuen.
- **Charakter umbenannt oder transferiert:** am Charakter unter dem Eintrag
  „Battle.net API“ ⋮ → **Neu konfigurieren**, dann Realm und Namen ändern. Gerät,
  Entitäts-IDs und Verlauf bleiben; die Entitäts-IDs tragen weiter den alten
  Namen. Region und Spielversion lassen sich nicht ändern, dafür den Charakter
  neu hinzufügen.
- **Reparaturhinweise** (Einstellungen → System → Reparaturen): Die Integration
  vergleicht bei jeder Profilabfrage die Charakter-ID mit der gespeicherten und
  fragt einmal am Tag den Status-Endpunkt, ob das Profil noch gültig ist. So
  empfiehlt es Blizzard. Einen Hinweis gibt es, wenn
  - der Charakter dreimal in Folge (etwa 45 Minuten) nicht gefunden wird,
  - unter dem Namen jetzt ein anderer Charakter steht (andere ID) oder
  - Blizzard das Profil als ungültig meldet.

  In den letzten beiden Fällen zeigen die Entitäten keine Werte, bis du über
  **Neu konfigurieren** bestätigst. Der Hinweis verschwindet von selbst, sobald
  alles wieder passt.
- **Nicht mehr benötigte Geräte:** Das Gerät eines Charakters entfernt Home
  Assistant mit dem Charakter. Spielwelt-Geräte und Realm-Entitäten ohne
  Charakter entfernt die Integration beim nächsten Start. Übrig gebliebene
  Geräte lassen sich auf ihrer Geräteseite löschen.
- **Diagnose:** Einstellungen → Geräte & Dienste → WoW Charakter → ⋮ →
  **Diagnose herunterladen** liefert die API-Antworten ohne Client-ID und Secret.
  Damit lassen sich Feldnamen prüfen, wenn ein Wert fehlt.

## WoW Forever

Blizzard hat den API-Namespace für Forever noch nicht dokumentiert (Start
04.11.2026). Beim Hinzufügen eines Forever-Charakters probiert die Integration die
Kandidaten aus `const.py` (`GAME_VERSIONS["forever"]["namespaces"]`) der Reihe nach:
Der erste, unter dem die API eine Realm-Liste liefert, wird gespeichert. Die
Kandidaten sind **unbestätigt**. Sobald Blizzard den Namespace nennt, dort
eintragen; schlägt das Hinzufügen fehl, ist das die wahrscheinlichste Ursache.

Für Forever-Charaktere legt die Integration nur Entitäten an, deren Endpunkt beim
Start Daten liefert.

## Grenzen

- Profildaten aktualisiert Blizzard erst, wenn sich der Charakter ausloggt.
- Die Region China wird nicht unterstützt.
- Gold, Position und Account-Daten liefert die API nur mit einer Anmeldung des
  Spielers (Authorization Code Flow, Scope `wow.profile`). Die Integration nutzt
  nur Client-ID und Secret und kann sie deshalb nicht abfragen.
- Große Schatzkammer und Affixe der aktuellen Woche liefert die API nicht: Sie
  kennt je Season nur den besten Lauf je Dungeon, und die Woche hat nur Start und
  Ende.
- WoW Forever ist ungetestet.
- Das Logo zeigt Home Assistant ab 2026.3 aus dem Ordner `brand/` der
  Integration. In der HACS-Liste erscheint stattdessen ein Platzhalter: HACS 2.0.5
  lädt Symbole nur von `brands.home-assistant.io`, und dort nimmt Home Assistant
  keine neuen Custom-Integrationen mehr auf. Das betrifft jede neue
  Custom-Integration und lässt sich in diesem Repo nicht beheben.

## Teststand

Automatische Tests laufen gegen Home Assistant 2026.2.3; live geprüft wurde unter
Home Assistant 2026.10.4 mit Retail-Charakteren der Region EU.

- **0.8.x:** 84 automatische Tests, hassfest ohne Fehler. Die Live-Prüfung steht
  noch aus.
- **0.7.x:** 71 automatische Tests, hassfest ohne Fehler. 0.7.0 am 27.10.2026
  über HACS installiert und live geprüft: keine Meldung der Integration im Log,
  kein Reparaturhinweis, keine Entität nicht verfügbar; alle fünf
  Spielwelt-Entitäten blieben erhalten. Am Charakter wird „Neu konfigurieren“
  angeboten, der Dialog lädt die Realm-Liste und füllt Realm und Namen vor;
  Geräte lassen sich löschen. Den Charakter-Eintrag hat die Integration 10 s
  nach dem Start geschrieben, wie beim Nachtragen der ID erwartet; die ID selbst
  ist von außen nicht auslesbar. Nicht live geprüft: die Reparaturhinweise (kein
  Charakter umbenannt), das Speichern über „Neu konfigurieren“ und die
  Darstellung der Symbole.
- **0.6.x:** 52 automatische Tests. 0.6.0 am 26.10.2026 über HACS installiert und
  live geprüft: keine Fehler, alle neuen Entitäten angelegt. Leere Sockel (3),
  Verzauberungen (2) und Set (3/5, ein Bonus aktiv) stimmen mit dem Arsenal
  überein; Spezialisierung mit Heldentalentbaum und Talent-Code, 55 Titel,
  276 Statistik-Werte und Berufsstufen auf Deutsch. Gefunden: Die
  Erfolgskategorien kamen gemischt und auf Englisch. 0.6.1 behebt das, live
  geprüft: 15 Hauptkategorien mit deutschen Namen bei zwei Charakteren; beim
  ersten ergeben ihre Summen genau die Erfolgspunkte des Profils (16.045) und die
  Anzahl der Erfolge (1.753). Ungeprüft sind die Laufdetails (`runs`), weil kein Charakter in
  der aktuellen Season einen Lauf hat.
- **0.5.x:** 40 automatische Tests. 0.5.0 live geprüft: Die Tooltip-Felder kommen
  an und stimmen mit dem Tooltip im Spiel überein.
- **0.4.x:** 38 automatische Tests. 0.4.0 live geprüft: keine Fehler, je
  Charakter 18 Ausrüstungs-Sensoren und ein Ruf-Sensor (75 bzw. 74 Fraktionen).
  Feldnamen und Platz-Bezeichner stimmen mit den echten Antworten überein. Name,
  Itemlevel, Verzauberung und Sockel der 12 im Arsenal lesbaren Plätze stimmen
  überein, ebenso der Wert 170 aus `api_rating`. Item-Symbole, Set-Namen,
  Renommee und Paragon kommen an.
- **0.3.x:** 32 automatische Tests. 0.3.0 live geprüft: alle Entitäten angelegt,
  keine Fehler, Titel und Mythic+-Farbe an echten Antworten bestätigt.
  Erfahrungspunkte waren bei beiden 0 (Höchststufe beim letzten Login); das
  Verhalten beim Leveln ist ungeprüft. 0.3.1: Die statischen Spieldaten liefern
  deutsche Berufsnamen, die Mythic+-Wertung ist ohne Lauf in der aktuellen Season
  „unbekannt“. Avatar und Ganzkörperbild werden in Home Assistant angezeigt.
- **0.2.x:** 20 automatische Tests, darunter die Übernahme von 0.1.x-Einträgen.
  Live: Ein 0.1.x-Eintrag wurde übernommen, Gerät, Entitäts-IDs und Werte blieben
  erhalten, der globale Token-Endpunkt liefert Daten; ein zweiter Charakter wurde
  über „Charakter hinzufügen“ angelegt, die Werte beider Charaktere stimmen mit
  dem Arsenal überein. Erneutes Anmelden und der Ausfall einzelner Charaktere sind
  nur automatisch getestet.
- **0.1.x:** live geprüft: Realm-Liste, Profil, Mythic+-Profil und die Abfrage
  alle 15 Minuten.
- **WoW Forever** ist ungetestet.

## Tests

```bash
pip install pytest-homeassistant-custom-component==0.13.316 ruff==0.16.9
ruff check . && ruff format --check .
pytest tests   # pytest.ini setzt asyncio_mode = auto
```

Dieselben Schritte laufen bei jedem Push und Pull Request im Workflow
„Pruefung“, zusammen mit hassfest und der HACS-Prüfung.

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
