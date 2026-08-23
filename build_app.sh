#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT_DIR/dist/Roblox Anti-AFK.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$ROOT_DIR/macos/Info.plist" "$CONTENTS_DIR/Info.plist"

clang \
  -fobjc-arc \
  "$ROOT_DIR/macos/RobloxAntiAFKApp.m" \
  -framework Cocoa \
  -framework ApplicationServices \
  -framework QuartzCore \
  -o "$MACOS_DIR/Roblox Anti-AFK"

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_DIR" >/dev/null
fi

echo "$APP_DIR"
