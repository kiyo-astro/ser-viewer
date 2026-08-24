#!/usr/bin/env bash
# Build "SER Viewer.app" and a DMG on macOS.
#
#   ./packaging/build_macos.sh            build into dist/
#   ./packaging/build_macos.sh --venv     build inside a throw-away virtualenv
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if [[ "${1:-}" == "--venv" ]]; then
    rm -rf .buildenv
    "$PYTHON" -m venv .buildenv
    PYTHON="$ROOT/.buildenv/bin/python"
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -r requirements-dev.txt
fi

"$PYTHON" packaging/make_icon.py
rm -rf build dist
"$PYTHON" -m PyInstaller --noconfirm --clean packaging/serview.spec

APP="dist/SER Viewer.app"
test -d "$APP" || { echo "the .app bundle was not produced" >&2; exit 1; }

# Ad-hoc signature: without it macOS refuses to launch an unsigned arm64 bundle.
codesign --force --deep --sign - "$APP"

VERSION="$("$PYTHON" -c 'import re,pathlib;print(re.search(r"__version__ = \"([^\"]+)\"", pathlib.Path("serview/__init__.py").read_text()).group(1))')"
ARCH="$(uname -m)"
DMG="dist/SER-Viewer-${VERSION}-macOS-${ARCH}.dmg"
STAGING="$(mktemp -d)"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
rm -f "$DMG"
hdiutil create -volname "SER Viewer $VERSION" -srcfolder "$STAGING" -ov -format UDZO "$DMG"
rm -rf "$STAGING"

echo
echo "Built $APP"
echo "Built $DMG"
