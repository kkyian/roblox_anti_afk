# Roblox Anti-AFK

A small macOS app that sends a periodic keyboard or mouse action while Roblox is active.

Use it only in experiences where this kind of automation is allowed by the game rules.

## Build The App

```bash
chmod +x build_app.sh
./build_app.sh
```

The app is created at:

```text
dist/Roblox Anti-AFK.app
```

Double-click it in Finder to run it.

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
