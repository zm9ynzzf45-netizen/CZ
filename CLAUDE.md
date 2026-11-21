# CZ – Hinweise für Claude

## Antwortstil
- Antworte auf Deutsch, kurz und einfach (der Nutzer ist GitHub-Anfänger).
- Erkläre mit Grafiken (PNG/Diagramm) plus wenigen kurzen Sätzen statt langer Texte.
- Bevor du dem Nutzer Befehle, Installationen oder Schritte gibst: erst selbst prüfen
  (Simulation/Test), dann schriftlich bestätigen, WAS geprüft wurde und was nicht.
- Der Nutzer hat einen Mac mit macOS 13 (Apple Silicon, arm64). Abhängigkeiten
  immer gegen macOS 13 arm64 prüfen (nur fertige Wheels).

## Projekt
- Fork von MoneyPrinterTurbo, erweitert zu CZ (KI-Kurzvideos für TikTok/Reels/Shorts).
- Higgsfield ist als Videoquelle `higgsfield` eingebaut (`app/services/material.py`).
- Mac-Installer: `scripts/mac/install_cz_app.sh` legt `~/Applications/CZ.app` an.
