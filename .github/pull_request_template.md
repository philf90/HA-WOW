<!--
Pflichtvorlage. Die Prüfung „PR-Vorlage“ schlägt fehl, solange ein Abschnitt
fehlt oder leer ist, ein Feld nach dem Doppelpunkt leer bleibt oder ein
Kästchen offen ist. Trifft ein Punkt nicht zu: Kästchen ankreuzen und
„entfällt: <Grund>“ dahinter schreiben. Kommentare wie dieser dürfen bleiben.
-->

## Zusammenfassung

<!-- Was ändert sich für Nutzer? 1–3 Sätze. -->

## Belege

<!-- Quellen für Endpunkte, Namespaces und Feldnamen: Blizzard-Doku (Link),
Typdefinitionen (Paket und Version), echte Antwort (Diagnose).
Ohne externe Quelle: „Keine: <Grund>“. -->

## Änderungen

<!-- Ein Punkt je Datei oder Bereich. -->

## Verhaltensänderungen

<!-- Was ändert sich für bestehende Installationen, je Spielversion (Retail,
Classic, Forever)? Neue oder entfallene Entitäten, geänderte Entitäts-IDs,
zusätzliche API-Abfragen. Sonst: „Keine: <Begründung>“. -->

## Tests

- Automatische Tests:
- Gegenprobe:
- Live geprüft:

<!-- Automatische Tests: Anzahl gesamt und neu, z. B. „102, davon 8 neu“.
Gegenprobe: welche Schutzmaßnahmen einzeln entfernt, mit Ergebnis.
Live geprüft: „ja (HA-Version, Spielversion, was)“ oder „nein (Grund)“. -->

## Nicht geprüft / offen

<!-- Was ist unbelegt oder ungetestet? „Nichts“ nur, wenn alles live geprüft ist. -->

## Checkliste

- [ ] `ruff check .` und `ruff format --check .` ohne Befund
- [ ] `pytest tests` vollständig grün, auch `test_repo_konsistenz.py`
- [ ] Nur Endpunkte und Spieldaten, die die Blizzard-Doku für die Spielversion nennt
- [ ] Texte in `strings.json`, `en.json` und `de.json`; Symbol in `icons.json`
- [ ] Lange Listen in `_unrecorded_attributes` und in der Diagnose gekürzt
- [ ] README: Entitäten, Attribute und Teststand mit aktueller Testzahl
- [ ] Version in `manifest.json` erhöht, `.github/release-notes/v<Version>.md` angelegt
- [ ] Keine Client-ID, kein Secret und keine echten Charakterdaten im Diff
