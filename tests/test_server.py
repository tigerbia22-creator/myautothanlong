import base64
import copy
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from thanlong.server import Controller, LocalServer


class FakeADB:
    """Simulated device, never sends input to a real emulator."""
    events = []
    image = Image.new("RGB", (100, 60))
    available = [{"serial": "127.0.0.1:5555", "state": "device", "model": "LDPlayer"}]

    def __init__(self, executable="adb", serial=None):
        self.executable, self.serial = executable, serial

    def devices(self):
        return copy.deepcopy(self.available)

    def connect(self, address):
        self.events.append(("connect", address))
        return "connected to " + address

    def screenshot(self):
        if not self.serial:
            raise RuntimeError("Chưa chọn thiết bị")
        return self.image.copy()

    def tap(self, x, y):
        self.events.append(("tap", x, y))

    def swipe(self, x, y, x2, y2, duration_ms):
        self.events.append(("swipe", x, y, x2, y2, duration_ms))

    def keyevent(self, code):
        self.events.append(("keyevent", code))


class ServerTests(unittest.TestCase):
    def setUp(self):
        FakeADB.events = []
        FakeADB.available = [{"serial": "127.0.0.1:5555", "state": "device", "model": "LDPlayer"}]
        FakeADB.image = Image.fromarray(np.random.default_rng(42).integers(0, 256, (60, 100, 3), dtype=np.uint8))
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch("thanlong.server.ADB", FakeADB)
        self.patch.start()
        self.ctl = Controller(Path(self.temp.name))
        self.server = LocalServer(("127.0.0.1", 0), self.ctl)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.ctl.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.patch.stop()
        self.temp.cleanup()

    def request(self, path, body=None, *, token=True, origin=None, raw=None, host=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        method = "POST" if body is not None or raw is not None else "GET"
        headers = {}
        if method == "POST":
            headers["Content-Type"] = "application/json"
            if token:
                headers["X-ThanLong-Token"] = self.server.token
        if origin:
            headers["Origin"] = origin
        if host:
            headers["Host"] = host
        if isinstance(body, dict) and path in {"/api/tap", "/api/swipe", "/api/template"}:
            body = {"capture_id": self.ctl.last_capture_id, **body}
        content = raw if raw is not None else json.dumps(body) if body is not None else None
        connection.request(method, path, body=content, headers=headers)
        response = connection.getresponse()
        result = response.read()
        status = response.status
        mime = response.getheader("Content-Type")
        connection.close()
        return status, json.loads(result) if mime.startswith("application/json") else result

    def select(self):
        status, state = self.request("/api/device", {"adb_path": "LDPlayer path/adb.exe", "connect": False})
        self.assertEqual(status, 200, state)
        self.assertTrue(state["connected"])

    def profile(self, steps=None):
        return {"id": "trung_ac", "name": "Trừng ác", "reference_size": [100, 60], "repeat": 1,
                "steps": steps if steps is not None else [{"id": "tap-1", "action": "tap", "x": 10, "y": 20}]}

    def wait_finished(self):
        deadline = time.monotonic() + 3
        while self.ctl.runner.status()["running"] and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(self.ctl.runner.status()["running"])
        return self.ctl.runner.status()

    def test_initial_profiles_are_explicitly_uncalibrated(self):
        status, state = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(len(state["profiles"]), 2)
        self.assertTrue(all(not p["steps"] and p["reference_size"] is None for p in state["profiles"]))
        status, _ = self.request("/api/run", {"profile_id": "trung_ac"})
        self.assertEqual(status, 400)

    def test_csrf_origin_and_host_guards(self):
        self.assertEqual(self.request("/api/stop", {}, token=False)[0], 403)
        self.assertEqual(self.request("/api/stop", {}, origin="https://outside.example")[0], 403)
        self.assertEqual(self.request("/api/state", host="outside.example")[0], 403)
        self.assertEqual(self.request("/api/stop", {})[0], 200)

    def test_screenshot_and_manual_bounds(self):
        self.assertEqual(self.request("/api/screenshot")[0], 409)
        self.select()
        status, raw = self.request("/api/screenshot")
        self.assertEqual(status, 200)
        self.assertEqual(Image.open(io.BytesIO(raw)).size, (100, 60))
        self.assertEqual(self.request("/api/tap", {"x": 100, "y": 0})[0], 400)
        self.assertEqual(self.request("/api/tap", {"x": 20, "y": 30})[0], 200)
        self.assertIn(("tap", 20, 30), FakeADB.events)
        FakeADB.image = Image.new("RGB", (101, 60))
        self.assertEqual(self.request("/api/tap", {"x": 20, "y": 30})[0], 400)

    def test_image_template_run_and_dry_run(self):
        self.select()
        self.request("/api/screenshot")
        status, template = self.request("/api/template", {"x": 20, "y": 10, "width": 12, "height": 8})
        self.assertEqual(status, 200, template)
        profile = self.profile([{"action": "tap_image", "template": template["template"], "timeout": 0, "threshold": 0.99}])
        self.assertEqual(self.request("/api/profiles/trung_ac", profile)[0], 200)
        self.assertEqual(self.request("/api/run", {"profile_id": "trung_ac", "dry_run": True})[0], 200)
        self.assertIsNone(self.wait_finished()["error"])
        self.assertFalse(FakeADB.events)
        self.assertEqual(self.request("/api/run", {"profile_id": "trung_ac"})[0], 200)
        self.assertIsNone(self.wait_finished()["error"])
        self.assertEqual(FakeADB.events, [("tap", 26, 14)])

    def test_import_export_preserves_templates_and_normalizes_names(self):
        self.select()
        self.request("/api/screenshot")
        _, template = self.request("/api/template", {"x": 3, "y": 4, "width": 10, "height": 10})
        self.request("/api/profiles/trung_ac", self.profile([{"action": "wait_image", "template": template["template"]}]))
        _, bundle = self.request("/api/export/trung_ac")
        self.assertEqual(bundle["format"], "thanlong-profile")
        self.assertIn(template["template"], bundle["templates"])
        status, imported = self.request("/api/import", {"bundle": bundle})
        self.assertEqual(status, 200, imported)
        renamed = imported["steps"][0]["template"]
        self.assertNotEqual(renamed, template["template"])
        self.assertEqual((self.ctl.template_dir / renamed).read_bytes(), base64.b64decode(bundle["templates"][template["template"]]))

    def test_export_ignores_unknown_template_on_coordinate_step(self):
        profile = self.profile()
        profile["steps"][0]["template"] = "../outside.txt"
        (Path(self.temp.name) / "outside.txt").write_text("private test content")
        self.assertEqual(self.request("/api/profiles/trung_ac", profile)[0], 200)
        status, bundle = self.request("/api/export/trung_ac")
        self.assertEqual(status, 200)
        self.assertEqual(bundle["templates"], {})

    def test_new_connection_selects_new_address_instead_of_old_device(self):
        self.select()
        FakeADB.available.append({"serial": "127.0.0.1:5557", "state": "device", "model": "LDPlayer2"})
        status, state = self.request("/api/device", {"address": "127.0.0.1:5557", "connect": True})
        self.assertEqual(status, 200, state)
        self.assertEqual(state["device"]["serial"], "127.0.0.1:5557")

    def test_numeric_overflow_cannot_poison_saved_state(self):
        status, _ = self.request("/api/profiles/trung_ac", raw='{"id":"trung_ac","description":1e999}')
        self.assertEqual(status, 400)
        self.assertEqual(self.request("/api/state")[0], 200)
        self.assertFalse((self.ctl.profile_dir / "trung_ac.json").exists())
        bad = self.profile()
        bad["description"] = float("inf")
        with self.assertRaises(ValueError):
            self.ctl.save_profile("trung_ac", bad)

    def test_stop_prevents_later_taps_and_locks_mutations_while_running(self):
        self.select()
        self.request("/api/profiles/trung_ac", self.profile([
            {"action": "wait", "seconds": 30}, {"action": "tap", "x": 10, "y": 20}]))
        self.assertEqual(self.request("/api/run", {"profile_id": "trung_ac"})[0], 200)
        self.assertEqual(self.request("/api/profiles/trung_ac", self.profile())[0], 400)
        self.assertEqual(self.request("/api/device", {"connect": False})[0], 400)
        self.assertEqual(self.request("/api/stop", {})[0], 200)
        self.assertIsNone(self.wait_finished()["error"])
        self.assertFalse(FakeADB.events)

    def test_settings_and_profile_survive_restart(self):
        self.select()
        self.request("/api/profiles/trung_ac", self.profile())
        reloaded = Controller(Path(self.temp.name))
        self.assertEqual(reloaded.device["serial"], "127.0.0.1:5555")
        self.assertEqual(reloaded.profiles["trung_ac"]["steps"][0]["x"], 10)

    def test_bad_template_and_import_are_rejected_without_files(self):
        profile = self.profile([{"action": "tap_image", "template": "../outside.png"}])
        self.assertEqual(self.request("/api/profiles/trung_ac", profile)[0], 400)
        self.assertEqual(self.request("/api/templates/../outside.png")[0], 400)
        self.assertEqual(self.request("/api/import", {"bundle": {"format": "thanlong-profile", "version": 1,
            "profile": self.profile([{"action": "wait_image", "template": "missing.png"}]), "templates": {}}})[0], 400)
        self.assertFalse(list(self.ctl.template_dir.iterdir()))

    def test_portable_size_limits_apply_before_persisting(self):
        self.select()
        self.ctl.capture()
        with patch("thanlong.server.MAX_TEMPLATE_BYTES", 64):
            with self.assertRaises(ValueError):
                self.ctl.save_template({"x": 0, "y": 0, "width": 12, "height": 12, "capture_id": self.ctl.last_capture_id})
        self.assertFalse(list(self.ctl.template_dir.iterdir()))
        with patch("thanlong.server.MAX_BODY", 100):
            with self.assertRaises(ValueError):
                self.ctl.save_profile("trung_ac", self.profile())
        self.assertFalse((self.ctl.profile_dir / "trung_ac.json").exists())

    def test_guided_preset_is_saved_as_uncalibrated_single_cycle(self):
        status, available = self.request("/api/presets")
        self.assertEqual(status, 200)
        self.assertEqual(len(available[0]["required_templates"]), 11)
        self.assertEqual(available[0]["checkpoints"], 4)
        before = copy.deepcopy(self.ctl.profiles["tang_bao_do"])
        status, draft = self.request("/api/presets/trung_ac_video_1016", {})
        self.assertEqual(status, 200, draft)
        self.assertEqual(len(draft["steps"]), 18)
        self.assertEqual(sum(step["action"] == "confirm" for step in draft["steps"]), 4)
        self.assertTrue(draft["single_cycle"])
        self.assertEqual(self.ctl.profiles["tang_bao_do"], before)
        self.assertEqual(self.request("/api/run", {"profile_id": "trung_ac"})[0], 400)
        draft["repeat"] = 2
        self.assertEqual(self.request("/api/profiles/trung_ac", draft)[0], 400)

    def test_incomplete_preset_roundtrips_without_template_files(self):
        self.request("/api/presets/trung_ac_video_1016", {})
        _, bundle = self.request("/api/export/trung_ac")
        self.assertEqual(bundle["templates"], {})
        status, restored = self.request("/api/import", {"bundle": bundle})
        self.assertEqual(status, 200, restored)
        self.assertEqual(restored["steps"][1]["template"], "")
        self.assertEqual(restored["preset_id"], "trung_ac_video_1016")

    def test_guided_dry_run_waits_for_four_explicit_confirmations(self):
        self.select()
        self.ctl.capture()
        template = self.ctl.save_template({"x": 10, "y": 10, "width": 12, "height": 12, "capture_id": self.ctl.last_capture_id})["template"]
        profile = self.ctl.load_preset("trung_ac_video_1016")
        profile["reference_size"] = [100, 60]
        for step in profile["steps"]:
            step["delay_after"] = 0
            if step["action"] in {"tap_image", "wait_image"}:
                step["template"] = template
                step["timeout"] = 0
        self.ctl.save_profile("trung_ac", profile)
        self.assertEqual(self.request("/api/run", {"profile_id": "trung_ac", "dry_run": True})[0], 200)
        confirmations = []
        deadline = time.monotonic() + 4
        while self.ctl.runner.status()["running"] and time.monotonic() < deadline:
            state = self.ctl.runner.status()
            if state["awaiting_confirmation"]:
                token = state["confirmation_id"]
                self.assertNotIn(token, confirmations)
                self.assertEqual(self.request("/api/confirm", {"confirmation_id": token})[0], 200)
                self.assertEqual(self.request("/api/confirm", {"confirmation_id": token})[0], 400)
                confirmations.append(token)
            else:
                time.sleep(0.005)
        self.assertFalse(self.ctl.runner.status()["running"])
        self.assertIsNone(self.ctl.runner.status()["error"])
        self.assertEqual(len(confirmations), 4)
        self.assertFalse(FakeADB.events)

    def test_stale_screenshot_cannot_control_or_crop_another_device(self):
        self.select()
        self.ctl.capture()
        old_capture = self.ctl.last_capture_id
        FakeADB.available.append({"serial": "127.0.0.1:5557", "state": "device", "model": "LDPlayer2"})
        self.ctl.set_device({"serial": "127.0.0.1:5557", "connect": False})
        self.ctl.capture()
        self.assertNotEqual(self.ctl.last_capture_id, old_capture)
        self.assertEqual(self.request("/api/tap", {"x": 10, "y": 20, "capture_id": old_capture})[0], 400)
        self.assertEqual(self.request("/api/template", {"x": 10, "y": 20, "width": 12, "height": 12, "capture_id": old_capture})[0], 400)
        self.assertFalse(FakeADB.events)
        self.assertEqual(self.request("/api/tap", {"x": 10, "y": 20})[0], 200)


if __name__ == "__main__":
    unittest.main()
