#!/usr/bin/env bash
#
# wrap build/AirTweaks.app into a distributable DMG with drag-to-Applications
# layout. run Scripts/build.sh first.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="AirTweaks"
APP="$ROOT/build/$APP_NAME.app"
DMG="$ROOT/build/$APP_NAME.dmg"
STAGING="$ROOT/build/dmg-staging"
VOLNAME="$APP_NAME"

[[ -d "$APP" ]] || { echo "!! missing $APP — run Scripts/build.sh first"; exit 1; }

echo "==> [1/5] strip stale quarantine on source .app"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

echo "==> [2/5] re-sign .app ad-hoc"
codesign --force --deep --sign - "$APP"

echo "==> [3/5] stage dmg contents"
rm -rf "$STAGING" "$DMG"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

echo "==> [4/5] create compressed dmg"
hdiutil create \
    -volname "$VOLNAME" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    -fs HFS+ \
    "$DMG" >/dev/null

echo "==> [5/5] sign dmg ad-hoc"
codesign --force --sign - "$DMG"
rm -rf "$STAGING"

SIZE=$(du -h "$DMG" | cut -f1)
echo
echo "==> done: $DMG ($SIZE)"
echo
echo "    testers: after copying to /Applications, first launch needs:"
echo "        xattr -dr com.apple.quarantine /Applications/$APP_NAME.app"
echo "    or right-click → open (gatekeeper prompt on unsigned build)."
