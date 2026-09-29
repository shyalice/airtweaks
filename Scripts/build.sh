#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="AirTweaks"
APP="$ROOT/build/$APP_NAME.app"

echo "==> [1/3] backend"
if [[ "${SKIP_PYINSTALLER:-0}" != "1" ]]; then
    bash "$ROOT/Scripts/build_backend.sh"
fi
BACKEND_DIR="$ROOT/build/backend-dist/airtweaks-backend"
[[ -x "$BACKEND_DIR/airtweaks-backend" ]] \
    || { echo "!! backend binary missing at $BACKEND_DIR/"; exit 1; }

echo "==> [2/3] swift build --configuration release"
cd "$ROOT"
swift build --configuration release

echo "==> [3/3] .app bundle"
BIN="$ROOT/.build/release/$APP_NAME"
[[ -f "$BIN" ]] || { echo "!! swift build did not produce $BIN"; exit 1; }

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/$APP_NAME"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>$APP_NAME</string>
    <key>CFBundleIdentifier</key><string>com.rei.airtweaks</string>
    <key>CFBundleName</key><string>$APP_NAME</string>
    <key>CFBundleDisplayName</key><string>$APP_NAME</string>
    <key>CFBundleShortVersionString</key><string>0.2</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>14.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSPrincipalClass</key><string>NSApplication</string>
</dict>
</plist>
PLIST

cp -R "$BACKEND_DIR" "$APP/Contents/Resources/backend"
codesign --force --deep --sign - "$APP" || true

echo "==> done: $APP"
echo "    open $APP"

if [[ "${BUILD_DMG:-0}" == "1" ]]; then
    bash "$ROOT/Scripts/dmg.sh"
fi
