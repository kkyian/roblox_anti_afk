from __future__ import annotations

import http.client
import json
import socket
import threading
import unittest

import roblox_anti_afk as app


class FakeInputController(app.InputController):
    name = "Test"
    focus_guard_available = True

    def __init__(self, active: bool | None = True) -> None:
        self.active = active
        self.actions: list[str] = []

    def perform(self, action: str) -> None:
        self.actions.append(action)

    def press_space(self) -> None:
        self.actions.append("space")

    def left_click(self) -> None:
        self.actions.append("click")

    def mouse_nudge(self) -> None:
        self.actions.append("nudge")

    def is_roblox_active(self) -> bool | None:
        return self.active

    def permission_state(self) -> dict[str, object]:
        return {"name": "Test permission", "ok": True, "message": "Ready."}


class SettingsParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = app.AntiAfkEngine(FakeInputController())

    def test_defaults(self) -> None:
        settings = self.engine._parse_settings({})

        self.assertEqual(settings.interval, 180)
        self.assertEqual(settings.jitter, 15)
        self.assertEqual(settings.action, "space")
        self.assertTrue(settings.require_roblox_focus)

    def test_clamps_jitter_to_interval_floor(self) -> None:
        settings = self.engine._parse_settings({"interval": 10, "jitter": 300})

        self.assertEqual(settings.jitter, 5)

    def test_accepts_string_false_for_focus_guard(self) -> None:
        settings = self.engine._parse_settings({"require_roblox_focus": "false"})

        self.assertFalse(settings.require_roblox_focus)

    def test_rejects_invalid_focus_guard(self) -> None:
        with self.assertRaisesRegex(ValueError, "true or false"):
            self.engine._parse_settings({"require_roblox_focus": "sometimes"})

    def test_rejects_invalid_action(self) -> None:
        with self.assertRaisesRegex(ValueError, "supported action"):
            self.engine._parse_settings({"action": "jump"})


class PortHelpersTests(unittest.TestCase):
    def test_parse_port_accepts_zero_for_ephemeral_port(self) -> None:
        self.assertEqual(app.parse_port("0"), 0)

    def test_parse_port_rejects_out_of_range_value(self) -> None:
        with self.assertRaises(app.argparse.ArgumentTypeError):
            app.parse_port("70000")

    def test_find_open_port_skips_occupied_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            port = occupied.getsockname()[1]
            if port == 65535:
                self.skipTest("Cannot search past the last TCP port.")

            found = app.find_open_port("127.0.0.1", port)

        self.assertGreaterEqual(found, port)
        self.assertNotEqual(found, port)

    def test_browser_url_uses_loopback_for_wildcard_host(self) -> None:
        self.assertEqual(app.browser_url("0.0.0.0", 8765), "http://127.0.0.1:8765")


class ApiHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = app.AntiAfkEngine(FakeInputController())
        handler = app.make_handler(self.engine)
        self.server = app.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.engine.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(
        self,
        method: str,
        path: str,
        body: object | None = None,
    ) -> tuple[int, dict[str, object]]:
        raw_body = None if body is None else json.dumps(body)
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
        try:
            connection.request(
                method,
                path,
                body=raw_body,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
        finally:
            connection.close()

    def test_status_endpoint(self) -> None:
        status, payload = self.request("GET", "/api/status")

        self.assertEqual(status, 200)
        self.assertFalse(payload["running"])
        self.assertEqual(payload["platform"]["name"], "Test")

    def test_start_endpoint_validates_payload(self) -> None:
        status, payload = self.request(
            "POST",
            "/api/start",
            {"interval": 5, "jitter": 0, "action": "space"},
        )

        self.assertEqual(status, 400)
        self.assertIn("Interval", payload["error"])

    def test_start_and_stop_endpoints(self) -> None:
        status, payload = self.request(
            "POST",
            "/api/start",
            {
                "interval": 10,
                "jitter": 0,
                "action": "nudge",
                "require_roblox_focus": False,
            },
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["running"])
        self.assertEqual(payload["settings"]["action"], "nudge")

        status, payload = self.request("POST", "/api/stop", {})

        self.assertEqual(status, 200)
        self.assertFalse(payload["running"])


if __name__ == "__main__":
    unittest.main()
