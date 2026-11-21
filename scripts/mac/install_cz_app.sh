#!/usr/bin/env bash
# Installs CZ on macOS and adds a "CZ" app to ~/Applications.
# Run once:  bash scripts/mac/install_cz_app.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
APP_DIR="$HOME/Applications/CZ.app"

echo "==> CZ wird eingerichtet in: $REPO_DIR"

if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  echo "==> Installiere uv (Python-Paketverwaltung) ..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

echo "==> Installiere Abhängigkeiten (dauert ein paar Minuten) ..."
cd "$REPO_DIR"
uv sync --frozen

echo "==> Lege die App CZ in ~/Applications an ..."
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

cat > "$APP_DIR/Contents/Resources/start-cz.command" <<CMD
#!/usr/bin/env bash
# Startet CZ. Dieses Fenster offen lassen, solange du mit CZ arbeitest.
export PATH="\$HOME/.local/bin:\$PATH"
export STREAMLIT_SERVER_HEADLESS=true
REPO_DIR="$REPO_DIR"
LOG="\$REPO_DIR/storage/cz-webui.log"
URL_FILE="\$REPO_DIR/storage/cz-url"
mkdir -p "\$REPO_DIR/storage"
cd "\$REPO_DIR"
echo "CZ startet ... bitte kurz warten."
echo "Zum Beenden dieses Fenster schließen."
./webui.sh > "\$LOG" 2>&1 &
SERVER_PID=\$!
trap 'kill \$SERVER_PID 2>/dev/null; rm -f "\$URL_FILE"' EXIT
URL=""
for i in \$(seq 1 120); do
  URL=\$(grep -o 'http://127.0.0.1:[0-9]*' "\$LOG" | head -1)
  if [ -n "\$URL" ] && curl -s -o /dev/null "\$URL"; then break; fi
  if ! kill -0 \$SERVER_PID 2>/dev/null; then echo "CZ konnte nicht starten:"; tail -20 "\$LOG"; read -r -p "Enter zum Schließen"; exit 1; fi
  sleep 1
done
echo "\$URL" > "\$URL_FILE"
echo "CZ läuft: \$URL"
# Chrome bevorzugen: ältere Safari-Versionen (macOS 13) zeigen die Oberfläche leer an.
if [ -d "/Applications/Google Chrome.app" ]; then
  open -a "Google Chrome" "\$URL"
else
  open "\$URL"
fi
tail -f "\$LOG"
CMD
chmod +x "$APP_DIR/Contents/Resources/start-cz.command"

cat > "$APP_DIR/Contents/MacOS/CZ" <<LAUNCH
#!/usr/bin/env bash
HERE="\$(cd "\$(dirname "\$0")/.." && pwd)"
URL_FILE="$REPO_DIR/storage/cz-url"
# Läuft CZ schon? Dann nur den Browser öffnen.
if [ -f "\$URL_FILE" ] && curl -s -o /dev/null "\$(cat "\$URL_FILE")"; then
  if [ -d "/Applications/Google Chrome.app" ]; then open -a "Google Chrome" "\$(cat "\$URL_FILE")"; else open "\$(cat "\$URL_FILE")"; fi
else
  open -a Terminal "\$HERE/Resources/start-cz.command"
fi
LAUNCH
chmod +x "$APP_DIR/Contents/MacOS/CZ"

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>CZ</string>
  <key>CFBundleDisplayName</key><string>CZ</string>
  <key>CFBundleIdentifier</key><string>local.cz.studio</string>
  <key>CFBundleExecutable</key><string>CZ</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1.0</string>
</dict>
</plist>
PLIST

echo ""
echo "Fertig. Du findest CZ jetzt unter Programme im Ordner ~/Applications."
echo "Tipp: CZ ins Dock ziehen, dann reicht ein Klick."
open "$HOME/Applications" || true
