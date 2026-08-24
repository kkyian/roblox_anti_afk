#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import json
import platform
import random
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


ACTIONS = {
    "space": {
        "label": "Space key",
        "detail": "Taps Space in the active Roblox window.",
    },
    "click": {
        "label": "Left click",
        "detail": "Clicks at the current mouse position.",
    },
    "nudge": {
        "label": "Mouse nudge",
        "detail": "Moves the pointer 1 pixel and back.",
    },
}


class InputActionError(RuntimeError):
    pass


@dataclass
class Settings:
    interval: int = 180
    jitter: int = 15
    action: str = "space"
    require_roblox_focus: bool = True


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError("Roblox focus guard must be true or false.")


def parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port must be a number.") from exc
    if port < 0 or port > 65535:
        raise argparse.ArgumentTypeError("Port must be between 0 and 65535.")
    return port


class InputController:
    name = "Unknown"
    focus_guard_available = False

    def perform(self, action: str) -> None:
        if action == "space":
            self.press_space()
        elif action == "click":
            self.left_click()
        elif action == "nudge":
            self.mouse_nudge()
        else:
            raise InputActionError(f"Unsupported action: {action}")

    def press_space(self) -> None:
        raise NotImplementedError

    def left_click(self) -> None:
        raise NotImplementedError

    def mouse_nudge(self) -> None:
        raise NotImplementedError

    def is_roblox_active(self) -> bool | None:
        return None

    def permission_state(self) -> dict[str, Any]:
        return {
            "name": "Input permission",
            "ok": None,
            "message": "Permission status is unavailable on this platform.",
        }


class MacInputController(InputController):
    name = "macOS"
    focus_guard_available = True

    KEY_SPACE = 49
    K_CG_HID_EVENT_TAP = 0
    K_CG_EVENT_LEFT_MOUSE_DOWN = 1
    K_CG_EVENT_LEFT_MOUSE_UP = 2
    K_CG_EVENT_MOUSE_MOVED = 5
    K_CG_MOUSE_BUTTON_LEFT = 0

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    def __init__(self) -> None:
        self._app_services = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        self._core_foundation = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self._configure_quartz()

    def _configure_quartz(self) -> None:
        app = self._app_services
        app.CGEventCreate.argtypes = [ctypes.c_void_p]
        app.CGEventCreate.restype = ctypes.c_void_p
        app.CGEventGetLocation.argtypes = [ctypes.c_void_p]
        app.CGEventGetLocation.restype = self.CGPoint
        app.CGEventCreateMouseEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            self.CGPoint,
            ctypes.c_uint32,
        ]
        app.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        app.CGEventCreateKeyboardEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.c_bool,
        ]
        app.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        app.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        app.CGEventPost.restype = None
        app.AXIsProcessTrusted.argtypes = []
        app.AXIsProcessTrusted.restype = ctypes.c_bool
        self._core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        self._core_foundation.CFRelease.restype = None

    def _release(self, event: int | None) -> None:
        if event:
            self._core_foundation.CFRelease(event)

    def _current_position(self) -> CGPoint:
        event = self._app_services.CGEventCreate(None)
        if not event:
            raise InputActionError("Could not read the current mouse position.")
        try:
            return self._app_services.CGEventGetLocation(event)
        finally:
            self._release(event)

    def _post_mouse(self, event_type: int, point: CGPoint) -> None:
        event = self._app_services.CGEventCreateMouseEvent(
            None, event_type, point, self.K_CG_MOUSE_BUTTON_LEFT
        )
        if not event:
            raise InputActionError("Could not create a mouse event.")
        try:
            self._app_services.CGEventPost(self.K_CG_HID_EVENT_TAP, event)
        finally:
            self._release(event)

    def _post_key(self, key_code: int, pressed: bool) -> None:
        event = self._app_services.CGEventCreateKeyboardEvent(None, key_code, pressed)
        if not event:
            raise InputActionError("Could not create a keyboard event.")
        try:
            self._app_services.CGEventPost(self.K_CG_HID_EVENT_TAP, event)
        finally:
            self._release(event)

    def press_space(self) -> None:
        self._post_key(self.KEY_SPACE, True)
        time.sleep(0.05)
        self._post_key(self.KEY_SPACE, False)

    def left_click(self) -> None:
        point = self._current_position()
        self._post_mouse(self.K_CG_EVENT_LEFT_MOUSE_DOWN, point)
        time.sleep(0.05)
        self._post_mouse(self.K_CG_EVENT_LEFT_MOUSE_UP, point)

    def mouse_nudge(self) -> None:
        point = self._current_position()
        nudged = self.CGPoint(point.x + 1, point.y)
        self._post_mouse(self.K_CG_EVENT_MOUSE_MOVED, nudged)
        time.sleep(0.05)
        self._post_mouse(self.K_CG_EVENT_MOUSE_MOVED, point)

    def is_roblox_active(self) -> bool | None:
        script = (
            'tell application "System Events" to get name of '
            "first application process whose frontmost is true"
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return "roblox" in result.stdout.strip().lower()

    def permission_state(self) -> dict[str, Any]:
        trusted = bool(self._app_services.AXIsProcessTrusted())
        return {
            "name": "Accessibility",
            "ok": trusted,
            "message": (
                "Ready to send input."
                if trusted
                else "Enable Accessibility access for your terminal or Python app."
            ),
        }


WINDOWS_ULONG_PTR = (
    ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
)


class WindowsMouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", WINDOWS_ULONG_PTR),
    ]


class WindowsKeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", WINDOWS_ULONG_PTR),
    ]


class WindowsInputUnion(ctypes.Union):
    _fields_ = [("mi", WindowsMouseInput), ("ki", WindowsKeyboardInput)]


class WindowsInput(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", WindowsInputUnion)]


class WindowsInputController(InputController):
    name = "Windows"
    focus_guard_available = True

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    VK_SPACE = 0x20
    INPUT = WindowsInput
    MOUSEINPUT = WindowsMouseInput
    KEYBDINPUT = WindowsKeyboardInput

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.SendInput.argtypes = [
            ctypes.c_uint,
            ctypes.POINTER(self.INPUT),
            ctypes.c_int,
        ]
        self.user32.SendInput.restype = ctypes.c_uint

    def _send(self, event: INPUT) -> None:
        sent = self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))
        if sent != 1:
            raise InputActionError("Windows did not accept the input event.")

    def _key_event(self, vk: int, flags: int = 0) -> INPUT:
        event = self.INPUT()
        event.type = self.INPUT_KEYBOARD
        event.union.ki = self.KEYBDINPUT(vk, 0, flags, 0, 0)
        return event

    def _mouse_event(self, flags: int, dx: int = 0, dy: int = 0) -> INPUT:
        event = self.INPUT()
        event.type = self.INPUT_MOUSE
        event.union.mi = self.MOUSEINPUT(dx, dy, 0, flags, 0, 0)
        return event

    def press_space(self) -> None:
        self._send(self._key_event(self.VK_SPACE))
        time.sleep(0.05)
        self._send(self._key_event(self.VK_SPACE, self.KEYEVENTF_KEYUP))

    def left_click(self) -> None:
        self._send(self._mouse_event(self.MOUSEEVENTF_LEFTDOWN))
        time.sleep(0.05)
        self._send(self._mouse_event(self.MOUSEEVENTF_LEFTUP))

    def mouse_nudge(self) -> None:
        self._send(self._mouse_event(self.MOUSEEVENTF_MOVE, 1, 0))
        time.sleep(0.05)
        self._send(self._mouse_event(self.MOUSEEVENTF_MOVE, -1, 0))

    def is_roblox_active(self) -> bool | None:
        hwnd = self.user32.GetForegroundWindow()
        if not hwnd:
            return None

        title_buffer = ctypes.create_unicode_buffer(512)
        self.user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        candidates = [title_buffer.value]

        pid = ctypes.c_ulong()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = self.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
            )
            if handle:
                try:
                    path_buffer = ctypes.create_unicode_buffer(1024)
                    size = ctypes.c_ulong(len(path_buffer))
                    query = self.kernel32.QueryFullProcessImageNameW
                    if query(handle, 0, path_buffer, ctypes.byref(size)):
                        candidates.append(path_buffer.value)
                finally:
                    self.kernel32.CloseHandle(handle)

        text = " ".join(candidates).lower()
        return "roblox" in text

    def permission_state(self) -> dict[str, Any]:
        return {
            "name": "Input permission",
            "ok": True,
            "message": "Ready to send input.",
        }


class LinuxInputController(InputController):
    name = "Linux"
    focus_guard_available = True

    def __init__(self) -> None:
        self.xdotool = shutil.which("xdotool")

    def _run_xdotool(self, *args: str) -> str:
        if not self.xdotool:
            raise InputActionError("Install xdotool to send desktop input on Linux.")
        result = subprocess.run(
            [self.xdotool, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or "xdotool failed."
            raise InputActionError(message)
        return result.stdout.strip()

    def press_space(self) -> None:
        self._run_xdotool("key", "space")

    def left_click(self) -> None:
        self._run_xdotool("click", "1")

    def mouse_nudge(self) -> None:
        self._run_xdotool("mousemove_relative", "--", "1", "0")
        time.sleep(0.05)
        self._run_xdotool("mousemove_relative", "--", "-1", "0")

    def is_roblox_active(self) -> bool | None:
        if not self.xdotool:
            return None
        try:
            name = self._run_xdotool("getwindowfocus", "getwindowname")
        except InputActionError:
            return None
        return "roblox" in name.lower()

    def permission_state(self) -> dict[str, Any]:
        return {
            "name": "xdotool",
            "ok": bool(self.xdotool),
            "message": (
                "Ready to send input."
                if self.xdotool
                else "Install xdotool to send input on Linux."
            ),
        }


class UnsupportedInputController(InputController):
    def __init__(self, system_name: str) -> None:
        self.name = system_name

    def press_space(self) -> None:
        raise InputActionError(f"{self.name} is not supported for input automation.")

    def left_click(self) -> None:
        raise InputActionError(f"{self.name} is not supported for input automation.")

    def mouse_nudge(self) -> None:
        raise InputActionError(f"{self.name} is not supported for input automation.")


def make_input_controller() -> InputController:
    system_name = platform.system()
    if system_name == "Darwin":
        return MacInputController()
    if system_name == "Windows":
        return WindowsInputController()
    if system_name == "Linux":
        return LinuxInputController()
    return UnsupportedInputController(system_name)


class AntiAfkEngine:
    def __init__(self, controller: InputController) -> None:
        self.controller = controller
        self.lock = threading.RLock()
        self.settings = Settings()
        self.running = False
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.next_action_at: float | None = None
        self.last_action_at: float | None = None
        self.action_count = 0
        self.last_error: str | None = None
        self.events: deque[dict[str, str]] = deque(maxlen=80)

    def start(self, payload: dict[str, Any]) -> None:
        settings = self._parse_settings(payload)
        with self.lock:
            self.settings = settings
            self.last_error = None
            if self.running:
                self._schedule_next_locked(initial=False)
                self._log_locked("Settings updated.")
                return
            self.stop_event.clear()
            self.running = True
            self.action_count = 0
            self.next_action_at = time.time() + 5
            self._log_locked("Started. First action is armed.")
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self) -> None:
        thread: threading.Thread | None = None
        with self.lock:
            if not self.running:
                return
            self.running = False
            self.next_action_at = None
            self.stop_event.set()
            thread = self.thread
            self._log_locked("Stopped.")
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)

    def _parse_settings(self, payload: dict[str, Any]) -> Settings:
        try:
            interval = int(payload.get("interval", 180))
            jitter = int(payload.get("jitter", 15))
        except (TypeError, ValueError) as exc:
            raise ValueError("Interval and jitter must be numbers.") from exc

        action = str(payload.get("action", "space"))
        if action not in ACTIONS:
            raise ValueError("Choose a supported action.")
        if interval < 10 or interval > 900:
            raise ValueError("Interval must be between 10 and 900 seconds.")
        if jitter < 0 or jitter > 300:
            raise ValueError("Jitter must be between 0 and 300 seconds.")
        jitter = min(jitter, max(0, interval - 5))
        require_roblox_focus = parse_bool(payload.get("require_roblox_focus"), True)
        return Settings(
            interval=interval,
            jitter=jitter,
            action=action,
            require_roblox_focus=require_roblox_focus,
        )

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            with self.lock:
                if not self.running:
                    break
                next_action_at = self.next_action_at or time.time()
            wait_time = max(0.0, next_action_at - time.time())
            if self.stop_event.wait(wait_time):
                break

            with self.lock:
                if not self.running:
                    break
                settings = self.settings

            try:
                if settings.require_roblox_focus:
                    active = self.controller.is_roblox_active()
                    if active is False:
                        with self.lock:
                            self._log_locked("Skipped because Roblox is not active.")
                            self._schedule_next_locked(initial=False)
                        continue
                    if active is None:
                        with self.lock:
                            self._log_locked(
                                "Skipped because the active app could not be checked."
                            )
                            self._schedule_next_locked(initial=False)
                        continue

                self.controller.perform(settings.action)
                label = ACTIONS[settings.action]["label"]
                with self.lock:
                    self.action_count += 1
                    self.last_action_at = time.time()
                    self.last_error = None
                    self._log_locked(f"Sent action: {label}.")
                    self._schedule_next_locked(initial=False)
            except Exception as exc:  # noqa: BLE001 - surface input errors to the UI.
                with self.lock:
                    self.last_error = str(exc)
                    self._log_locked(f"Error: {self.last_error}")
                    self._schedule_next_locked(initial=False)

        with self.lock:
            self.running = False
            self.next_action_at = None

    def _schedule_next_locked(self, initial: bool) -> None:
        if initial:
            self.next_action_at = time.time() + 5
            return
        spread = self.settings.jitter
        delay = self.settings.interval
        if spread:
            delay += random.randint(-spread, spread)
        self.next_action_at = time.time() + max(5, delay)

    def _log_locked(self, message: str) -> None:
        self.events.appendleft(
            {
                "time": time.strftime("%H:%M:%S"),
                "message": message,
            }
        )

    def status(self) -> dict[str, Any]:
        with self.lock:
            next_action_in = None
            if self.running and self.next_action_at:
                next_action_in = max(0, int(round(self.next_action_at - time.time())))
            return {
                "running": self.running,
                "settings": asdict(self.settings),
                "next_action_in": next_action_in,
                "last_action_at": self.last_action_at,
                "action_count": self.action_count,
                "last_error": self.last_error,
                "events": list(self.events),
                "platform": {
                    "name": self.controller.name,
                    "focus_guard_available": self.controller.focus_guard_available,
                    "permission": self.controller.permission_state(),
                },
                "actions": ACTIONS,
            }


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Roblox Anti-AFK</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f6f8;
      --panel: #ffffff;
      --ink: #182230;
      --muted: #667085;
      --line: #d8dee6;
      --accent: #2764d8;
      --accent-ink: #ffffff;
      --ok: #18794e;
      --warn: #a15c07;
      --bad: #b42318;
      --soft: #eef4ff;
      --shadow: 0 12px 30px rgba(16, 24, 40, 0.08);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
    }

    .shell {
      width: min(1040px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 36px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 20px;
    }

    h1 {
      margin: 0;
      font-size: clamp(1.55rem, 2vw, 2rem);
      line-height: 1.1;
      letter-spacing: 0;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      padding: 7px 11px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      color: var(--muted);
      font-weight: 700;
      white-space: nowrap;
    }

    .dot {
      width: 9px;
      height: 9px;
      border-radius: 99px;
      background: var(--muted);
    }

    .status-pill.running {
      color: var(--ok);
    }

    .status-pill.running .dot {
      background: var(--ok);
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 16px;
      align-items: start;
    }

    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }

    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
    }

    .panel-title {
      margin: 0;
      font-size: 1rem;
      line-height: 1.2;
      letter-spacing: 0;
    }

    .panel-body {
      padding: 18px;
    }

    .control-stack {
      display: grid;
      gap: 18px;
    }

    .field-row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    label,
    .field-label {
      display: block;
      margin-bottom: 7px;
      color: var(--muted);
      font-size: 0.82rem;
      font-weight: 700;
    }

    input[type="number"] {
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 11px;
      color: var(--ink);
      background: #fff;
      font: inherit;
      font-weight: 650;
    }

    input[type="number"]:focus-visible,
    button:focus-visible,
    .action-option:has(input:focus-visible) {
      outline: 3px solid rgba(39, 100, 216, 0.24);
      outline-offset: 2px;
    }

    .actions {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .action-option {
      min-height: 88px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px;
      cursor: pointer;
      background: #fff;
      transition: border-color 140ms ease, background 140ms ease, transform 140ms ease;
    }

    .action-option:hover {
      transform: translateY(-1px);
      border-color: #b7c6dc;
    }

    .action-option input {
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }

    .action-option:has(input:checked) {
      border-color: var(--accent);
      background: var(--soft);
    }

    .action-name {
      display: block;
      margin-bottom: 6px;
      font-weight: 800;
      line-height: 1.2;
    }

    .action-detail {
      display: block;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.35;
    }

    .toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px 13px;
    }

    .toggle-row input {
      width: 18px;
      height: 18px;
      flex: 0 0 auto;
      accent-color: var(--accent);
    }

    .toggle-title {
      display: block;
      font-weight: 800;
    }

    .toggle-detail {
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 0.84rem;
      line-height: 1.35;
    }

    .buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    button {
      min-height: 42px;
      border: 1px solid transparent;
      border-radius: 8px;
      padding: 9px 14px;
      color: var(--accent-ink);
      background: var(--accent);
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }

    button.secondary {
      color: var(--ink);
      background: #fff;
      border-color: var(--line);
    }

    button.danger {
      background: var(--bad);
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.55;
    }

    .metric-list {
      display: grid;
      gap: 12px;
    }

    .metric {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      padding-bottom: 11px;
      border-bottom: 1px solid var(--line);
    }

    .metric:last-child {
      padding-bottom: 0;
      border-bottom: 0;
    }

    .metric span:first-child {
      color: var(--muted);
      font-size: 0.84rem;
      font-weight: 700;
    }

    .metric span:last-child {
      text-align: right;
      font-weight: 850;
    }

    .notice {
      margin-top: 14px;
      border: 1px solid #f0d7a8;
      border-radius: 8px;
      padding: 11px 12px;
      background: #fff7e8;
      color: var(--warn);
      font-size: 0.88rem;
      line-height: 1.4;
    }

    .notice.ok {
      border-color: #b8dec9;
      background: #effaf4;
      color: var(--ok);
    }

    .log {
      display: grid;
      gap: 8px;
      max-height: 270px;
      overflow: auto;
      padding-right: 3px;
    }

    .log-entry {
      display: grid;
      grid-template-columns: 72px minmax(0, 1fr);
      gap: 8px;
      align-items: baseline;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.35;
    }

    .log-time {
      font-variant-numeric: tabular-nums;
      font-weight: 750;
      color: #475467;
    }

    .empty {
      color: var(--muted);
      font-size: 0.9rem;
    }

    @media (max-width: 820px) {
      .shell {
        width: min(100vw - 20px, 620px);
        padding-top: 16px;
      }

      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }

      .grid,
      .field-row,
      .actions {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <div class="topbar">
      <h1>Roblox Anti-AFK</h1>
      <div id="statusPill" class="status-pill"><span class="dot"></span><span>Stopped</span></div>
    </div>

    <div class="grid">
      <section class="panel">
        <div class="panel-header">
          <h2 class="panel-title">Controls</h2>
        </div>
        <div class="panel-body">
          <div class="control-stack">
            <div class="field-row">
              <div>
                <label for="interval">Interval seconds</label>
                <input id="interval" type="number" min="10" max="900" step="5" value="180">
              </div>
              <div>
                <label for="jitter">Jitter seconds</label>
                <input id="jitter" type="number" min="0" max="300" step="5" value="15">
              </div>
            </div>

            <div>
              <div class="field-label">Action</div>
              <div id="actions" class="actions"></div>
            </div>

            <label class="toggle-row" for="focusGuard">
              <span>
                <span class="toggle-title">Roblox focus guard</span>
                <span class="toggle-detail">Send input only while Roblox is the active app.</span>
              </span>
              <input id="focusGuard" type="checkbox" checked>
            </label>

            <div class="buttons">
              <button id="startBtn" type="button">Start</button>
              <button id="stopBtn" class="danger" type="button" disabled>Stop</button>
            </div>
          </div>
        </div>
      </section>

      <aside class="panel">
        <div class="panel-header">
          <h2 class="panel-title">Status</h2>
        </div>
        <div class="panel-body">
          <div class="metric-list">
            <div class="metric"><span>Next action</span><span id="nextAction">-</span></div>
            <div class="metric"><span>Actions sent</span><span id="actionCount">0</span></div>
            <div class="metric"><span>Platform</span><span id="platformName">-</span></div>
            <div class="metric"><span>Permission</span><span id="permissionName">-</span></div>
          </div>
          <div id="permissionNotice" class="notice" hidden></div>
        </div>
      </aside>

      <section class="panel">
        <div class="panel-header">
          <h2 class="panel-title">Activity</h2>
          <button id="refreshBtn" class="secondary" type="button">Refresh</button>
        </div>
        <div class="panel-body">
          <div id="log" class="log"></div>
        </div>
      </section>
    </div>
  </main>

  <script>
    const state = {
      action: "space",
      status: null,
    };

    const els = {
      statusPill: document.querySelector("#statusPill"),
      interval: document.querySelector("#interval"),
      jitter: document.querySelector("#jitter"),
      actions: document.querySelector("#actions"),
      focusGuard: document.querySelector("#focusGuard"),
      startBtn: document.querySelector("#startBtn"),
      stopBtn: document.querySelector("#stopBtn"),
      refreshBtn: document.querySelector("#refreshBtn"),
      nextAction: document.querySelector("#nextAction"),
      actionCount: document.querySelector("#actionCount"),
      platformName: document.querySelector("#platformName"),
      permissionName: document.querySelector("#permissionName"),
      permissionNotice: document.querySelector("#permissionNotice"),
      log: document.querySelector("#log"),
    };

    function secondsLabel(value) {
      if (value === null || value === undefined) return "-";
      if (value <= 0) return "now";
      const minutes = Math.floor(value / 60);
      const seconds = value % 60;
      if (minutes === 0) return `${seconds}s`;
      return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: {"Content-Type": "application/json"},
        ...options,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Request failed.");
      }
      return data;
    }

    function renderActions(actions) {
      if (!actions || els.actions.children.length) return;
      Object.entries(actions).forEach(([key, action]) => {
        const label = document.createElement("label");
        label.className = "action-option";
        label.innerHTML = `
          <input type="radio" name="action" value="${key}">
          <span class="action-name"></span>
          <span class="action-detail"></span>
        `;
        label.querySelector(".action-name").textContent = action.label;
        label.querySelector(".action-detail").textContent = action.detail;
        const input = label.querySelector("input");
        input.checked = key === state.action;
        input.addEventListener("change", () => {
          state.action = key;
        });
        els.actions.appendChild(label);
      });
    }

    function setNotice(permission) {
      els.permissionName.textContent = permission?.name || "-";
      const message = permission?.message || "";
      els.permissionNotice.hidden = !message;
      els.permissionNotice.textContent = message;
      els.permissionNotice.classList.toggle("ok", permission?.ok === true);
    }

    function renderLog(events) {
      els.log.replaceChildren();
      if (!events || events.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "No activity yet.";
        els.log.appendChild(empty);
        return;
      }
      events.forEach((event) => {
        const row = document.createElement("div");
        row.className = "log-entry";
        const time = document.createElement("span");
        time.className = "log-time";
        time.textContent = event.time;
        const message = document.createElement("span");
        message.textContent = event.message;
        row.append(time, message);
        els.log.appendChild(row);
      });
    }

    function render(status) {
      state.status = status;
      renderActions(status.actions);
      state.action = status.settings.action;

      els.interval.value = status.settings.interval;
      els.jitter.value = status.settings.jitter;
      els.focusGuard.checked = status.settings.require_roblox_focus;
      els.actions.querySelectorAll("input[name='action']").forEach((input) => {
        input.checked = input.value === state.action;
      });

      els.statusPill.classList.toggle("running", status.running);
      els.statusPill.querySelector("span:last-child").textContent = status.running ? "Running" : "Stopped";
      els.startBtn.disabled = status.running;
      els.stopBtn.disabled = !status.running;
      els.nextAction.textContent = secondsLabel(status.next_action_in);
      els.actionCount.textContent = String(status.action_count);
      els.platformName.textContent = status.platform.name;
      setNotice(status.platform.permission);
      renderLog(status.events);
    }

    async function refresh() {
      try {
        const status = await api("/api/status");
        render(status);
      } catch (error) {
        els.permissionNotice.hidden = false;
        els.permissionNotice.textContent = error.message;
      }
    }

    async function start() {
      const payload = {
        interval: Number(els.interval.value),
        jitter: Number(els.jitter.value),
        action: state.action,
        require_roblox_focus: els.focusGuard.checked,
      };
      const status = await api("/api/start", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      render(status);
    }

    async function stop() {
      const status = await api("/api/stop", {method: "POST", body: "{}"});
      render(status);
    }

    els.startBtn.addEventListener("click", () => start().catch((error) => alert(error.message)));
    els.stopBtn.addEventListener("click", () => stop().catch((error) => alert(error.message)));
    els.refreshBtn.addEventListener("click", refresh);
    setInterval(refresh, 1000);
    refresh();
  </script>
</body>
</html>
"""


class AppHandler(BaseHTTPRequestHandler):
    engine: AntiAfkEngine

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_text(HTML, "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._send_json(self.engine.status())
            return
        self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/start":
                self.engine.start(payload)
                self._send_json(self.engine.status())
                return
            if path == "/api/stop":
                self.engine.stop()
                self._send_json(self.engine.status())
                return
            self._send_json({"error": "Not found."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object.")
        return payload

    def _send_text(
        self,
        body: str,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(
        self,
        data: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        encoded = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def find_open_port(host: str, preferred_port: int) -> int:
    if preferred_port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])

    end_port = min(65535, preferred_port + 49)
    for port in range(preferred_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(
        f"Could not find an open local port from {preferred_port} to {end_port}."
    )


def browser_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    return f"http://{display_host}:{port}"


def make_handler(engine: AntiAfkEngine) -> type[AppHandler]:
    class BoundAppHandler(AppHandler):
        pass

    BoundAppHandler.engine = engine
    return BoundAppHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Roblox Anti-AFK app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=parse_port, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    try:
        controller = make_input_controller()
    except Exception as exc:  # noqa: BLE001 - show startup errors plainly.
        print(f"Failed to initialize input controller: {exc}", file=sys.stderr)
        return 1

    engine = AntiAfkEngine(controller)
    try:
        port = find_open_port(args.host, args.port)
        server = ThreadingHTTPServer((args.host, port), make_handler(engine))
    except OSError as exc:
        print(f"Failed to start local server: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    server.daemon_threads = True
    url = browser_url(args.host, port)

    print(f"Roblox Anti-AFK is running at {url}")
    print("Press Ctrl+C to quit.")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        engine.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
