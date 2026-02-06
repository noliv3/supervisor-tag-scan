# SuperVisor-tag-scan

Ein residenter Python-Service zur Medienanalyse (Tags, NSFW, Face-Detect) für LocalSupervisor und Discord-Bots.

## Core Features
- **Resident Architecture:** Modelle bleiben im RAM (kein Reload pro Bild).
- **Bitmask Control:** Steuerung der GPU-Last über Integer-Flags (statt String-Listen).
- **Legacy Bridge:** Volle Kompatibilität zur alten API (`POST /scan_image`), übersetzt alte JSON-Requests intern in Bitmasken.
- **SQLite Caching:** Speicherung von Hashes, Tags und Trends.

## Bitmask Definitionen (WICHTIG für alle Devs)
- **1 (Basic):** Hash, Resolution, Filesize.
- **2 (NSFW):** Schneller NSFW Check.
- **4 (Tags):** DeepDanbooru Inferenz (GPU Heavy).
- **8 (Face):** YOLOv8 Face Detection & BBox (für Vidax).
- **16 (Vector):** CLIP Embeddings (Semantische Suche).
