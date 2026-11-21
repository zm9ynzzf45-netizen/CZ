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
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$REPO_DIR/resource/cz/CZ.icns" "$APP_DIR/Contents/Resources/CZ.icns"

# Startet CZ im eigenen Fenster (scripts/mac/cz_desktop.py), ohne Terminal und Browser.
cat > "$APP_DIR/Contents/MacOS/CZ" <<LAUNCH
#!/usr/bin/env bash
export PATH="\$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
REPO_DIR="$REPO_DIR"
LOG="\$REPO_DIR/storage/cz-app.log"
mkdir -p "\$REPO_DIR/storage"
cd "\$REPO_DIR"
export CZ_APP_PATH="$APP_DIR"
echo "=== CZ Start \$(date) ===" > "\$LOG"
if ! uv run --frozen python scripts/mac/cz_desktop.py >> "\$LOG" 2>&1; then
  osascript -e 'display dialog "CZ konnte nicht starten. Details stehen in ~/cz/storage/cz-app.log – schick sie Claude." buttons {"OK"} default button 1 with icon caution with title "CZ"' >/dev/null 2>&1
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
  <key>CFBundleIconFile</key><string>CZ</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>2.0</string>
  <key>CFBundleShortVersionString</key><string>2.0</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# Finder soll das neue Symbol sofort anzeigen.
touch "$APP_DIR" 2>/dev/null || true

echo ""
echo "Fertig. Du findest CZ jetzt unter Programme im Ordner ~/Applications."
echo "Doppelklick auf CZ öffnet dein CZ Studio im eigenen Fenster."
echo "Tipp: CZ ins Dock ziehen, dann reicht ein Klick."
open "$HOME/Applications" || true
