# Architektur-Regeln für KI-Agenten/Developer

## Interne Akteure
- **The Gatekeeper (Auth):** Validiert Tokens gegen `tokens.json`.
- **The Translator (Legacy API):** Nimmt alte JSON-Requests (`["tags", "nsfw"]`) entgegen und wandelt sie in Bitmasken (`6`) um.
- **The Resource Manager (Model Loader):** Verwaltet den VRAM. Lädt Modelle nur, wenn das entsprechende Bit im Request gesetzt ist (Lazy Loading). Hält Modelle im Cache.
- **The Archivist (Database):** Schreibt Ergebnisse asynchron in `scanner.db`. Aktualisiert "Tags Done" Flags, damit nicht doppelt gescannt wird.

## Entwicklungs-Richtlinien
- **API First:** Keine GUI, nur FastAPI Endpoints.
- **Compatibility:** Die Response-Struktur von `/scan_image` darf NICHT verändert werden (Legacy Support).
- **Performance:** Keine synchronen I/O Operationen im Main-Loop.
