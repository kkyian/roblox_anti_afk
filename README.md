# Roblox Anti-AFK

A small macOS app that sends a periodic keyboard or mouse action while Roblox is active.

Use it only in experiences where this kind of automation is allowed by the game rules. This project is not affiliated with Roblox Corporation.

## Features

- Native macOS app with Start, Stop, status, and activity log controls.
- Optional Roblox focus guard so input is sent only while Roblox is the active app.
- Configurable interval, jitter, and action type.
- Browser-based Python fallback for macOS, Windows, and Linux.

## Requirements

- macOS 13 or newer for the native app.
- Xcode Command Line Tools for building the native app:

```bash
xcode-select --install
```

- Python 3.10 or newer for the browser version.
- Linux browser-version users also need `xdotool`.

## Run Checks

```bash
python3 -m py_compile roblox_anti_afk.py
python3 -m unittest discover -s tests
plutil -lint macos/Info.plist
./build_app.sh
```

## Build The macOS App

```bash
chmod +x build_app.sh
./build_app.sh
```

The app is created at:

```text
dist/Roblox Anti-AFK.app
```

Double-click it in Finder to run it.

`dist/` is generated build output and is ignored by the repository. If you want to share a built app, attach it to a GitHub Release instead of committing it.

## macOS Permission

macOS requires Accessibility permission before apps can send keyboard or mouse input:

1. Open System Settings.
2. Go to Privacy & Security > Accessibility.
3. Enable access for Roblox Anti-AFK.

The app also has an Open Settings button for this.

## Controls

- `Interval seconds`: how often an action is sent.
- `Jitter seconds`: randomizes the interval slightly.
- `Action`: choose Space, left click, or mouse nudge.
- `Roblox focus guard`: sends input only when Roblox is the active app.

Keep Roblox focused when the app is running. The focus guard is enabled by default so the app does not send input into unrelated windows.

## Browser Version

```bash
python3 roblox_anti_afk.py
```

The app opens at `http://127.0.0.1:8765`.

To run without opening a browser automatically:

```bash
python3 roblox_anti_afk.py --no-browser
```

## Project Layout

```text
.
├── .github/workflows/ci.yml
├── build_app.sh
├── LICENSE
├── macos/
│   ├── Info.plist
│   └── RobloxAntiAFKApp.m
├── roblox_anti_afk.py
├── tests/
│   └── test_roblox_anti_afk.py
└── README.md
```

## Publish Checklist

- Run `./build_app.sh`.
- Run `python3 -m py_compile roblox_anti_afk.py`.
- Run `python3 -m unittest discover -s tests`.
- Confirm `macos/Info.plist` passes `plutil -lint macos/Info.plist`.
- Keep generated `dist/` output out of source control.
- Confirm `LICENSE` has the intended copyright holder.
