# SuperVisor-tag-scan

Residenter Python-Service zur Medienanalyse. Ersetzt den Legacy-Scanner „PixAI Sensible Scanner“ ohne sichtbare Änderungen für bestehende Clients und bleibt gleichzeitig kompatibel zu LocalSupervisor (`POST /scan_image`).

## Zielzustand

1. Legacy wirkt weiter vorhanden.
- Alte Clients nutzen weiterhin dieselben Endpoints, Formate, Statuscodes, Limits und Response-Strukturen.
- Keine sichtbaren Unterschiede für Anwender.

2. Harte Absicherung.
- Tokenpflicht für alle geschützten Endpoints.
- Robuste Input-Validierung, Größenlimits, saubere Fehlerpfade.
- Logging wie im Legacy.

3. Persistenz in SQLite statt Dateimetadaten.
- Tokens, Stats, Scan-Resultate, Tag-Trends in SQLite.
- Bilder dürfen weiterhin im Dateisystem liegen, Metadaten nicht.

4. Erweiterbarkeit.
- Neue Modelle als Module/Plugins, ohne Legacy zu brechen.
- WDTagger später.

## APIs

Dieses Repo bedient zwei API-Familien parallel.

### A) Legacy HTTP API (PixAI Sensible Scanner kompatibel)

Diese Oberfläche muss exakt dem Verhalten von `pixai-sensible-main/scanner_api.py` entsprechen.

Endpoints:

1) GET /token
- Query: `email=<mailadresse>`
- Optional: `renew=1` (Prüfung erfolgt im Legacy per „renew in query“, nicht per Wert)
- Response: `text/plain; charset=utf-8` (nur der Token-String)
- Fehler:
  - 400 JSON: `{"error":"missing email"}`

2) GET /stats
- Header: `Authorization: <TOKEN>`
- Response: JSON Statistiken aus Legacy-Modul `modules.statistics`
- Fehler:
  - 403 JSON: `{"error":"forbidden"}`

3) POST /check
- Header: `Authorization: <TOKEN>`
- Content-Type: `multipart/form-data`
- Form-Field: `image` (Datei)
- Max: 10 MB
- Response: JSON Dictionary mit Keys je Modulname, z. B.
  - `modules.nsfw_scanner`
  - `modules.tagging`
  - `modules.deepdanbooru_tags`
  - `modules.statistics`
  - `modules.image_storage`
  - plus zusätzliche Module aus `modules.cfg` (per ModuleManager)
- Fehler:
  - 403 JSON `{"error":"invalid content-type"}` wenn kein multipart
  - 400 JSON `{"error":"image missing"}`
  - 413 JSON `{"error":"payload too large"}`
  - 400 JSON `{"error":"invalid image"}`

4) POST /batch
- Header: `Authorization: <TOKEN>`
- Content-Type: `multipart/form-data`
- Form-Field: `file` (GIF/Video/Container)
- Max: 25 MB
- Response: JSON aus `gif_batch.scan_batch`
- Fehler:
  - 400 JSON `{"error":"invalid content-type"}`
  - 400 JSON `{"error":"file missing"}`
  - 413 JSON `{"error":"payload too large"}`
  - 500 JSON `{"error":"<exception text>"}`

Legacy Logging (Kompatibilitätsziel):
- `scanner.log` für Verarbeitung.
- `raw_connections.log` für Fehlversuche und Raw-Peeks.

Legacy Module-Semantik (Kompatibilitätsziel):
- Basis-Pipeline wie in `scanner_api.process_image`:
  - nsfw_scanner -> tagging -> deepdanbooru_tags -> statistics.record_tags -> image_storage
  - danach zusätzliche Module aus `modules.cfg` via ModuleManager, außer Skip-Set.
- Fehler pro Modul werden als `{"error":"..."}` im Modul-Key zurückgegeben, ohne den Request zu killen.

### B) LocalSupervisor API (bestehend)

1) POST /scan_image
- Body JSON:
  - `file_path`: Pfad zur Datei
  - `modules`: Liste alter Modulnamen, wird intern auf Bitmask gemappt
  - `token`: Token-String
- Response-Struktur darf nicht gebrochen werden, da externe Systeme darauf basieren:
  - `file_path`
  - `statistics`
  - `nsfw_score`
  - `tags`
  - optional `error`

## Sicherheit

Muss systematisch und konsistent umgesetzt werden.

- Tokenpflicht:
  - Legacy: Header `Authorization`
  - LocalSupervisor: Body `token`
- Token-Lebensdauer Legacy: 30 Tage.
- Größenlimits strikt erzwingen: 10 MB `/check`, 25 MB `/batch`.
- Validierung:
  - `/check`: echte Bildvalidierung (PIL verify wie Legacy).
  - `/scan_image`: corrupt/unreadable handling wie vorhanden.
- Optionaler Pfad-Whitelist für `/scan_image`:
  - `SCAN_ALLOWED_ROOTS="/pfad1,/pfad2"` setzt erlaubte Root-Pfade.
  - Wenn gesetzt, werden nur Dateien unterhalb dieser Roots akzeptiert.
- Fehlerantworten müssen stabil bleiben, keine internen Details in Legacy-JSON außer dem existierenden `{"error": str(e)}` Verhalten.

## Persistenz (SQLite)

Ziel: Datei-basierte Metadaten aus Legacy ersetzen, ohne Legacy-Responses zu ändern.

In DB speichern:
- Tokens + Timestamps + Nutzung.
- Stats (gesamt, tag counts).
- Scan Results (hash, flags_done, meta_json, nsfw_score, tags, characters, timestamps).
- Tag-Trends.

Im Dateisystem optional:
- Bilder unter `scanned/` weiterhin möglich, aber keine JSON-Metadaten als Source of Truth.

## Repo-Mapping Legacy zu Neu

Legacy (pixai-sensible-main):
- `scanner_api.py` Legacy HTTP API
- `token_manager.py` Tokens 30 Tage, `tokens.json`
- `gif_batch.py` Batch Scan
- `modules/` Pipeline-Module + Modelle
- `main.py` + `watcher.py` Hot-Reload + ModuleManager
- `modules.cfg` Liste zusätzlicher Module

Neu (supervisor-tag-scan-main):
- `main.py` FastAPI App
- `routers/legacy_api.py` LocalSupervisor Bridge (`/scan_image`)
- `routers/auth.py` aktuelles Token-System (nicht Legacy-kompatibel)
- `core/model_manager.py` RAM/VRAM Cache
- `core/database.py` SQLite
- `core/image_utils.py` Hash/Metadata/Corrupt Check
- `core/bitmask.py` Module->Flags

## Arbeitsplan (Abarbeitungspfad)

Phase 0 Dokumentation (jetzt)
- README und AGENTS fixieren, Kompatibilitätsvertrag definieren.

Phase 1 Nahtloser Legacy-Wechsel
- Legacy HTTP API Endpoints in FastAPI nachbauen (`/token`, `/stats`, `/check`, `/batch`) mit identischem Verhalten.
- Legacy Token-Manager kompatibel machen (bestehende `tokens.json` akzeptieren).
- Legacy Pipeline-Keys und Fehlerverhalten exakt reproduzieren.
- Logging kompatibel (scanner.log, raw_connections.log).

Phase 2 Absicherung und Stabilität
- Ein einziger Auth-Layer, der Legacy und LocalSupervisor bedient.
- Limit/Validation überall konsistent.
- Keine stillen Änderungen an Response-Strukturen.

Phase 3 SQLite als Source of Truth
- Tokens, Stats, Scan Results, Trends in SQLite.
- Migration aus Legacy-Dateien.
- Legacy Responses bleiben gleich.

Phase 4 Cleanup
- Pycache/leer-Modelle aus Legacy nicht als Runtime-Abhängigkeit behandeln.
- Modellpfade sauber, Config zentral.

## Start

- `python main.py` startet das FastAPI/uvicorn Service auf Port 8000.
- Health: `GET /health`.

## Smoke Test

- `pip install -r requirements-dev.txt`
- `python tools/legacy_smoke_test.py`
