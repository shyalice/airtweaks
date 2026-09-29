#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV="build/backend-venv"
DIST="build/backend-dist"
WORK="build/backend-work"
SPEC="build/backend-spec"

echo "==> [1/4] build venv"
if [[ ! -d "$VENV" ]]; then
    HOST_PYMD="$(command -v pymobiledevice3 || true)"
    if [[ -n "$HOST_PYMD" ]]; then
        HOST_PY="$(head -1 "$HOST_PYMD" | sed 's/^#! *//')"
    else
        HOST_PY="$(command -v python3.12 || command -v python3.11 || command -v python3)"
    fi
    "$HOST_PY" -m venv "$VENV"
fi

VPIP="$VENV/bin/pip"
VPY="$VENV/bin/python"

echo "==> [2/4] deps"
"$VPIP" install --upgrade --quiet pip wheel
"$VPIP" install --quiet 'pyinstaller>=6.6' 'pymobiledevice3==11.12.5'

echo "==> [3/4] clean"
rm -rf "$DIST" "$WORK" "$SPEC"
mkdir -p "$DIST" "$WORK" "$SPEC"

echo "==> [4/4] pyinstaller"
"$VPY" -m PyInstaller \
    --noconfirm --clean --onedir \
    --name airtweaks-backend \
    --distpath "$DIST" --workpath "$WORK" --specpath "$SPEC" \
    --collect-all pymobiledevice3 \
    --collect-submodules construct \
    --collect-submodules cryptography \
    --collect-submodules bpylist2 \
    --hidden-import features._airlift \
    --hidden-import features.usbmux \
    --hidden-import features.carrier_sim \
    --hidden-import features.call_history \
    --hidden-import features.diagnostics \
    --hidden-import features.ringtones \
    --add-data "$ROOT/Python/features:features" \
    "$ROOT/Python/backend.py"

BIN="$DIST/airtweaks-backend/airtweaks-backend"
[[ -x "$BIN" ]] || { echo "!! missing $BIN"; exit 1; }
echo "==> ok: $BIN ($(du -sh "$DIST/airtweaks-backend" | cut -f1))"
