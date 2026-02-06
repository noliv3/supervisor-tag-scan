# Agent-Regeln und Projektvertrag

## Primärvertrag

1) Legacy-Kompatibilität ist nicht verhandelbar.
- Legacy HTTP API muss identisches Verhalten wie `pixai-sensible-main/scanner_api.py` liefern.
- Statuscodes, Limits, Header, Content-Types, Feldnamen, Error-Payloads sind Teil des Vertrags.
- Keine kosmetischen Changes an Legacy-Responses.

2) Absicherung zuerst.
- Tokenpflicht für alle geschützten Endpoints.
- Limits und Validierung strikt wie Legacy.
- Logging kompatibel.

3) Persistenz in SQLite.
- DB ist Source of Truth für Tokens, Stats, Scan Results.
- Dateien nur als optionaler Bildspeicher.

## Rollen (mentales Modell)

- Compatibility Layer
  - Implementiert Legacy HTTP API (`/token`, `/stats`, `/check`, `/batch`) exakt.
  - Implementiert LocalSupervisor Bridge (`/scan_image`) ohne Breaking Changes.

- Auth Layer
  - Validiert Legacy Token-Header und LocalSupervisor Token-Field.
  - Verwaltet Token-Lifetime (Legacy 30 Tage).

- Pipeline Layer
  - Führt Legacy-Pipeline aus und liefert Legacy-Keyspace:
    `modules.nsfw_scanner`, `modules.tagging`, `modules.deepdanbooru_tags`,
    `modules.statistics`, `modules.image_storage`, plus dynamische Module.
  - Fehler isoliert pro Modul als `{"error":"..."}`.

- Storage Layer
  - Schreibt Scan Results in SQLite.
  - Statistiken und Trends in SQLite.
  - Optionaler Image-Dump, aber keine Metadaten-Dateien als Wahrheit.

## Arbeitsreihenfolge

1) Doku und Vertrag fixieren (diese Änderung).
2) Legacy HTTP API kompatibel implementieren.
3) Auth vereinheitlichen, Legacy Tokens akzeptieren.
4) Pipeline exakt portieren, Zusatzmodule aus `modules.cfg` berücksichtigen.
5) DB-Schema finalisieren, Migration von `tokens.json` und `scanned/statistics.json`.
6) Cleanup.

## Output-Regel für Agenten

- Wenn Dateien geändert werden, immer die komplette Datei ausgeben.
- Keine Diffs, keine Ausschnitte.

## Nicht-Ziele (vorerst)

- WDTagger oder neue Modelle.
- Optimierungen, die Legacy-Verhalten ändern.
- Refactors ohne direkten Nutzen für Phase 1–3.
