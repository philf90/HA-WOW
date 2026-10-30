<p align="center">
  <img src="https://raw.githubusercontent.com/philf90/HA-WOW/main/assets/banner.png" alt="WoW Charakter – World of Warcraft für Home Assistant" width="100%">
</p>

# WoW Charakter

[![Erstellt mit Claude Code](https://img.shields.io/badge/erstellt%20mit-Claude%20Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)
[![KI-generiert](https://img.shields.io/badge/Code%20%26%20Doku-KI--generiert-6A2BB0)](#ki-hinweis)

Home-Assistant-Integration für World-of-Warcraft-Charaktere: Level, Itemlevel,
Ausrüstung, Raid- und Mythic+-Fortschritt, Berufe, Ruf, Erfolge und mehr als
Sensoren, dazu WoW-Marke, wöchentlicher Reset und Serverstatus. Die Daten kommen
aus der offiziellen Battle.net API. Unterstützt Retail, WoW Classic (Era,
Progression, Anniversary) und ist für WoW Forever vorbereitet. Version 0.22.0.

Zwei Dashboard-Karten liefert die Integration selbst mit: „WoW Arsenal“
(`custom:wow-arsenal-card`) und „WoW Talentbaum“ (`custom:wow-talent-tree-card`,
Retail), ohne zusätzliche HACS-Karten oder Dashboard-Ressourcen.

<p align="center">
  <img src="https://raw.githubusercontent.com/philf90/HA-WOW/main/assets/vorschau-karten.png" alt="Arsenal-, Charaktere-, Berufe- und Raid-Karte im Nachtblau-Stil mit Beispieldaten" width="100%">
</p>
<p align="center"><sub>Arsenal, Charaktere, Berufe und Raids · Beispieldaten</sub></p>

> **KI-Hinweis:** Dieses Projekt ist mit Claude Code entstanden. Code, Tests und
> Dokumentation wurden von der KI geschrieben und mit automatischen Tests sowie in
> einer echten Home-Assistant-Instanz geprüft; Details im Abschnitt
> [KI-Hinweis](#ki-hinweis).

## Voraussetzungen

- **Home Assistant 2026.2.3 oder neuer** (live geprüft mit 2026.10.4)
- **[HACS](https://hacs.xyz)** für die Installation per Klick (ohne HACS geht es
  auch, siehe unten)
- **Battle.net-API-Client** (kostenlos): Client-ID und Secret, angelegt mit einem
  Blizzard-Konto auf <https://develop.battle.net>. Blizzard verlangt dafür einen
  Authenticator (Zwei-Faktor-Anmeldung) am Konto. Für die Suche nach Charakteren
  per Battle.net-Anmeldung zusätzlich die Redirect-URL
  `https://my.home-assistant.io/redirect/oauth` im Client (seit 0.17.0), siehe
  [API-Client anlegen](#api-client-anlegen)
- **My Home Assistant** (Teil von `default_config`, also meist schon aktiv) für
  die Battle.net-Anmeldung; ohne siehe
  [Ohne My Home Assistant](#ohne-my-home-assistant)
- Charaktere in den Regionen **EU, US, KR oder TW** (China wird nicht unterstützt)

## Installation

[![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=philf90&repository=HA-WOW&category=integration)
[![Integration hinzufügen](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=wow_character)

1. **API-Client anlegen:** auf <https://develop.battle.net> einen Client
   erstellen, mit der Redirect-URL `https://my.home-assistant.io/redirect/oauth`;
   Schritt für Schritt unter [API-Client anlegen](#api-client-anlegen).
2. **Integration herunterladen:** Erste Schaltfläche oben → HACS fragt, ob das
   Repository hinzugefügt werden soll → **Hinzufügen** → **Herunterladen**.
   Von Hand: HACS → ⋮ → **Benutzerdefinierte Repositories** →
   `https://github.com/philf90/HA-WOW`, Typ „Integration“ → „WoW Charakter“
   herunterladen.
   Ohne HACS: Ordner `custom_components/wow_character` nach
   `config/custom_components/` kopieren.
3. **Home Assistant neu starten.**
4. **Einrichten:** Zweite Schaltfläche oben, oder Einstellungen → Geräte & Dienste
   → Integration hinzufügen → „WoW Charakter“. Client-ID und Secret eingeben;
   die Integration prüft sie sofort bei Blizzard.
5. **Charaktere wählen**, eine von zwei Möglichkeiten:
   - **Mit Battle.net anmelden und Charaktere wählen** (seit 0.17.0): Ein
     Fenster mit der Battle.net-Anmeldung öffnet sich. Anmelden und den Zugriff
     auf die World-of-Warcraft-Charaktere erlauben. Das Fenster schließt sich,
     und Home Assistant zeigt alle Charaktere des Kontos aus EU, US, KR und TW
     und allen Spielversionen, nach Level sortiert. Die gewünschten ankreuzen und
     **Absenden**. Beim ersten Mal fragt My Home Assistant nach der Adresse deiner
     Instanz. Details und Fehlerbilder unter
     [Battle.net-Anmeldung](#battlenet-anmeldung-seit-0170).
   - **Ohne Anmeldung fortfahren:** Der Eintrag entsteht ohne Charaktere. Diese
     dann am Eintrag „Battle.net API“ über **Charakter hinzufügen** anlegen,
     per Battle.net-Anmeldung oder **Von Hand eingeben**: zuerst Region und
     Spielversion (Retail, Classic Era, Classic Progression, Classic
     Anniversary oder Forever), dann Realm aus der Liste wählen und
     Charakternamen eingeben. Von Hand geht auch für Charaktere anderer Konten.

Danach ist jeder Charakter ein eigenes Gerät mit seinen Sensoren; die Werte für
Region und Realm stehen im Gerät „WoW-Spielwelt EU“ (bzw. US, KR, TW).

### API-Client anlegen

Laut Blizzard („Getting Started“) braucht das Battle.net-Konto einen
Authenticator, und die Blizzard Developer API Terms of Use müssen akzeptiert
sein. Dann:

1. <https://develop.battle.net> öffnen, anmelden, oben **API Access** →
   **Create New Client**.
2. Die Felder ausfüllen:

   | Feld | Eintrag |
   |---|---|
   | Client Name | frei wählbar, muss bei Blizzard weltweit eindeutig sein, z. B. „Home Assistant WoW“ mit einem eigenen Zusatz |
   | Redirect URIs | `https://my.home-assistant.io/redirect/oauth`, zeichengenau: `https`, kein `/` am Ende. Ohne My Home Assistant siehe [unten](#ohne-my-home-assistant) |
   | Service URL | Kästchen für „keine Service-URL“ ankreuzen |
   | Intended Use | kurz beschreiben, z. B. „Home Assistant integration for my own World of Warcraft characters“ |

3. **Create**. In der Übersicht des Clients (**Manage Client**) stehen Client-ID
   und Client-Secret.

Das Secret gehört nur in Home Assistant: nicht weitergeben, nicht in Screenshots
oder Foren zeigen (Nutzungsbedingungen, Abschnitt 2(l)). Ist es doch
sichtbar geworden: **Generate New Secret**, für das alte eine kurze Ablauffrist
wählen und das neue in Home Assistant eintragen (siehe
[Ändern, Hinweise und Diagnose](#ändern-hinweise-und-diagnose)). Ein bestehender
Client ohne Redirect-URL lässt sich unter **Manage Client** ergänzen.

**Gut zu wissen:**

- Blizzard aktualisiert die Profildaten erst, wenn sich der Charakter im Spiel
  ausloggt.
- Einige Sensoren sind zunächst ausgeschaltet (Charakterwerte, Spielstatistik).
  Einschalten unter Einstellungen → Geräte & Dienste → WoW Charakter → Charakter
  → Entitäten.
- Dashboard-Karten: mitgeliefert sind
  [„WoW Arsenal“](#karte-wow-arsenal-seit-0150) und
  [„WoW Talentbaum“](#karte-wow-talentbaum-seit-0140); weitere Karten als YAML
  siehe [Dashboard-Karten](#dashboard-karten).

## Inhalt

- [Aktualisieren](#aktualisieren)
- [Battle.net-Anmeldung](#battlenet-anmeldung-seit-0170)
- [Aufbau](#aufbau)
- [Entitäten je Charakter](#entitäten-je-charakter)
- [Entitäten der Spielwelt](#entitäten-der-spielwelt)
- [Attribute im Detail](#attribute-im-detail)
- [Abfragen und Takte](#abfragen-und-takte)
- [Aktionen](#aktionen-seit-0210)
- [Dashboard-Karten](#dashboard-karten)
- [Ändern, Hinweise und Diagnose](#ändern-hinweise-und-diagnose)
- [WoW Classic](#wow-classic)
- [WoW Forever](#wow-forever)
- [Grenzen](#grenzen)
- [Teststand](#teststand)
- [Tests](#tests)
- [KI-Hinweis](#ki-hinweis)
- [Lizenz](#lizenz)

## Aktualisieren

HACS zeigt neue Versionen als Update an. Nach dem Herunterladen Home Assistant
neu starten. Wer von Hand aktualisiert, ersetzt den ganzen Ordner
`custom_components/wow_character` samt `translations/`; sonst fehlen neue Texte,
z. B. die Einträge im Menü „Charakter hinzufügen“. Was sich je Version ändert, steht in den
[Release-Notes](https://github.com/philf90/HA-WOW/releases).

**Update auf 0.22.0:** keine Migration, Entitäts-IDs bleiben. Geändert:
Der Sensor „Bevölkerung“ hat jetzt feste Zustände (`full`, `high`, `medium`,
`low`, `recommended`), die Home Assistant in der eigenen Sprache anzeigt;
vorher stand dort der Text der API (z. B. „Voll“). Automationen, die auf den
alten Text prüfen, brauchen den neuen Zustand; ältere Werte im Verlauf bleiben
als Text stehen. Das Attribut `best_runs` zeigt nur noch die Stufe („+12“), ob
in Zeit, steht in `runs` (`timed`). Das Gerätemodell heißt „World of Warcraft“
bzw. „World of Warcraft Classic Era“ statt „World of Warcraft (retail)“. Die
Diagnose enthält keine Namen anderer Spieler mehr.

**Update auf 0.21.1:** keine Migration, nur eine Korrektur für die Aktion
`wow_character.refresh` mit Gerät: Sie nutzte eine Angabe am Gerät, die Home
Assistant 2026.10 als veraltet meldet und die ab 2027.10 entfällt.

**Update auf 0.21.0:** keine Migration. Neu sind die Aktionen
`wow_character.refresh` und `wow_character.get_character` (siehe
[Aktionen](#aktionen-seit-0210)). 0.21.0 enthält auch 0.19.1 und 0.20.0, die
nicht als eigene Releases erschienen sind. Zurück auf 0.19.0 geht ohne Backup;
Automationen mit den neuen Aktionen schlagen dort fehl.

**Update auf 0.20.0:** keine Migration. Neu sind im Optionsdialog die Takte
(Profil, Details, seltene Details) und abschaltbare Gruppen (siehe
[Takte und Gruppen](#takte-und-gruppen-seit-0200)); ohne Änderung bleibt
alles wie bisher. Zurück auf 0.19.x geht ohne Backup; die neuen Optionen
ignoriert 0.19.x.

**Update auf 0.19.1:** keine Migration, nur Fehlerkorrekturen bei
Störungen der Battle.net API (siehe [Abfragen und Takte](#abfragen-und-takte)).

**Update auf 0.19.0:** keine Migration. Neu ist die Option „Sprache der
API-Texte“ am Eintrag „Battle.net API“ (siehe [Sprache](#sprache)); ohne
Änderung bleibt alles in der Sprache der Region wie bisher. Zurück auf 0.18.x
geht ohne Backup; eine gewählte Sprache ignoriert 0.18.x.

**Update auf 0.18.0:** keine Migration. Neue Entitäten entstehen jetzt ohne
Neuladen, sobald die API Daten dafür liefert, z. B. ein neu gelernter Beruf, die
erste Wertung in einem PvP-Bracket oder der Beitritt zu einer Gilde (siehe
[Abfragen und Takte](#abfragen-und-takte)). Dafür fragt die Integration
Endpunkte ohne Entität alle 6 Stunden ab, statt gar nicht mehr. Zurück auf
0.17.x geht ohne Backup.

**Update auf 0.17.2:** keine Migration, nur Fehlerkorrekturen. Wer unter
0.17.1 oder früher die Client-ID gewechselt hat, hat die Spielwelt-Entitäten
doppelt (die neuen mit der Endung `_2`); die alten stehen als „nicht mehr
bereitgestellt“ in der Entitätenliste und lassen sich dort löschen.

**Update auf 0.17.1:** keine Migration. Einträge, Geräte, Entitäts-IDs,
Verlauf und Abfragen bleiben, wie sie sind; das Speicherformat ist unverändert,
zurück auf 0.16.x geht deshalb ohne Backup. Neu ist nur, was du nutzen kannst:

1. Im Blizzard-Client unter **Manage Client** die Redirect-URL
   `https://my.home-assistant.io/redirect/oauth` ergänzen und speichern.
2. Am Eintrag „Battle.net API“ → **Charakter hinzufügen** → **Mit Battle.net
   anmelden und Charaktere wählen**, anmelden und die noch fehlenden
   Charaktere ankreuzen. Bereits eingerichtete erscheinen nicht in der Liste.

„Charakter hinzufügen“ ist seit 0.17.1 ein Menü; das bisherige Formular steht
dort unter **Von Hand eingeben**. „Neu konfigurieren“ ist ebenfalls ein Menü:
**Charaktere abgleichen** (derselbe Ablauf) oder **Client-ID oder Secret
ändern**.

**Update von 0.1.x:** Beim ersten Start übernimmt die Integration (ab 0.2.0) die
bisherigen Einträge (einer je Charakter) automatisch: Einträge mit derselben
Client-ID werden zu einem Eintrag „Battle.net API“ zusammengefasst, jeder Charakter
wird ein Untereintrag. Geräte, Entitäts-IDs, eigene Anpassungen und Verlauf bleiben
erhalten. **Vorher ein Backup anlegen:** Nach dem Umbau kann 0.1.x die Einträge
nicht mehr lesen; zurück geht es nur über das Backup.

## Battle.net-Anmeldung (seit 0.17.0)

Die Anmeldung dient nur dazu, die Charaktere des Kontos zu finden. Alle
laufenden Abfragen nutzen weiter Client-ID und Secret.

**Neue Charaktere abgleichen:**

1. Einstellungen → Geräte & Dienste → WoW Charakter → **Charakter
   hinzufügen** → **Mit Battle.net anmelden und Charaktere wählen**. Derselbe
   Ablauf steht auch am Eintrag „Battle.net API“ ⋮ → **Neu konfigurieren** →
   **Charaktere abgleichen**.
2. Im geöffneten Fenster bei Battle.net anmelden und den Zugriff auf die
   World-of-Warcraft-Charaktere erlauben.
3. Die Liste zeigt nur Charaktere, die noch nicht eingerichtet sind. Ankreuzen,
   **Absenden**. Die Meldung nennt die Zahl der neuen Charaktere; der Eintrag lädt
   neu und legt ihre Geräte an.

Neue Charaktere findet die Integration nicht von selbst, weil sie das Login-Token
nicht behält (siehe unten). Nach einem neuen Charakter im Spiel: einmal ausloggen
(Blizzard aktualisiert Profildaten erst dann), dann abgleichen.

**Einzelheiten:**

- **Wo:** beim Einrichten nach Client-ID und Secret, später über
  **Charakter hinzufügen** oder am Eintrag „Battle.net API“ ⋮ → **Neu
  konfigurieren** → **Charaktere abgleichen**. Die Liste bietet nur Charaktere
  an, die noch nicht eingerichtet sind; ein eingerichteter Charakter wird an
  seiner ID erkannt, ältere Einträge ohne ID am Namen. Ein umbenannter
  Charakter erscheint deshalb nicht doppelt.
- **Hilfsdialog:** Nach der Anmeldung setzt Home Assistant über
  `/auth/external/callback` nur Dialoge des Haupteintrags fort, nicht den
  Dialog „Charakter hinzufügen“. Dafür startet die Integration im Hintergrund
  einen Hilfsdialog am Haupteintrag, der den Rücksprung annimmt und
  weitergibt (seit 0.17.1). Er läuft mit der Quelle „user“ und erscheint
  deshalb nicht unter „Entdeckt“; schließt du „Charakter hinzufügen“, endet er
  mit.
- **Redirect-URL:** Blizzard leitet nach der Anmeldung nur an eine Adresse
  zurück, die im API-Client eingetragen ist; sonst zeigt Blizzard „400 –
  Umleitungs-URL ist nicht gültig“. Mit My Home Assistant (Teil von
  `default_config`) ist das `https://my.home-assistant.io/redirect/oauth`, ohne
  `<Adresse von Home Assistant>/auth/external/callback`, laut Blizzard-Doku nur
  mit HTTPS. Der Anmeldeschritt zeigt die benutzte Adresse an.
- **Was Blizzard liefert:** Scope `wow.profile`, Endpunkt `/profile/user/wow`
  („Account Profile Summary“) je Region und Spielversion: 4 Regionen × 6
  Namespaces (Forever mit zwei Kandidaten) = höchstens 24 Abfragen je Suche,
  parallel. HTTP 404 heißt „kein Konto dort“; HTTP 403 kam im Live-Test für
  die Forever-Kandidaten, die Blizzard noch nicht kennt, und zählt ebenfalls
  nicht als Fehlabfrage (seit 0.17.1). Je Charakter nutzt die
  Integration Name, ID, Level, Klasse und Realm (Name und Slug).
- **Was gespeichert wird:** nur die Untereinträge der gewählten Charaktere, mit
  denselben Daten und Entitäts-IDs wie von Hand angelegt. Das Login-Token nicht:
  Es gilt 24 Stunden, und ein Refresh-Token gibt Blizzard nicht aus (getestet am
  29.10.2026, auch mit dem Scope `offline_access`). Neue Charaktere kommen über
  einen neuen Abgleich mit erneuter Anmeldung dazu.
- **Erneut anmelden (Reauth):** wie bisher nur, wenn Blizzard Client-ID oder
  Secret ablehnt. Die Battle.net-Anmeldung löst nie eine erneute Anmeldung aus;
  ein neues Passwort oder eine entzogene Freigabe ändert am Betrieb nichts.
- **Fehler** brechen nur den Dialog ab, der Eintrag läuft weiter: Anmeldung
  abgelehnt, Freigabe für die WoW-Charaktere abgewählt, Code-Tausch abgelehnt,
  keine Charaktere gefunden. Schlagen einzelne Abfragen fehl, nennt die
  Auswahlliste ihre Zahl; dort fehlen dann eventuell Charaktere.

**Fehlerbilder:**

| Was du siehst | Ursache | Abhilfe |
|---|---|---|
| Blizzard-Seite „400 – Ungültiger Authorisierungscode oder Umleitungs-URL ist nicht gültig“ | Redirect-URL fehlt im Client oder weicht ab (z. B. `/` am Ende) | Unter **Manage Client** die Adresse eintragen, die der Anmeldeschritt in Home Assistant anzeigt; Fenster schließen, Abgleich neu starten |
| Seite „Invalid state. Is My Home Assistant configured to go to the right instance?“ | My Home Assistant leitet an eine andere Instanz weiter, als der Dialog läuft | Auf <https://my.home-assistant.io> die Adresse der richtigen Instanz einstellen, Abgleich neu starten |
| „Home Assistant konnte seine eigene Adresse für die Anmeldung nicht ermitteln“ | My Home Assistant ist nicht aktiv, und die Oberfläche nennt keine Adresse | `my:` oder `default_config:` in `configuration.yaml`, oder [Ohne My Home Assistant](#ohne-my-home-assistant) |
| „Der Zugriff auf deine World-of-Warcraft-Charaktere wurde nicht erlaubt“ | Freigabe bei Battle.net abgewählt | Erneut abgleichen und die Freigabe erteilen |
| „Battle.net hat die Anmeldung abgelehnt“ | Code-Tausch abgelehnt, z. B. Code schon verwendet (er gilt nur einmal) oder Secret nicht mehr gültig | Erneut versuchen; sonst Client-ID, Secret und Redirect-URL prüfen |
| „Alle Charaktere dieses Kontos sind bereits eingerichtet“ | nichts Neues auf dem Konto | Neuer Charakter? Einmal im Spiel ausloggen, dann erneut abgleichen |
| „Keine Charaktere gefunden“ | Konto ohne WoW-Charaktere in EU, US, KR, TW | Anderes Konto? Bei Battle.net abmelden und mit dem richtigen anmelden |

Die Freigabe für den Client lässt sich in den Einstellungen des Battle.net-Kontos
wieder entziehen; die Integration läuft danach unverändert weiter.

### Ohne My Home Assistant

Ohne My Home Assistant nutzt Home Assistant als Rücksprung
`<Adresse von Home Assistant>/auth/external/callback`, mit der Adresse, unter
der du die Oberfläche gerade geöffnet hast. Diese Adresse muss als Redirect-URL
im Blizzard-Client stehen, und laut Blizzard-Doku muss sie mit `https://`
beginnen. Eine Adresse wie `http://homeassistant.local:8123` nimmt Blizzard
damit nicht an. Der Anmeldeschritt zeigt die genutzte Adresse an. Ohne
HTTPS-Adresse bleibt das Anlegen von Hand.

## Aufbau

- **Haupteintrag „Battle.net API“:** Client-ID und Secret eines API-Clients,
  einmalig.
- **Untereintrag je Charakter:** Region, Spielversion, Realm und Name. Jeder
  Charakter ist ein eigenes Gerät mit eigenen Entitäten. Beliebig viele Charaktere
  je API-Client, auch aus verschiedenen Regionen und Spielversionen.
- **Gerät „WoW-Spielwelt“ je Region:** WoW-Marke, Reset und Server der Realms, auf
  denen Charaktere angelegt sind.

Fällt die Abfrage eines Charakters aus, sind nur seine Entitäten nicht verfügbar;
die anderen laufen weiter. Bekommt die Integration beim Start kein Token (kein
Netz, Blizzard gestört), wiederholt Home Assistant den Start selbst, statt ohne
Daten zu starten (seit 0.17.2); sonst fehlten Entitäten, die nur aus der ersten
Antwort entstehen. Scheitert nur das Mythic+-Profil, bleiben die übrigen
Profilwerte verfügbar und die Wertung behält ihren letzten Stand (seit 0.17.2).

## Entitäten je Charakter

Die Takte in den Tabellen sind die Vorgaben; seit 0.20.0 lassen sie sich
ändern (siehe [Takte und Gruppen](#takte-und-gruppen-seit-0200)).

| Wert | Typ | Takt | Quelle (Endpunkt, Feld) |
|---|---|---|---|
| **Profil** | | | |
| Level (Klasse, Spezialisierung, Volk, Fraktion, Gilde, Realm, Titel als Attribute) | Sensor | 15 min | Profil, `level` |
| Geschlecht und Transmog (Attribute am Level-Sensor) | Attribute | 6 h | `appearance` |
| Itemlevel (angelegt, Durchschnitt) | Sensoren | 15 min | Profil, `equipped_item_level`, `average_item_level` |
| Erfahrungspunkte | Sensor | 15 min | Profil, `experience` |
| Erfolgspunkte | Sensor | 15 min | Profil, `achievement_points` |
| Letzter Login | Zeitstempel | 15 min | Profil, `last_login_timestamp` |
| Avatar, Ganzkörperbild | Bilder | 6 h | `character-media` |
| Spezialisierung mit Heldentalenten und Talent-Code | Sensor | 1 h | `specializations` |
| Talente (Baum mit den meisten Punkten; Punkte und Talente je Baum), nur außerhalb von Retail | Sensor | 1 h | `specializations` |
| Talentbaum (Spezialisierung; Knoten von Klassen-, Spezialisierungs- und aktivem Heldenbaum als Attribute), Retail | Sensor | 1 h | `specializations`; Baum aus `talent-tree/{id}/playable-specialization/{specId}`, Symbole aus `media/spell/{id}` |
| Titel (Anzahl, Liste als Attribut) | Sensor | 6 h | `titles` |
| Level gestiegen | Ereignis | 15 min | Profil, `level` |
| Gilde (Mitglieder; Name, Erfolgspunkte, Aktivitäten und Mitgliederliste als Attribute), nur in einer Gilde | Sensor | 6 h, Aktivitäten 1 h | `/data/wow/guild/{realm}/{gilde}`, `…/activity` und `…/roster`; Klassennamen aus `playable-class/{id}` |
| Jägerbegleiter (Anzahl; beschworener, aktive und alle Begleiter als Attribute), nur für Jäger | Sensor | 6 h; für Nicht-Jäger einmal je Start | `hunter-pets` |
| **Ausrüstung** | | | |
| Ausrüstung, 18 Plätze (Kopf bis Schildhand) | Sensoren, Itemlevel (ohne Itemlevel außerhalb von Retail der Name des Items); Symbol als Bild | 1 h | `equipment`; Symbol aus `media/item/{id}` |
| Leere Sockel, Verzauberungen, Set-Fortschritt | Sensoren | 1 h | `equipment`, ausgewertet |
| Leben, Primärwert, Krit, Tempo, Meisterschaft, Vielseitigkeit | Sensoren, **zunächst aus** | 1 h | `statistics` |
| **Fortschritt** | | | |
| Raid-Fortschritt LFR, Normal, Heroisch, Mythisch | Sensoren | 1 h | `encounters/raids`, neueste Erweiterung |
| Boss besiegt | Ereignis | 1 h | `encounters/raids`, `last_kill_timestamp` |
| Mythic+-Wertung der aktuellen Season (Farbe, Season, `api_rating` als Attribute) | Sensor | 15 min | Mythic+-Profil, `current_mythic_rating` |
| Höchster Mythic+-Schlüssel (beste Läufe als Attribut), Läufe in Zeit | Sensoren | 1 h | `mythic-keystone-profile/season/{aktuelle Season}` |
| Ehrenstufe, ehrenhafte Siege | Sensoren | 1 h | `pvp-summary` |
| PvP-Wertung je Bracket (2v2, 3v3, RBG), nur Brackets mit Daten | Sensoren | 1 h; Brackets ohne Sensor 6 h | `pvp-bracket/{bracket}` |
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
| Bevölkerung je Realm | Sensor | 15 min | `connected-realm/{id}`, `population.type` (seit 0.22.0; vorher `population.name`) |

## Attribute im Detail

### Ausrüstung

Die Ausrüstungs-Sensoren gibt es für alle Plätze, auch leere, damit Karten feste
Entitäten haben. Zustand ist das Itemlevel. Classic Era nennt je Item kein
Itemlevel; außerhalb von Retail zeigt der Sensor dann den Namen des Items (seit
0.11.3), leere Plätze bleiben „unbekannt“. Attribute: `name`, `item_id`, `quality` (z. B. `EPIC`),
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

Den Sensor gibt es nur für Charaktere in einer Gilde; tritt ein Charakter später
einer bei, entsteht er mit der nächsten Profilabfrage (seit 0.18.0, vorher erst
nach dem Neuladen), die Werte folgen mit der nächsten Detailabfrage.
Zustand ist die Zahl der Mitglieder; Attribute `name`, `realm`,
`faction`, `achievement_points`, `created`, `activities` (die zehn neuesten
Einträge: Erfolge von Mitgliedern mit `character` und `achievement`, Bosskills
mit `boss` und `difficulty`, je mit `type` und `timestamp`) und `members` (seit
0.11.0): je Mitglied `name`, `level`, `class`, `class_id` und `rank`, sortiert
nach Rang (0 zuerst) und Name. Die Mitgliederliste nennt die Klasse nur als ID;
den Namen schlägt die Integration einmal je Klasse in `playable-class/{id}` nach,
klappt das nicht, bleibt `class` leer. Namen der Ränge liefert die API nicht.

### Aussehen und PvP-Brackets

- **Aussehen** (seit 0.11.0, am Level-Sensor): `gender` und `transmog`, je
  Gegenstand `slot`, `slot_name`, `id`, `name` und `enchant`. Der Endpunkt wird
  nur abgefragt, solange der Level-Sensor aktiv ist.
- **Namen der Transmog-Gegenstände** (seit 0.11.2): Die API nennt keine Namen,
  und ob `id` die Item-ID ist, ist nicht dokumentiert. Die Integration prüft das
  an den echten Daten: Stimmt die ID auf mindestens einem Platz mit dem dort
  angelegten Item überein (Platz ohne Transmog), sind es Item-IDs. Dann kommt
  `name` aus der Ausrüstung oder einmal je Gegenstand aus `item/{id}`. Stimmt
  kein Platz überein (alles transmogrifiziert oder Ausrüstung nicht abgefragt),
  bleibt `name` leer.
- **PvP-Wertung je Bracket** (seit 0.11.0): Zustand ist die Wertung; Attribute
  `season_played`, `season_won`, `season_lost`, `weekly_played`, `weekly_won`,
  `weekly_lost` und `season_id`. Abgefragt werden die Brackets `2v2`, `3v3` und
  `rbg` (`3v3` nennt die Classic-Doku als Beispiel, alle drei die
  Typdefinitionen von `@blizzard-api/wow`); einen Sensor gibt es für jedes, das
  Daten liefert. Brackets mit Sensor fragt die Integration stündlich ab, auch
  nach einem späteren 404, Brackets ohne Sensor alle 6 Stunden; liefert eines
  dann Daten, entsteht sein Sensor ohne Neuladen (seit 0.18.0; von 0.11.1 bis
  0.17.x gar nicht mehr bis zum Neuladen). `5v5` aus Classic ist nirgends
  dokumentiert und fehlt deshalb.

### Jägerbegleiter

Den Sensor gibt es nur, wenn die API Begleiter liefert. Für andere Klassen
meldet sie laut Blizzard-Doku 404; scheitert die erste Abfrage, fragt die
Integration alle 6 Stunden erneut und legt den Sensor dann ohne Neuladen an
(seit 0.18.0). Zustand ist die Zahl der Begleiter.

Klassenprüfung (seit 0.10.1): Meldet die API für einen Charakter 404, ist er
laut Doku kein Jäger, und die Integration fragt den Endpunkt bis zum nächsten
Neuladen nicht mehr ab (vorher alle 6 Stunden). Eine Klassen-ID nennt die Doku
nicht; die Prüfung stützt sich deshalb auf diese Antwort statt auf eine ID.
Hat der Endpunkt seit dem Start schon Begleiter geliefert, gilt ein späterer 404
nicht als endgültig, damit der Sensor eines Jägers bei einem kurzen Fehler der
API nicht stehen bleibt. Andere Fehler (z. B. keine Antwort) führen zu einem
erneuten Versuch.
Attribute: `summoned` (Name des beschworenen Begleiters), `active` (Namen der
aktiven Begleiter) und `pets`, je Begleiter `name`, `level`, `creature`,
`creature_id`, `slot`, `active` und `summoned`. Die Feldnamen der API stammen aus
den Typdefinitionen von `@blizzard-api/wow` 4.1.4 und `@blizzard-api/classic-wow`
4.2.0; dort sind `is_active` und `is_summoned` optional, fehlen sie, gilt der
Begleiter als nicht aktiv bzw. nicht beschworen. Gilt für alle Spielversionen;
die Classic-Doku nennt den Endpunkt ebenfalls.

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
- **Talente** (seit 0.12.0, nur außerhalb von Retail): Classic liefert die
  Talente als Punkte je Baum (`specialization_groups`), Retail laut
  Typdefinitionen nicht. Zustand ist der Baum mit den meisten Punkten der aktiven
  Gruppe, bei Gleichstand alle diese Bäume („Elementar / Verstärkung“).
  Attribute: `total_points` und `trees`, je Baum `name`, `points` und `talents`
  (je Talent `name`, `rank`, `description`). Die Antwort nennt nur Bäume mit
  Punkten; ohne Punkte gibt es keinen Sensor, er entsteht mit den ersten
  Punkten (seit 0.18.0 ohne Neuladen).
- **Talentbaum** (seit 0.13.0, Retail): Zustand ist die Spezialisierung.
  Attribute: `hero` (aktiver Heldenbaum), `class_nodes`, `spec_nodes` und
  `hero_nodes` (je Knoten `id`, `row`, `col`, `type`, `max_rank`, `rank`,
  `talent` als gewählte Talent-ID, `talents` mit `id`, `name`, `spell_id`,
  `description` und `icon`, sowie `unlocks` für die Pfeile) und `gates` (je
  Schwelle `tree`, `row`, `points`). Grundlage ist die echte Antwort vom
  28.10.2026: Die IDs der vergebenen Talente sind die Knoten-IDs; die Knoten der
  Heldenbäume stehen in der Antwort auch unter den Knoten der Spezialisierung und
  werden dort herausgenommen; Knoten ohne Talent (vermutlich die Wahl des
  Heldenbaums) fallen weg. Classic liefert keinen Talentbaum.
  **Apex-Talent** (seit 0.16.1): Laut
  [Blizzard](https://worldofwarcraft.blizzard.com/news/24244472/) kostet es
  „a total of four specialization talent points“ in drei Stufen (1, 2 und 1
  Punkt), ab Stufe 81. Die API zeigt das so: Der Baum führt den Apex-Knoten mit
  einem Rang und nur der ersten Stufe; im Profil steht jede gelernte Stufe als
  eigener Eintrag mit derselben Knoten-ID, eigener Talent-ID und eigenem Rang
  (echte Antwort, Frost: Knoten 110422 dreimal, Rang 1, 2 und 1). Der Knoten
  bekommt deshalb `rank` als Summe der Stufen, `max_rank` 4 (aus Blizzards
  Angabe, die API nennt sie nicht), `talent` die erste Stufe, falls gelernt, und
  `stages` (je Stufe `id`, `name`, `spell_id`, `description`, `icon`, `rank`; die
  erste aus dem Baum, die weiteren aus dem Profil). Als Apex gilt der einzige
  Knoten in der untersten Zeile des Spezialisierungsbaums; Blizzard: „beneath the
  (currently) final section of the specialization tree“. Die Symbole der
  weiteren Stufen kosten zwei Abfragen mehr, einmalig.
- **Mythic+-Läufe:** Der Sensor „Höchster Mythic+-Schlüssel“ hat `best_runs`
  (Kurzform je Dungeon, z. B. „+12“; bis 0.21.x mit „in Zeit“ auf Deutsch) und
  `runs`: je Lauf `dungeon`, `dungeon_id`, `level`,
  `timed`, `duration` (Sekunden), `completed`, `rating`, `color`, `affixes` und
  `members` (Name, Realm, Spezialisierung, Itemlevel). Die Einheit von `duration`
  in der API ist nicht belegt; die Integration erkennt Sekunden und Millisekunden
  an der Größe.

### Sprache

Texte aus der API (Namen von Klassen, Gegenständen, Raids, Realms usw.) kommen
in der Sprache, die unter **Konfigurieren** am Eintrag „Battle.net API“ als
„Sprache der API-Texte“ eingestellt ist (seit 0.19.0). Die Namen der Entitäten
selbst folgen wie bei jeder Integration der Sprache von Home Assistant.

| Auswahl | Europa | Amerika | Korea | Taiwan |
|---|---|---|---|---|
| Sprache der Region (Vorgabe, wie vor 0.19.0) | `de_DE` | `en_US` | `ko_KR` | `zh_TW` |
| English | `en_GB` | `en_US` | `en_US` | `en_US` |
| Deutsch, Français, Italiano, Русский | `de_DE`, `fr_FR`, `it_IT`, `ru_RU` | – | – | – |
| Español | `es_ES` | `es_MX` | – | – |
| Português do Brasil | – | `pt_BR` | – | – |
| 한국어 | – | – | `ko_KR` | – |
| 繁體中文 | – | – | – | `zh_TW` |

„–“ heißt: Die Region kennt die Sprache nicht, es gilt die Sprache der Region.
„Sprache von Home Assistant“ nimmt die Sprache der Oberfläche (z. B. `fr` aus
„fr“, `en` aus „en-GB“) und wählt danach wie in der Tabelle. Die Zuordnung
stammt aus den Bibliotheken `@blizzard-api/core` 4.2.0 und `blizzard.js` 5.0.0
(geprüft am 29.10.2026); die Integration nutzt nur Sprachen, die beide nennen.
`pt_PT` für Europa nennt nur `blizzard.js`, es fehlt deshalb. Speichern lädt die
Integration neu; die Entitäts-IDs bleiben, Namen mit Teilen aus der API (z. B.
Beruf oder Realm) übernehmen die neue Sprache. Die Diagnose zeigt die Option
und die genutzte Sprache je Region (`options`, `locales`).

Ausnahmen: Die Berufe-Seite und die Erfolge-Seite eines Charakters liefern Namen
auf Englisch, auch mit deutscher Spracheinstellung. Die Integration schlägt Berufe, Berufsstufen und
Erfolgskategorien deshalb einmalig in den statischen Spieldaten nach; klappt das
nicht, bleibt der englische Name. Raidnamen kommen weiterhin auf Englisch.

### Nicht in der Datenbank

Lange Attribute speichert Home Assistant nicht im Verlauf: `tooltip`, `factions`,
`runs`, `titles`, `statistics`, `activities`, `pets`, `members`, `transmog`,
`trees`, `class_nodes`, `spec_nodes`, `hero_nodes` und `gates`. Die Werte stehen trotzdem im aktuellen Zustand.

## Abfragen und Takte

### Takte und Gruppen (seit 0.20.0)

Unter **Konfigurieren** am Eintrag „Battle.net API“ stehen neben der Sprache:

| Option | Vorgabe | Erlaubt | Gilt für |
|---|---|---|---|
| Profil | 15 min | 5–120 min | Profil und Mythic+-Profil: Level, Itemlevel, Mythic+-Wertung usw. |
| Details | 60 min | 15–720 min | Endpunkte mit 1 h in den Tabellen: Ausrüstung, Raids, Mythic+-Läufe, PvP, Erfolge, Charakterwerte, Gildenaktivitäten, Spezialisierung |
| Seltene Details | 360 min | 60–1440 min | Endpunkte mit 6 h in den Tabellen (Berufe, Sammlungen, Ruf, Titel, Quests, Spielstatistik, Gilde und Mitglieder, Bilder, Aussehen, Jägerbegleiter), dazu Endpunkte ohne Entität, PvP-Brackets ohne Sensor und die WoW-Marke ohne Sensor |

Seltene Details dürfen nicht häufiger laufen als Details; der Dialog lehnt das
ab. Die Spielwelt (Realms, WoW-Marke, Reset) bleibt beim festen Takt von
15 Minuten, der Status-Endpunkt bei einmal am Tag. Profildaten aktualisiert
Blizzard erst nach dem Ausloggen; kürzere Profiltakte bringen deshalb selten
früher neue Werte.

**Ausgeschaltete Gruppen:** Gilde, Sammlungen und Titel, Erfolge,
Spielstatistik, Quests, Ruf, Berufe, Raids, PvP. Für eine ausgeschaltete Gruppe
fragt die Integration nichts ab und legt keine Entitäten an, auch nicht später
ohne Neuladen; die Ereignisse der Gruppe (z. B. „Boss besiegt“ bei Raids, „Neu
gesammelt“ bei Sammlungen) entfallen mit. Schon vorhandene Entitäten bleiben
mit Entitäts-ID, Anpassungen und Verlauf in der Registry, stehen aber als
„nicht verfügbar“ bzw. „nicht mehr bereitgestellt“ da; beim Einschalten kommen
sie mit derselben Entitäts-ID zurück. Wer eine Gruppe dauerhaft nicht braucht,
kann ihre Entitäten löschen. Bewusst nicht über die Registry deaktiviert: Das
Wiedereinschalten ließe Home Assistant den Eintrag nach 30 Sekunden ein zweites
Mal neu laden.

Speichern lädt die Integration einmal neu.

### Allgemein

- Ein Endpunkt mit Entitäten wird nur abgefragt, wenn mindestens eine davon
  aktiviert ist; sind alle deaktiviert, entfällt er. Beim Start fragt die
  Integration alle Endpunkte einmal ab, weil manche Entitäten nur entstehen,
  wenn Daten kommen. Endpunkte, für die keine Entität entstanden ist (z. B.
  Berufe ohne Beruf, Erfolge in Classic Era), fragt sie danach alle 6 Stunden
  ab. Liefern sie Daten, entstehen die Entitäten ohne Neuladen, ebenso neue
  Berufe, Gilde, PvP-Brackets, Zusatzplätze, Realms und Sensoren, die erst
  später einen Wert haben (seit 0.18.0; von 0.11.3 bis 0.17.x fragte sie solche
  Endpunkte bis zum Neuladen gar nicht ab). Fällt eine Bedingung weg (z. B.
  Gilde verlassen), bleibt die Entität und zeigt „unbekannt“.
- Ereignisse lösen nur für Einträge aus, die nach dem Start von Home Assistant
  dazukommen.
- Abfragelimit: Blizzard erlaubt laut Doku („Getting Started“, Throttling)
  100 Abfragen je Sekunde und meldet darüber HTTP 429 bis zum Ende der Sekunde.
  Bei 429 wartet die Integration eine Sekunde und fragt einmal erneut (seit
  0.14.1). Kommt dann wieder 429, bricht sie das Nachschlagen von Symbolen und
  (seit 0.19.1) von Berufsnamen ab und holt den Rest beim nächsten Takt.
- Störungen (seit 0.19.1): Läuft das Token ab, während mehrere Abfragen
  gleichzeitig laufen, holt die Integration nur ein neues. Antwortet Blizzard
  mit etwas anderem als einem JSON-Objekt (z. B. einer Wartungsseite) oder
  einer Token-Antwort ohne Token, gilt das als gewöhnlicher Abfragefehler:
  kurze Meldung im Log, Werte bis zum nächsten Takt nicht verfügbar, beim Start
  ein neuer Versuch. Lehnt Blizzard beim Nachschlagen der Berufsnamen die
  Zugangsdaten ab, fragt Home Assistant wie bei allen anderen Abfragen nach
  einer erneuten Anmeldung.
- Talentbaum (seit 0.13.0): Den Baum der Spezialisierung lädt die Integration
  einmal je Start und Spezialisierung, die Symbole einmal je Talent, erst nach
  dem Anlegen der Entitäten (bei einer Klasse rund 100 Abfragen, einmalig). Ist
  der Sensor „Talentbaum“ deaktiviert, entfällt beides.
- Berufs-Sensoren entstehen aus den Antworten; ein neu gelernter Beruf
  erscheint spätestens nach 6 Stunden, ohne Neuladen (seit 0.18.0).
- Das Token holt die Integration über den globalen Endpunkt
  `https://oauth.battle.net/token` (seit 0.2.0), wie die Bibliotheken
  `@blizzard-api/core` und `blizzard.js`.
- Einmal am Tag je Charakter der Status-Endpunkt (`…/status`, Feld `is_valid`),
  siehe [Ändern, Hinweise und Diagnose](#ändern-hinweise-und-diagnose).
- Spielwelt: WoW-Marke, Reset, Season und jeder Realm werden einzeln abgefragt.
  Fällt eine Abfrage aus, behält ihr Wert den letzten Stand; nicht verfügbar wird
  die Spielwelt erst, wenn alle ausfallen. Gibt es keinen Sensor „WoW-Marke“
  (Classic und Forever ohne Preis), fragt sie die Integration nur alle 6 Stunden
  ab und legt den Sensor an, sobald ein Preis kommt (seit 0.18.0; von 0.10.2 bis
  0.17.x gar nicht mehr bis zum Neuladen).
- Die Realm-Liste beim Hinzufügen zeigt keine internen Realms von Blizzard (z. B.
  „EU1A Account Realm“, „EU4A1-INST“, „RDB EU“).

## Aktionen (seit 0.21.0)

### Aktualisieren (`wow_character.refresh`)

Fragt Charaktere sofort ab, statt den nächsten Takt abzuwarten: Profil und
alle Detail-Endpunkte, die sonst im Takt laufen, auch die seltenen und die
Suche nach neuen Entitäten (PvP-Brackets ohne Sensor usw.). Abgeschaltete
Gruppen und Endpunkte, deren Entitäten alle deaktiviert sind, bleiben aus.

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `device_id` | nein | Geräte von Charakteren oder Spielwelten. Leer: alle Charaktere aller geladenen Einträge. Ein Spielwelt-Gerät fragt WoW-Marke, Reset und Season sofort ab (Realms ohnehin bei jedem Lauf). |

Scheitert eine Abfrage, meldet die Aktion die betroffenen Charaktere als
Fehler; die Entitäten behalten wie beim Takt den letzten Stand bzw. werden
nicht verfügbar. Je Charakter sind das 20 bis 26 Abfragen (je nach Gilde,
Klasse und aktivierten Entitäten), dazu Symbole, die noch nicht bekannt sind;
das Abfragelimit von Blizzard liegt bei 100 je Sekunde (siehe
[Allgemein](#allgemein)). Blizzard
aktualisiert das Profil erst nach dem Ausloggen; eine Automation sollte also
nach dem Ausloggen aufrufen, nicht im Spiel.

```yaml
action: wow_character.refresh
data:
  device_id: 0123456789abcdef0123456789abcdef  # Gerät des Charakters
```

### Charakter nachschlagen (`wow_character.get_character`)

Liefert das Profil eines beliebigen Charakters als Antwort, ohne ihn
einzurichten, z. B. für Freunde oder Gildenmitglieder. Es entstehen weder
Gerät noch Entitäten.

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `config_entry_id` | nur bei mehreren Einträgen | Eintrag „Battle.net API“, dessen Zugang benutzt wird |
| `region` | ja | `eu`, `us`, `kr` oder `tw` |
| `game_version` | nein | `retail` (Vorgabe), `forever`, `classic_era`, `classic_progression`, `classic_anniversary` |
| `realm` | ja | Name oder Slug, Groß- und Kleinschreibung egal, z. B. `Die Aldor` oder `die-aldor` |
| `character` | ja | Name des Charakters |

Die Antwort enthält `name`, `id`, `realm`, `realm_slug`, `region`,
`game_version`, `level`, `class`, `spec`, `race`, `faction`, `guild`, `title`,
`achievement_points`, `equipped_item_level`, `average_item_level`,
`last_login` (ISO-Zeit), `mythic_rating` (nur Retail; Wert der API ohne
Season-Prüfung, wie im Arsenal) und `avatar` (Bildadresse). Fehlt ein Wert,
steht `null` da. Texte kommen in der Sprache aus den Optionen (siehe
[Sprache](#sprache)).

Abfragen: Realm-Liste der Region (einmal je Start von Home Assistant bzw.
Neuladen), Profil, Mythic+-Profil (nur Retail) und Bilder. Unbekannter Realm
oder Charakter ergibt eine Fehlermeldung statt einer Antwort.

```yaml
action: wow_character.get_character
data:
  region: eu
  realm: Die Aldor
  character: Testchar
response_variable: charakter
```

## Dashboard-Karten

Zwei Karten liefert die Integration selbst mit; Home Assistant lädt sie mit dem
Frontend, ohne zusätzliche HACS-Karten oder Dashboard-Ressourcen:

- [„WoW Arsenal“](#karte-wow-arsenal-seit-0150) (`custom:wow-arsenal-card`,
  seit 0.15.0): Charakterseite mit Ausrüstung und Kennzahlen.
- [„WoW Talentbaum“](#karte-wow-talentbaum-seit-0140)
  (`custom:wow-talent-tree-card`, seit 0.14.0): Talentbäume mit vergebenen
  Punkten (Retail).

Weitere Karten im Nachtblau-Stil als YAML liegen im Repository
[philf90/home-assistant](https://github.com/philf90/home-assistant) unter
`dashboard/sonstiges/`: die Arsenal-Karte (`wow-arsenal-karte.yaml` mit
`wow-templates.yaml`) und zehn einzeln nutzbare Karten (`wow-*-karte.yaml`) für
Charaktere, Spielwelt, Raids, Mythic+, Berufe, Ruf, Sammlungen, Werte, PvP und
Gilde. Sie zeigen die Spielversion und passen sich an: Was eine Version nicht
liefert (bei Classic z. B. Raids, Mythic+ und Sammlungen), fällt weg oder wird
als Hinweis genannt.
Alle brauchen `custom:button-card`; weitere Voraussetzungen (z. B. browser_mod
für das Arsenal-Popup) stehen im Kopf jeder Datei. Die Arsenal-Karte liefert
die Integration seit 0.15.0 auch selbst mit, ohne diese Voraussetzungen (siehe
[Karte „WoW Arsenal“](#karte-wow-arsenal-seit-0150)).

<p align="center">
  <img src="https://raw.githubusercontent.com/philf90/HA-WOW/main/assets/vorschau-galerie.png" alt="Mythic+-, Sammlungen-, Werte- und Ruhmstufen-Karte im Nachtblau-Stil mit Beispieldaten" width="100%">
</p>
<p align="center"><sub>Mythic+, Sammlungen &amp; Erfolge, Werte und Ruhmstufen · Beispieldaten</sub></p>

<p align="center">
  <img src="https://raw.githubusercontent.com/philf90/HA-WOW/main/assets/vorschau-pvp-gilde.png" alt="PvP- und Gilden-Karte im Nachtblau-Stil für Retail, Classic Anniversary und Classic Era mit Beispieldaten" width="100%">
</p>
<p align="center"><sub>PvP und Gilde in Retail, PvP in Classic Anniversary, Gilde in Classic Era · Beispieldaten</sub></p>

### Karte „WoW Arsenal“ (seit 0.15.0)

Die Arsenal-Karte aus `wow-arsenal-karte.yaml` als eigene Karte der Integration,
im selben Aufbau und Nachtblau-Stil, aber ohne `custom:button-card`, browser_mod
und Dashboard-Templates. Wie die Karte „WoW Talentbaum“ lädt Home Assistant sie
mit dem Frontend.

```yaml
type: custom:wow-arsenal-card
entity: sensor.mein_charakter_level   # eine beliebige Entität des Charakters
```

- Kopf mit Avatar, Symbol der Spezialisierung, Name, Titel, Spielversion,
  Stufe, Volk, Spezialisierung und Klasse; Pillen für Itemlevel, Mythic+-Wertung
  (sonst `api_rating`), Fraktion, Realm und Gilde.
- Ganzkörperbild mit den 18 Plätzen in der Reihenfolge des Arsenals: Symbol mit
  Rand in der Qualitätsfarbe, Itemlevel daneben (ohne Itemlevel leer), ein
  Amber-Punkt bei leerem Sockel, leere Plätze gestrichelt.
- Zusatzplätze außerhalb von Retail (seit 0.16.0): Jeder Sensor
  „Ausrüstung {Platz}“ des Charakters (siehe [WoW Classic](#wow-classic)) steht
  in der Waffenreihe hinter Waffen- und Schildhand. Ohne Zusatzplatz bleibt die
  Waffenreihe wie bisher.
- Mit der Maus zeigt ein Platz den Item-Tooltip; Antippen öffnet ihn als
  Fenster in der Karte (Escape oder ✕ schließt), browser_mod ist nicht nötig.
- Kennzahlen: Raid in der höchsten Schwierigkeit mit Kills, Anzahl der Erfolge
  (Sensor „Erfolge“, seit 0.15.2; vorher die Erfolgspunkte unter dem Namen
  „Erfolge“), Reittiere und Ehrenstufe, ohne Ehrenstufe die ehrenhaften Siege.
  Es erscheinen
  nur Kennzahlen, deren Entität es gibt; Classic Era zeigt deshalb von selbst
  weniger.
- Die Karte findet die Entitäten über das Gerät des Charakters und die
  Übersetzungsschlüssel der Integration. Anders als die YAML-Karte braucht sie
  kein Präfix und funktioniert mit jeder Sprache der Oberfläche; ihre eigenen
  Texte gibt es auf Deutsch und Englisch.
- Breite: In der Abschnittsansicht nimmt die Karte die ganze Breite des
  Abschnitts ein (12 von 12 Spalten, seit 0.15.1; in 0.15.0 nur 6). Schmaler als
  300 Pixel stehen die Kennzahlen in zwei Spalten statt in einer Reihe.

### Karte „WoW Talentbaum“ (seit 0.14.0)

Die Integration liefert eine eigene Karte mit, ohne zusätzliches HACS-Paket und
ohne Eintrag unter den Dashboard-Ressourcen: Home Assistant lädt sie mit dem
Frontend. Nach dem Update einmal die Seite neu laden (fehlt die Karte danach,
siehe [Ändern, Hinweise und Diagnose](#ändern-hinweise-und-diagnose)). Sie
zeichnet Klassen-, Spezialisierungs- und aktiven Heldenbaum aus dem Sensor
„Talentbaum“ (Retail):

```yaml
type: custom:wow-talent-tree-card
entity: sensor.mein_charakter_talentbaum
# optional, Auswahl und Reihenfolge der Bäume:
trees: [class, spec, hero]
```

- Form der Knoten wie im Spiel: Quadrat aktiv, Kreis passiv, Achteck Wahl.
- Vergebene Talente in Farbe mit goldenem Rahmen (Höchstrang) oder grünem
  (teilweise), nicht vergebene grau. Rang („2/3“) bei Talenten mit mehreren
  Rängen; meldet die API mehr Ränge als der Baum kennt, steht das so da (z. B.
  „2/1“). Das Apex-Talent zeigt die Punkte aller Stufen („4/4“, seit 0.16.1).
- Pfeile aus `unlocks`, golden, wenn beide Enden vergeben sind; gestrichelte
  Linien für die Punkte-Schwellen der API.
- Die Zahl hinter dem Baumnamen ist die Summe der vergebenen Ränge laut API,
  einschließlich vorgegebener Punkte.
- Antippen zeigt Name, Rang und Beschreibung unter dem Baum, bei Wahlknoten
  beide Talente mit Haken am gewählten, beim Apex-Talent alle Stufen mit Rang.
- Fehlt ein Symbol, steht ein Platzhalter mit den Anfangsbuchstaben.
- In der Kartenauswahl heißt sie „WoW Talentbaum“; der Editor bietet die
  Sensoren der Integration an.

## Ändern, Hinweise und Diagnose

- **Takte und Gruppen:** **Konfigurieren** am Eintrag „Battle.net API“ (seit
  0.20.0, siehe [Takte und Gruppen](#takte-und-gruppen-seit-0200)).
- **Sprache der API-Texte:** **Konfigurieren** am Eintrag „Battle.net API“
  (seit 0.19.0, siehe [Sprache](#sprache)).
- **Neues Secret:** am Eintrag „Battle.net API“ ⋮ → **Neu konfigurieren** →
  **Client-ID oder Secret ändern**. Lehnt Blizzard die Zugangsdaten ab, fragt
  Home Assistant von selbst nach neuen. Eine andere Client-ID geht ebenfalls;
  die Spielwelt-Entitäten behalten dabei ihre Entitäts-IDs und ihren Verlauf
  (seit 0.17.2, vorher entstanden sie neu mit der Endung `_2`).
- **Neue Charaktere:** **Charakter hinzufügen** → **Mit Battle.net anmelden und
  Charaktere wählen** (siehe [Battle.net-Anmeldung](#battlenet-anmeldung-seit-0170)).
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
- **Karte fehlt nach einem Update:** Zeigt das Dashboard statt einer Karte
  „Custom element doesn't exist: wow-talent-tree-card“ (oder
  `wow-arsenal-card`), hat die App oder der Browser die Datei der Karte nicht
  geladen. Ein Fehler beim Laden steht nur in der Konsole des Browsers („Failed
  to load extra module …“), nicht im Log von Home Assistant. Abhilfe: in der
  Companion App den Frontend-Cache zurücksetzen (Einstellungen der App,
  englisch „Reset frontend cache“), im Browser die Seite ohne Cache neu laden
  (Strg+Umschalt+R). Live so aufgetreten nach dem Update auf 0.15.2 in der
  iOS-App; die Datei der Karte war unverändert, nach dem Zurücksetzen des
  Caches erschien die Karte wieder.
- **Diagnose:** Einstellungen → Geräte & Dienste → WoW Charakter → ⋮ →
  **Diagnose herunterladen** liefert die API-Antworten ohne Client-ID und Secret.
  Seit 0.22.0 fehlen darin auch Name, ID und Verweis anderer Spieler (unter
  jedem Schlüssel `character`, z. B. Gruppen der Mythic+-Läufe,
  Gildenmitglieder und -aktivitäten); Realm, Stufe, Klasse und
  Spezialisierung bleiben zum Prüfen der Feldnamen stehen. Der eigene
  Charakter steht weiter mit Namen im Profil.
  Damit lassen sich Feldnamen prüfen, wenn ein Wert fehlt. Vergebene Talente
  stehen dort mit IDs und Rang, ohne Tooltip-Texte. Beim Herunterladen lädt die
  Diagnose einmal den Talentbaum des aktiven Loadouts (Retail, seit 0.12.1) und
  zeigt je Knoten ID, Zeile, Spalte, Art, Zahl der Ränge, Talente und
  Verbindungen. Seit 0.12.2 nimmt sie den Baum der Spezialisierung
  (`selected_spec_talent_tree`, Endpunkt `talent-tree/{id}/playable-specialization/{specId}`)
  und nur ohne diesen Verweis den Klassenbaum (`talent-tree/{id}`). Der
  Klassenbaum enthält die Knoten aller Spezialisierungen der Klasse, teils auf
  denselben Plätzen, und Verbindungen nur bei den Heldentalenten (echte Antwort
  vom 28.10.2026). Live geprüft am selben Tag: Die IDs der vergebenen Talente
  sind die Knoten-IDs des Baums; bei Wahlknoten zeigt die Talent-ID die Wahl.

## WoW Classic

Grundlage ist die offizielle Doku von Blizzard (Stand 28.10.2026):
[Classic Profile APIs](https://community.developer.battle.net/documentation/world-of-warcraft-classic/profile-apis),
[Classic Game Data APIs](https://community.developer.battle.net/documentation/world-of-warcraft-classic/game-data-apis)
und [Classic Namespaces](https://community.developer.battle.net/documentation/world-of-warcraft-classic/guides/namespaces).

| Spielversion in der Integration | Spiel laut Blizzard-Doku | Namespace |
|---|---|---|
| Classic Era | World of Warcraft Classic (Era) | `profile-classic1x-{region}` |
| Classic Progression | Mists of Pandaria Classic (Progression) | `profile-classic-{region}` |
| Classic Anniversary | Burning Crusade Classic (Anniversary) | `profile-classicann-{region}` |

Für die Realm-Liste und die Spielwelt gilt `dynamic-…`, für Symbole `static-…`
mit demselben Zusatz. Welche Erweiterung hinter Progression und Anniversary
steckt, ändert Blizzard mit der Zeit; der Namespace bleibt.

**Abgefragt werden nur Endpunkte, die die Classic-Doku nennt:**

| Bereich | Classic | Endpunkt |
|---|---|---|
| Profil (Level, Itemlevel, Erfahrung, Erfolgspunkte, letzter Login), Level gestiegen | ja | Profil |
| Status-Prüfung (Reparaturhinweise) | ja | `status` |
| Ausrüstung, leere Sockel, Verzauberungen, Set | ja | `equipment`; Symbole aus `media/item/{id}` |
| Ehrenstufe, ehrenhafte Siege | ja | `pvp-summary` |
| PvP-Wertung je Bracket | ja | `pvp-bracket/{bracket}` |
| Geschlecht und Transmog am Level-Sensor | ja | `appearance` |
| Charakterwerte (zunächst aus) | ja | `statistics` |
| Erfolge, Neuer Erfolg, Spielstatistik | ja | `achievements`, `achievements/statistics` |
| Spezialisierung | ja | `specializations` |
| Talente (Punkte je Baum) | ja | `specializations` |
| Avatar, Ganzkörperbild | ja | `character-media` |
| Gilde mit Mitgliederliste | ja | `/data/wow/guild/{realm}/{gilde}`, `…/activity`, `…/roster`; Klassennamen aus `playable-class/{id}` |
| Namen der Transmog-Gegenstände | ja, wenn die IDs belegt Item-IDs sind | `item/{id}` |
| Jägerbegleiter, nur für Jäger | ja | `hunter-pets` |
| Server, Warteschlange, Bevölkerung je Realm | ja | `realm/{slug}`, `connected-realm/{id}` |
| WoW-Marke | nur wenn die API einen Preis liefert; ohne Sensor alle 6 Stunden geprüft | `token/index` |
| Klassen-Symbol (`class_icon`) | ja | `media/playable-class/{id}` |
| Raids, Boss besiegt, Mythic+, wöchentlicher Reset | nein, nicht in der Doku | – |
| Berufe, Ruf, Titel, Quests, Sammlungen, Neu gesammelt | nein, nicht in der Doku | – |
| Symbole von Spezialisierung und Erfolgen, deutsche Erfolgskategorien | nein, nicht in der Doku | – |
| Auktionshaus | nein, bewusst weggelassen: laut Doku oft über 10 MB je Abfrage, nur Item-IDs ohne Namen | – |

**Was die Antworten enthalten, sagt die Doku nicht** (sie nennt Endpunkte und
Parameter, keine Antwortfelder). Die Integration liest Classic deshalb wie
Retail und legt für Classic (wie für Forever) nur an, was wirklich Daten
liefert:

- Entitäten eines Endpunkts nur, wenn er antwortet (z. B. keine Erfolge, falls
  Classic Era dafür 404 meldet).
- Sensoren nur, wenn sie einen Wert haben (z. B. kein Sensor
  „Meisterschaft“, wenn die Antwort keinen Wert dafür enthält). Ist die erste
  Abfrage gescheitert, werden sie angelegt und bleiben „unbekannt“, bis Daten
  kommen.
- Ausrüstungsplätze, die Retail nicht kennt, bekommen einen eigenen Sensor
  „Ausrüstung {Platz}“ mit dem Namen des Platzes aus der API, falls die Antwort
  solche Plätze enthält. Die Karte „WoW Arsenal“ zeigt sie seit 0.16.0 in der
  Waffenreihe.

Kommt ein Wert erst später dazu (z. B. erste Erfolge, ein belegter
Zusatzplatz), erscheint sein Sensor ohne Neuladen (seit 0.18.0). Endpunkte ohne
Entität fragt die Integration dafür alle 6 Stunden ab.

**Live geprüft mit Classic Era** (28.10.2026, ein Charakter auf Stufe 10, EU):
Namespace `profile-classic1x-eu`, Profil, Ausrüstung, Verzauberungen,
`pvp-summary`, `statistics`, `specializations`, `character-media` und
`appearance` antworten. In `appearance` sind die Platz-Bezeichner dieselben wie
in der Ausrüstung und die IDs die Item-IDs. Erfolge, Spielstatistik, PvP-Brackets
und die WoW-Marke liefern nichts, dafür entstehen keine Entitäten. Die Ausrüstung
nennt je Item kein Itemlevel. Die Talente kommen anders aufgebaut als in Retail
(`specialization_groups`); einen Sensor „Spezialisierung“ gibt es deshalb in
Classic Era nicht, dafür seit 0.12.0 den Sensor „Talente“. Das Profil verweist auch auf `titles` und `reputations`; die
Classic-Doku nennt beide nicht, die Integration fragt sie nicht ab.
Fällt ein Sensor bei einem späteren Start weg, bleibt er als „nicht mehr
bereitgestellt“ stehen und lässt sich löschen.

## WoW Forever

Blizzard hat den API-Namespace für Forever noch nicht dokumentiert (Start
04.11.2026). Beim Hinzufügen eines Forever-Charakters probiert die Integration die
Kandidaten aus `const.py` (`GAME_VERSIONS["forever"]["namespaces"]`) der Reihe nach:
Der erste, unter dem die API eine Realm-Liste liefert, wird gespeichert. HTTP 404
und 403 gelten dabei als „Namespace unbekannt“, der nächste Kandidat folgt (403
seit 0.17.2; vorher brach das Hinzufügen mit „Verbindung fehlgeschlagen“ ab). Die
Kandidaten sind **unbestätigt**. Sobald Blizzard den Namespace nennt, dort
eintragen; schlägt das Hinzufügen fehl, ist das die wahrscheinlichste Ursache.

Für Forever-Charaktere legt die Integration nur Entitäten an, deren Endpunkt
Daten liefert, und (seit 0.9.0) nur Sensoren, die einen Wert haben, wie bei
[Classic](#wow-classic); seit 0.18.0 auch später ohne Neuladen.

## Grenzen

- Profildaten aktualisiert Blizzard erst, wenn sich der Charakter ausloggt.
- Die Region China wird nicht unterstützt.
- Gold, Position und Account-Daten liefert die API nur mit einer Anmeldung des
  Spielers (Authorization Code Flow, Scope `wow.profile`). Das Login-Token gilt
  24 Stunden, ein Refresh-Token gibt Blizzard nicht aus. Die Integration nutzt
  die Anmeldung deshalb nur zur Suche nach Charakteren und kann diese Werte
  nicht dauerhaft abfragen.
- Große Schatzkammer und Affixe der aktuellen Woche liefert die API nicht: Sie
  kennt je Season nur den besten Lauf je Dungeon, und die Woche hat nur Start und
  Ende.
- WoW Forever ist ungetestet.
- WoW Classic ist nur mit einem Classic-Era-Charakter live geprüft, Progression
  und Anniversary nur automatisch (siehe [WoW Classic](#wow-classic)). Raids, Mythic+, Berufe, Ruf, Titel, Quests und
  Sammlungen gibt es für Classic nicht, weil die Classic-API sie nicht anbietet.
  Einen wöchentlichen Reset liefert die Classic-API ebenfalls nicht.
- Das Logo zeigt Home Assistant ab 2026.3 aus dem Ordner `brand/` der
  Integration. In der HACS-Liste erscheint stattdessen ein Platzhalter: HACS 2.0.5
  lädt Symbole nur von `brands.home-assistant.io`, und dort nimmt Home Assistant
  keine neuen Custom-Integrationen mehr auf. Das betrifft jede neue
  Custom-Integration und lässt sich in diesem Repo nicht beheben.

## Teststand

Automatische Tests laufen gegen Home Assistant 2026.2.3; live geprüft wurde unter
Home Assistant 2026.10.4 mit Retail-Charakteren der Region EU, seit 0.11.2 auch
mit einem Classic-Era-Charakter (siehe [WoW Classic](#wow-classic)).

- **0.22.x:** 307 automatische Tests. 0.22.0: 9 Tests für die Diagnose ohne
  andere Spieler (Mythic+-Läufe der Season und der Woche, Gildenmitglieder
  und -aktivitäten, Hilfsfunktion; der eigene Name bleibt), `best_runs` ohne
  festen Text, Bevölkerung als Zustand (bekannte Werte, unbekannter Wert und
  fehlender Typ ergeben „unbekannt“ statt eines Fehlers) und das Gerätemodell
  für Retail und Classic Era; ein Test angepasst (Bevölkerung `high` statt
  „Hoch“). Gegenprobe: neun Teile einzeln ausgebaut, jedes Mal schlug ein
  Test fehl. **Live geprüft mit 0.22.0** (30.10.2026, Home Assistant
  2026.10.4, acht Charaktere in EU Retail und Classic Era): Bevölkerung mit den
  Zuständen `full`, `medium` und `low` (vorher „Voll“, „Mittel“, „Niedrig“) und
  den fünf Optionen; Gerätemodell „World of Warcraft“ bzw. „World of Warcraft
  Classic Era“; Diagnose bereinigt unter `character` auch im echten
  Mythic+-Profil (nur der Realm bleibt); das Mythic+-Profil enthält
  `current_period`. Nicht live belegbar: fremde Namen, weil kein Charakter in
  einer Gilde ist und es keine Mythic+-Läufe mit Gruppe gab, sowie `best_runs`
  (keine Läufe in Season 18); wie die Oberfläche die Zustände anzeigt, ist
  über das MCP nicht sichtbar. Kein Eintrag im Log.
- **0.21.x:** 298 automatische Tests. 0.21.1: 2 Tests für Geräte ohne das
  veraltete `config_entries` (Funktion und ganzer Aufruf von `refresh` mit
  Gerät); Gegenprobe: mit dem alten Zugriff schlagen beide fehl. **Live geprüft
  mit 0.21.0** (30.10.2026, Home Assistant 2026.10.4, acht Charaktere in EU
  Retail und Classic Era): Optionsdialog mit Vorgaben 15 / 60 / 360 und neun
  Gruppen; „selten unter Details“ abgelehnt, Werte unter dem Minimum lehnt
  Home Assistant selbst ab (englische Meldung „Value 30.0 is too small“);
  Gruppe Quests aus und wieder an, die sieben Sensoren behalten ihre
  Entitäts-ID; Profiltakt 5 Minuten im Debug-Log nachgewiesen (Abfragen um
  08:46:56 und 08:51:56, Details und Spielwelt unverändert); refresh für einen
  Charakter, alle acht (8,2 s, kein HTTP 429) und die Spielwelt EU, jeweils
  nur die gewählten Abfragen; get_character für einen Retail-Charakter (alle 19 Felder wie die
  Sensoren, Realm als Slug und in Großbuchstaben) und für einen
  Classic-Era-Charakter (ohne Mythic+, Avatar aus `classic1x-eu`); beide
  Fehlermeldungen wörtlich. Dabei fiel die Warnung zu `config_entries` auf
  (behoben in 0.21.1). 0.21.0: 17 Tests für die Aktionen
  (refresh ohne Gerät oder mit leerer Geräteliste für alle Charaktere samt seltener Endpunkte und Brackets
  ohne Sensor, nur gewähltes Gerät, Spielwelt-Gerät, unbekanntes Gerät,
  Fehlermeldung bei gescheiterter Abfrage, Eintrag nicht geladen;
  get_character mit Antwort ohne Gerät und Untereintrag, Realm per Slug in
  beliebiger Schreibweise und zwischengespeicherter Realm-Liste, ohne
  Mythic+-Lauf, Classic ohne Mythic+-Abfrage, unbekannter Realm oder
  Charakter, API-Fehler, Wahl des Eintrags; services.yaml, Schemas und
  Übersetzungen stimmen überein).
- **0.20.x:** 279 automatische Tests. 0.20.0: 11 Tests für Takte und Gruppen
  (Vorgaben unverändert; gewählte Takte für Profil, Details und seltene
  Details samt Endpunkten ohne Entität; Brackets und WoW-Marke ohne Sensor im
  seltenen Takt; Dialog speichert ganze Minuten, lehnt seltene unter Details
  und Werte außerhalb der Grenzen ab; ausgeschaltete Gruppen ohne Abfragen,
  Entitäten und Ereignisse; Aus- und Einschalten behält die Entitäts-ID;
  Nachlegen beachtet ausgeschaltete Gruppen). Zwei Tests angepasst: Der
  Übersetzungstest prüft die Fehler des Optionsdialogs unter `options`, der
  Optionstest von 0.19.0 sucht das Sprachfeld unter mehreren Feldern.
  Gegenprobe: zehn Teile einzeln ausgebaut (Takt Profil, Takt Details,
  Zuordnung der Vorgaben, seltener Takt ohne Entität, für Brackets und für die
  WoW-Marke, Gruppen ohne Abfrage, Gruppen ohne Entitäten, ganze Minuten,
  seltene nicht unter Details), jedes Mal schlug ein Test fehl. **Nicht live
  geprüft.**
- **0.19.x:** 268 automatische Tests. 0.19.1: 11 Tests für Störungen der API
  (gleichzeitige Abfragen holen ein Token; Token-Antwort ohne Token, als
  Liste und als HTML, beim Start mit neuem Versuch; Profil als HTML und als
  Liste ohne „Unexpected error“ im Log; Code-Tausch der Anmeldung mit HTML und
  Liste; Berufsnamen mit abgelehnten Zugangsdaten und mit 429). Gegenprobe:
  acht Teile einzeln ausgebaut (Sperre beim Token, Prüfung auf `access_token`,
  ValueError beim Token, bei Abfragen und beim Code-Tausch, nur JSON-Objekte,
  Berufsnamen mit abgelehnten Zugangsdaten und Abbruch bei 429), jedes Mal
  schlug ein Test fehl. **Nicht live geprüft.** Dazu zwei Texte aus dem
  Live-Test (kürzere Auswahl „Sprache der Region (wie bisher)“, „Gefundene
  Charaktere …: 1“ statt „1 Charaktere gefunden“). **Live geprüft mit 0.19.0**
  (29.10.2026, Home Assistant 2026.10.4, acht Charaktere in EU Retail und
  Classic Era): Optionsdialog mit Vorgabe und elf Einträgen; Umstellen auf
  English lädt neu, alle Abfragen mit `en_GB`, Klasse, Volk, Titel,
  Heldentalente, Beruf, Ausrüstung und Bevölkerung auf Englisch, Entitäts-IDs
  unverändert, Verlauf erhalten (geprüft an einem Berufssensor), kein Fehler
  im Log; Karten „WoW Arsenal“ und „WoW
  Talentbaum“ mit englischen Texten; Charaktersuche über die Anmeldung mit
  englischer Klasse; zurück auf „Sprache der Region“ mit allen Werten wie
  vorher. Das Anlegen neuer Entitäten ohne Neuladen (0.18.0) lief beim
  Schreiben noch. 0.19.0: 29 Tests für die Sprache der
  API-Texte (Locale je Region und Sprache mit Rückfall auf die Region, 16
  Fälle; Auswahl „Sprache von Home Assistant“, 6 Fälle; ohne Option wie bisher;
  gewählte Sprache in allen Abfragen und in der Diagnose; Sprache von Home
  Assistant; Optionsdialog mit Vorgabe, Speichern lädt genau einmal neu;
  Realm-Liste beim Hinzufügen von Hand; Charaktersuche aus „Abgleichen“ und
  „Hinzufügen“). Gegenprobe: zehn Teile einzeln ausgebaut (Locale in den
  Abfragen, Sprache an den Client, Optionen im Stand für das Neuladen,
  Optionsdialog, Sprache beim Abgleichen, beim Hinzufügen und an die
  Charaktersuche, Sprache von Home Assistant, Rückfall auf die Region, Locales
  in der Diagnose), jedes Mal schlug ein Test fehl. **Nicht live geprüft.**
- **0.18.x:** 228 automatische Tests. 0.18.0: 9 Tests für Entitäten ohne
  Neuladen (neuer Beruf; Gildenbeitritt mit Werten nach der nächsten
  Detailabfrage; erste Wertung in 2v2, danach stündlich, ohne doppelte
  Entitäten; deaktivierter Endpunkt bleibt aus; in Classic Erfolge mit
  Ereignis, Zusatzplatz, Bilder, WoW-Marke und ein später antwortender Realm).
  Vier Tests an das neue Verhalten angepasst: Endpunkte ohne Entität, Brackets
  ohne Sensor, WoW-Marke ohne Sensor und Jägerbegleiter nach gescheiterter
  erster Abfrage werden jetzt alle 6 Stunden statt bis zum Neuladen gar nicht
  mehr abgefragt. Gegenprobe: zwölf Teile einzeln ausgebaut (je ein Listener
  in Sensor für Profil, Details und Spielwelt, in Binärsensor, Ereignis und
  Bild; seltene Abfrage von Endpunkten ohne Entität, von Brackets ohne Sensor
  und der WoW-Marke ohne Sensor; stündliche Abfrage neuer Brackets und der
  neuen WoW-Marke; jede Entität nur einmal), jedes Mal schlug ein Test fehl.
  Die letzte Probe fiel erst nach einer Prüfung des Logs auf doppelte IDs auf,
  weil Home Assistant doppelte Entitäten selbst verwirft. **Nicht live
  geprüft.**
- **0.17.x:** 219 automatische Tests. 0.17.2: 9 Tests für die Korrekturen
  (Start ohne Token wird wiederholt und legt danach Beruf, PvP-Bracket und
  Realm-Entitäten an; Realm-Entitäten in Retail auch ohne erste Antwort;
  Mythic+-Fehler beim Start und später, Profil bleibt verfügbar und die Wertung
  behält ihren Stand; neue Client-ID über „Neu konfigurieren“ und über die
  erneute Anmeldung ohne doppelte Spielwelt-Entitäten; Rückwechsel auf eine
  Client-ID mit verwaisten Entitäten ohne Fehler; Forever mit 403 für den
  ersten und für alle Kandidaten). Drei Tests angepasst: Abgelehnte
  Zugangsdaten beenden den Start jetzt mit erneuter Anmeldung; die erneute
  Anmeldung braucht dafür einen gültigen Start; das Nachtragen der
  Charakter-ID zählt jetzt die Starts, der alte Vergleich von `runtime_data`
  fand das doppelte Laden aus 0.17.1 nicht. Gegenprobe: sieben Teile der
  Korrektur einzeln ausgebaut (Token-Prüfung beim Start, Realms aus den
  Charakteren, Umschreiben der unique_id, Schutz vor belegter unique_id, alter
  Mythic+-Stand, ID im Stand des Starts, 403 überspringen), jedes Mal schlug
  ein Test fehl. **Nicht live
  geprüft.** 0.17.1: 4 Tests für die Anmeldung aus
  „Charakter hinzufügen“ (Hilfsdialog gibt den Rücksprung weiter und ist nicht
  unter „Entdeckt“, abgelehnte Anmeldung, Schließen beendet den Hilfsdialog) und
  für einen während des Starts gelöschten Charakter (keine Meldung „unknown
  subentry“). Gegenprobe: fünf Teile einzeln ausgebaut (keine Weitergabe, eigene
  Quelle statt „user“, kein Beenden beim Schließen, eingerichtete Charaktere
  nicht erkannt, gelöschte Charaktere trotzdem eingerichtet), jedes Mal schlug
  ein Test fehl. Dazu 4 Tests aus dem Live-Test: Abgleich mit drei Charakteren
  richtet alle ein und lädt nur einmal neu; ein während eines Neustarts
  angelegter Charakter wird danach eingerichtet; jede Änderung lädt neu, auch
  zurück zu einem früheren Stand; HTTP 403 der Forever-Kandidaten zählt nicht
  als Fehlabfrage. Gegenprobe: vier Teile der Korrektur einzeln ausgebaut (kein
  Abgeben vor dem Vergleich, kein Merker für das laufende Neuladen, kein
  Nachladen nach einer Änderung während des Starts, 403 als Fehler), jedes Mal
  schlug ein Test fehl. Zwei Teile lassen sich so nicht trennen: das Aufräumen
  des Merkers (ein neues Neuladen überschreibt ihn ohnehin) und der Stand vom
  Beginn des Starts (das Nachladen deckt ihn mit ab). **Live geprüft mit
  0.17.1** (29.10.2026, dasselbe Konto): Menü in „Charakter hinzufügen“,
  Anmeldung über den Hilfsdialog, Auswahlliste mit „Fehlgeschlagene Abfragen:
  0“, mehrere Charaktere auf einmal angelegt, alle mit Gerät; Reauth nach dem
  Erneuern des Secrets („Authentifizierung abgelaufen“, mit dem neuen Secret
  behoben). Nach einem Kopieren von Hand ohne den Ordner `translations/` fehlten
  die Menütexte; mit dem ganzen Ordner stimmten sie. **Live geprüft mit 0.17.0**
  (29.10.2026, Konto mit Retail- und Classic-Era-Charakteren in EU): Hinweis im
  Dialog „Charakter hinzufügen“, Anmeldung, Rücksprung über My Home Assistant
  und Auswahlliste mit den sechs noch nicht eingerichteten Charakteren;
  eingerichtete, auch der Classic-Era- Charakter, erschienen nicht. Dabei fielen
  die beiden Fehler auf, die 0.17.1 behebt: Nach dem Anlegen mehrerer Charaktere
  bekamen sie kein Gerät, und die Liste nannte 8 Fehlabfragen (HTTP 403 der
  Forever-Kandidaten). **Nicht live geprüft:** Neueinrichtung mit Anmeldung,
  Companion-App, Fehlerfälle der Anmeldung, Classic Progression und Anniversary
  mit Konto, Forever. 0.17.0: 202 automatische Tests, davon 17 neu. 3 prüfen,
  dass die Übersetzungen keine URLs enthalten (Regel von hassfest). 14 gelten
  der Battle.net-Anmeldung: Login-Adresse mit Scope und Redirect-URL,
  Code-Tausch mit derselben Redirect-URL, Charaktersuche nur mit dem Login-Token
  (24 Abfragen), Auswahl nach Level, Untereinträge mit denselben Daten und
  `unique_id` wie von Hand, ohne Auswahl, Forever-Kandidat, gezählte
  Fehlabfrage, sechs Abbruchgründe, fehlende Adresse; Abgleich bietet nur neue
  Charaktere an (per Name und per ID erkannt), nichts Neues, gleicher Name mit
  anderer ID. 3 bestehende Tests an die neuen Menüs angepasst. Gegenprobe: elf
  Fehler einzeln eingebaut (Scope nicht geprüft, Scope nicht angefordert,
  falsche Redirect-URL beim Code-Tausch, Abgleich nur per Name, nur per ID, ohne
  Filter, Login-Token wie Client-Token behandelt, Client-Token statt
  Login-Token, Fehlabfragen nicht gezählt, erster Forever-Kandidat gewinnt auch
  ohne Konto, abgelehnte Anmeldung nicht abgebrochen), jedes Mal schlug
  mindestens ein Test fehl. Von Hand mit curl gegen die echte API geprüft
  (29.10.2026, Konto mit Retail- und Classic-Era-Charakteren in EU): Code-Tausch
  per HTTP Basic, Antwort ohne `refresh_token` (auch mit `offline_access`, mit
  und ohne `openid` und `prompt=consent`), `/profile/user/wow` in 16
  Kombinationen aus Region und Spielversion, Feldnamen je Charakter. **Nicht
  live geprüft:** der Ablauf in Home Assistant selbst (Fenster, Rücksprung über
  My Home Assistant, Auswahl), Classic Progression und Anniversary mit Konto,
  Forever.
- **0.16.x:** 185 automatische Tests. 0.16.1: 4 Tests für das Apex-Talent
  (alle Stufen: Rang 4/4, Stufen in Spielreihenfolge mit Name, Beschreibung und
  Symbol; ohne und mit nur der ersten Stufe: 0/4 und 1/4; mehrere Knoten in der
  untersten Zeile: kein Apex), der alte Test zum mehrfach genannten Knoten
  entfällt. Gegenprobe: sechs Fehler einzeln eingebaut (Apex ohne
  Einzelknoten-Prüfung, höchster Rang statt Summe, Höchstzahl aus dem Baum,
  Reihenfolge des Profils, Symbole der Stufen nicht geladen, Talent der ersten
  Stufe fehlt), jedes Mal schlug mindestens ein Test fehl. Karte in Chromium mit
  erfundenen Daten: „4/4“ mit goldenem Rahmen, Details mit drei Stufen, ohne
  Fehler in der Konsole. **Nicht live geprüft:** 0.16.1 in Home Assistant; wie
  ein teilweise gelernter Apex im Profil aussieht (nur eine echte Probe mit allen
  Stufen). 0.16.0: keine neuen Tests, geändert
  ist nur die Karte „WoW Arsenal“ (JavaScript): Zusatzplätze außerhalb von
  Retail in der Waffenreihe. In Chromium mit erfundenen Daten gezeichnet:
  Retail 200 und 380 Pixel breit pixelgleich mit 0.15.2; Classic Era mit
  einem belegten und einem leeren Zusatzplatz (380 Pixel eine Reihe, 200
  Pixel zwei Reihen), Classic Progression mit Itemlevel; Fenster per
  Antippen auch für den Zusatzplatz, ohne Fehler in der Konsole. **Nicht live
  geprüft:** Welche Zusatzplätze Classic liefert, ist nicht dokumentiert, und
  die Classic-Charaktere der Live-Instanz haben derzeit keinen.
- **0.15.x:** 182 automatische Tests. 0.15.2: keine neuen Tests, geändert
  ist nur die Karte (JavaScript). Die Kachel „Erfolge“ zeigt die Anzahl der
  Erfolge statt der Erfolgspunkte. In Chromium mit erfundenen Daten 380 und
  200 Pixel breit gezeichnet, ohne Fehler in der Konsole. **Nicht live
  geprüft:** die Karte in 0.15.2. 0.15.1: keine neuen Tests, geändert
  ist nur die Karte (JavaScript). Live in Home Assistant 2026.10.4 (Handy,
  Abschnittsansicht) geprüft: alle 18 Itemlevel, Itemlevel 253, M+ 170
  (`api_rating`), Raid LFR 6/7 und 3 Amber-Punkte (Hals, beide Ringe) stimmen
  mit den Sensoren überein; die Karte war aber nur halb so breit wie der
  Abschnitt und kürzte die Kennzahlen ab. In Chromium mit erfundenen Daten
  200 und 380 Pixel breit gezeichnet: Kennzahlen in 200 Pixel zwei Spalten,
  in 380 Pixel eine Reihe, Fenster per Antippen, ohne Fehler in der Konsole.
  **Nicht live geprüft:** die Karte in 0.15.1. 0.15.0: Der Test zur Auslieferung prüft
  beide Karten, der Test zum Laden im Frontend beide Module. Gegenprobe: drei
  Fehler einzeln eingebaut, jedes Mal schlug mindestens ein Test fehl. Die
  Karte „WoW Arsenal“ selbst (JavaScript) ist nicht automatisch getestet:
  Gezeichnet in Chromium mit erfundenen Daten (Retail Deutsch, Classic Era
  Englisch, leere Plätze, leere Sockel, Tooltip mit Maus, Fenster per Antippen,
  Schließen mit Escape), 400 und 600 Pixel breit, ohne Fehler in der Konsole.
  **Nicht live geprüft:** die Karte in Home Assistant.
- **0.14.x:** 181 automatische Tests. 0.14.1: 4 Tests für das Abfragelimit
  (429, eine Sekunde Pause, dann Antwort; zweimal 429 ergibt einen Fehler;
  Symbole der Talente und der Items brechen nach erneutem 429 bis zum
  nächsten Takt ab). Gegenprobe: vier Fehler einzeln eingebaut, jedes Mal
  schlug mindestens ein Test fehl. Anlass: Nach jedem Neustart fehlten
  andere Talent-Symbole (Clambo 7, dann 9), also kein dauerhaftes Fehlen bei
  Blizzard; dass es 429 war, ist nicht belegt, weil gescheiterte Symbole nur
  im Debug-Log stehen. 0.14.0: 3 Tests für die Karte
  „WoW Talentbaum“ (Datei wird ausgeliefert; mit Frontend als Modul geladen,
  Version im Pfad; ohne Frontend nicht). Gegenprobe: drei Fehler einzeln
  eingebaut, jedes Mal schlug mindestens ein Test fehl. Die Karte selbst
  (JavaScript) ist nicht automatisch getestet: Gezeichnet in Chromium mit
  erfundenen Daten im Aufbau des Sensors (drei Bäume, Wahlknoten, Ränge,
  fehlende Symbole, Rang über Höchstrang), in 460 und 1000 Pixel Breite, ohne
  Fehler in der Konsole. **Nicht live geprüft:** die Karte in Home Assistant.
- **0.13.x:** 174 automatische Tests. 0.13.0: 8 Tests für den Sensor
  „Talentbaum“ (Knoten mit Lage, Rang, Wahl, Symbol und Pfeilen; Heldenknoten
  nur im aktiven Heldenbaum; Knoten ohne Talent fallen weg; mehrfach genannter
  Knoten; Baum einmal je Start, Symbole erst nach dem Anlegen; Fehler wird
  wiederholt; deaktivierter Sensor; Endpunkt bleibt ohne Sensor
  „Spezialisierung“ aktuell; kein Sensor in Classic). Der Konsistenz-Test
  erkennt `_unrecorded_attributes` jetzt auch über mehrere Zeilen. Gegenprobe:
  zehn Fehler einzeln eingebaut, jedes Mal schlug mindestens ein Test fehl.
  Grundlage ist die echte Antwort vom 28.10.2026 (Magier, Frost). **Nicht live
  geprüft:** diese Version.
- **0.12.x:** 166 automatische Tests. 0.12.2: Die Diagnose-Tests nutzen die
  Verweise wie in der echten Antwort und prüfen, dass der Baum der
  Spezialisierung Vorrang hat und der Klassenbaum nur ohne ihn geladen wird;
  Gegenprobe: zwei Fehler einzeln eingebaut, jedes Mal schlug mindestens ein
  Test fehl. 0.12.1: 4 Tests für die Diagnose
  (Talentbaum des aktiven Loadouts mit Knoten, Wahlknoten, Heldentalenten und
  Schwellen, ohne Tooltip-Texte; Verweis ohne Spezialisierung; Fehler der
  Abfrage; keine Abfrage ohne Verweis),
  ein bestehender Test prüft die vergebenen Talente jetzt mit IDs statt Anzahl.
  Gegenprobe: acht Fehler einzeln eingebaut, jedes Mal schlug mindestens ein
  Test fehl. Live geprüft mit einem Retail-Charakter: Die Knoten-IDs passen
  (siehe Diagnose unter [Ändern, Hinweise und Diagnose](#ändern-hinweise-und-diagnose)). 0.12.0: 4 Tests für den Sensor „Talente“
  (Baum mit den meisten Punkten, nur die aktive Gruppe, Punkte und Talente je
  Baum, Aktualisierung ohne Sensor „Spezialisierung“; Gleichstand; kein Sensor
  ohne Punkte; kein Sensor in Retail). Gegenprobe: sieben Fehler einzeln
  eingebaut, jedes Mal schlug mindestens ein Test fehl; dabei fiel auf, dass
  der Endpunkt ohne Zuordnung des Sensors nach dem Start nicht mehr abgefragt
  würde, das prüft jetzt ein Test. **Nicht live geprüft:** Progression und
  Anniversary; dort nennen nur die Typdefinitionen `specialization_groups`.
- **0.11.x:** 158 automatische Tests. 0.11.3: 3 neue Tests (Ausrüstung ohne
  Itemlevel zeigt außerhalb von Retail den Namen, in Retail nicht; Endpunkte ohne
  Entität werden nach dem Start nicht mehr abgefragt, Endpunkte mit Entität
  schon), dazu prüft der Test für Jägerbegleiter nach einem Fehler beim Start
  jetzt, dass der Endpunkt erst nach dem Neuladen wieder abgefragt wird.
  Gegenprobe: sechs Fehler einzeln eingebaut, jedes Mal schlug mindestens ein
  Test fehl. 0.11.2: 3 Tests für die Namen der
  Transmog-Gegenstände (Namen aus Ausrüstung und `item/{id}`, einmal je
  Gegenstand; Nachschlagen scheitert; Classic-Namespace) und die Prüfung im
  bestehenden Aussehen-Test, dass ohne passende ID nichts nachgeschlagen wird;
  Gegenprobe: fünf Fehler einzeln eingebaut, jedes Mal schlug mindestens ein
  Test fehl. 0.11.1: 3 Tests für die PvP-Abfragen
  (Brackets ohne Sensor nicht mehr, ohne Bracket-Sensor gar nicht, Bracket mit
  Sensor auch nach einem 404); Gegenprobe: vier Fehler einzeln eingebaut, jedes
  Mal schlug mindestens ein Test fehl. 0.11.0: 149 Tests, darunter 6 neue für Aussehen,
  PvP-Brackets und Gildenmitglieder (Attribute am Level-Sensor und deren
  Aktualisierung, keine Abfrage des Aussehens ohne Level-Sensor, Sensor nur für
  Brackets mit Daten, alter Stand bei einem Fehler, Namespaces in Classic,
  Klassennamen je Klasse einmal nachgeschlagen) und die Mitgliederliste im
  bestehenden Gilden-Test. Gegenprobe: neun Fehler einzeln eingebaut, jedes Mal
  schlug mindestens ein Test fehl; dabei fiel auf, dass die Testdaten die
  Sortierung nach Rang nicht prüften, das ist behoben. **Nicht live geprüft:**
  Die Felder stammen aus den Typdefinitionen (für Aussehen und PvP-Brackets nur
  Retail), nicht aus echten Antworten.
- **0.10.x:** 143 automatische Tests. Seit 0.10.2 dazu 6 Tests für die
  PR-Vorlage: „Keine: <Grund>“ unter „Belege“ gilt auch als Listenpunkt
  („- Keine: …“), ohne Grund weiter nicht; Gegenprobe: vier Fehler einzeln
  eingebaut, jedes Mal schlug mindestens ein Test fehl. 0.10.2: 3 Tests für die WoW-Marke
  (Classic ohne Preis beim Start wird nicht weiter abgefragt, Classic mit Preis
  und Retail ohne Preis schon); Gegenprobe: vier Fehler einzeln eingebaut, jedes
  Mal schlug mindestens ein Test fehl. 0.10.1: 3 Tests für die Klassenprüfung
  der Jägerbegleiter (Nicht-Jäger nur einmal abgefragt, spätere 404 bei einem
  Jäger sind nicht endgültig, auch zweimal hintereinander, Fehler ohne 404
  werden wiederholt); Gegenprobe: fünf Fehler einzeln eingebaut, jedes Mal
  schlug mindestens ein Test fehl. Seit 0.10.0 dazu 29 Tests für die
  Konsistenz des Repos und die PR-Vorlage (ohne neue Version, weil nur Tests
  und Prüfungen dazukamen). 0.10.0: 102 Tests, darunter 8 für die Jägerbegleiter: Werte
  und Attribute, kein Sensor für Nicht-Jäger (404) und bei gescheiterter erster
  Abfrage, Namespace in allen drei Classic-Versionen und Forever, keine Abfrage
  bei deaktiviertem Sensor, gekürzte Diagnose. Gegenprobe: jede der sechs
  Schutzmaßnahmen einzeln entfernt, jedes Mal schlug mindestens ein Test fehl.
  **Nicht live geprüft:** Kein Jäger unter den Test-Charakteren; die Feldnamen
  stammen aus den Typdefinitionen, nicht aus einer echten Antwort.
- **0.9.x:** 94 automatische Tests, darunter 10 für Classic: Namespaces aller
  drei Classic-Versionen beim Hinzufügen, nur dokumentierte Endpunkte und
  Symbole, keine Sensoren ohne Wert, Zusatzplätze der Ausrüstung, Name des
  Spielwelt-Geräts. Gegenprobe: Jede der 13 Schutzmaßnahmen einzeln entfernt,
  jedes Mal schlug mindestens ein Test fehl. **Nicht live geprüft:** Für Classic
  lag kein API-Zugang mit Classic-Charakter vor; ob die Antwortfelder von Classic
  denen von Retail entsprechen, ist offen.
- **0.8.x:** 84 automatische Tests, hassfest ohne Fehler. 0.8.0 am 27.10.2026
  über HACS installiert und live geprüft: keine Meldung der Integration im Log,
  kein Reparaturhinweis, keine Entität nicht verfügbar. Die Ereignisse „Neu
  gesammelt“ und „Level gestiegen“ sind angelegt; ausgelöst hat noch keines, weil
  seit dem Start nichts Neues dazukam. Symbole von Klasse, Spezialisierung und
  Berufen sowie die Raid-Bilder kommen an. Abgeschlossene Quests: 2.479 laut
  `quests/completed`, die Spielstatistik „Quests abgeschlossen“ (ID 98) nennt
  2.505. Woher die 26 Quests Unterschied kommen, ist nicht geklärt; vermutlich
  zählt die Statistik wiederholbare Quests mehrfach. Nicht live geprüft: der
  Gilden-Sensor (kein Charakter in einer Gilde).
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
- **WoW Classic** ist nur automatisch getestet (siehe 0.9.x).

## Tests

```bash
pip install pytest-homeassistant-custom-component==0.13.316 ruff==0.16.9
ruff check . && ruff format --check .
pytest tests   # pytest.ini setzt asyncio_mode = auto
```

Dieselben Schritte laufen bei jedem Push und Pull Request im Workflow
„Pruefung“, zusammen mit hassfest und der HACS-Prüfung.

`tests/test_repo_konsistenz.py` prüft, dass Version, README (auch die Testzahl
oben im Teststand), Versionshinweise, Übersetzungen und Endpunkte zusammenpassen.
Die Testzahl im README stimmt nur, wenn jede Änderung an den Tests sie mit
nachzieht.

**Pull Requests** folgen der Vorlage `.github/pull_request_template.md`. Der
Workflow „PR-Vorlage“ prüft bei jedem neuen Stand und jeder Änderung der
Beschreibung, dass alle Abschnitte ausgefüllt und alle Punkte der Checkliste
angekreuzt sind (nicht Zutreffendes mit „entfällt: <Grund>“). Ändert ein PR die
Integration, verlangt er eine neue Version in `manifest.json` und
Versionshinweise dazu. Lokal: `PR_BODY="$(cat beschreibung.md)" python3
.github/scripts/pruefe_pr.py`.

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
