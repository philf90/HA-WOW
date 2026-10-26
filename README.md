# WoW Charakter – Skizze einer Home-Assistant-Integration

Liest die Profildaten eines World-of-Warcraft-Charakters über die offizielle
Battle.net API. Version 0.1.0, Skizze zum Weiterbauen.

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

## Voraussetzungen

1. Kostenlosen API-Client auf <https://develop.battle.net> anlegen, Client-ID und
   Secret notieren.
2. Ordner `custom_components/wow_character` nach `config/custom_components/`
   kopieren und Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → Integration hinzufügen → „WoW Charakter“.
   - Schritt 1: Client-ID, Secret, Region und Spielversion. Dabei wird die
     Realm-Liste der Region geladen (`/data/wow/realm/index`).
   - Schritt 2: Realm aus der Liste wählen, Charakternamen eingeben.
   Pro Charakter einen Eintrag anlegen.

Automatisch getestet gegen Home Assistant 2026.2.3 (9 Tests). Am 26.10.2026 mit einem
Retail-Charakter unter Home Assistant 2026.10.4 eingerichtet: Realm-Liste, Profil und
Mythic+-Profil kamen von der echten API, ohne Fehler im Protokoll. Noch nicht nachgewiesen:
die regelmäßige Aktualisierung alle 15 Minuten. WoW Forever ist ungetestet.

## WoW Forever

Blizzard hat den API-Namespace für Forever noch nicht dokumentiert (Start
04.11.2026). Die Integration probiert beim Einrichten die Kandidaten aus
`const.py` (`GAME_VERSIONS["forever"]["namespaces"]`) der Reihe nach: Der erste,
unter dem die API eine Realm-Liste liefert, wird gespeichert. Die Kandidaten sind **unbestätigt**. Sobald Blizzard den
Namespace nennt, dort eintragen; schlägt die Einrichtung fehl, ist das die
wahrscheinlichste Ursache.

## Grenzen

- Profildaten aktualisiert Blizzard erst, wenn sich der Charakter ausloggt.
  Abfrage alle 15 Minuten.
- Client-ID und Secret werden je Charakter-Eintrag gespeichert.
- Kein Erneut-Anmelden-Dialog, wenn das Secret ungültig wird: Eintrag löschen
  und neu anlegen.

## Tests

```bash
pip install pytest-homeassistant-custom-component==0.13.316
pytest tests   # pytest.ini setzt asyncio_mode = auto
```
