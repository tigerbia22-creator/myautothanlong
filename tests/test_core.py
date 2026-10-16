from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from thanlong.adb import ADB, ADBError
from thanlong.automation import Runner, validate_profile
from thanlong.vision import match_template


def sample_image():
    return Image.fromarray(np.random.default_rng(42).integers(0, 256, (80, 120, 3), dtype=np.uint8))


class FakeADB:
    def __init__(self, image=None):
        self.image = image if image is not None else sample_image()
        self.calls = []
        self.captures = 0

    def screenshot(self):
        self.captures += 1
        return self.image.copy()

    def tap(self, *values):
        self.calls.append(("tap", *values))

    def swipe(self, *values):
        self.calls.append(("swipe", *values))

    def keyevent(self, *values):
        self.calls.append(("keyevent", *values))


def profile(steps):
    return {"id": "test", "name": "Test", "reference_size": [120, 80], "repeat": 1, "steps": steps}


def wait_finished(runner, timeout=3):
    deadline = time.monotonic() + timeout
    while runner.status()["running"] and time.monotonic() < deadline:
        time.sleep(0.01)
    if runner.status()["running"]:
        runner.stop()
        raise AssertionError("Runner did not finish in time")
    return runner.status()


def wait_confirmation(runner, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = runner.status()
        if state["awaiting_confirmation"]:
            return state
        if not state["running"]:
            raise AssertionError(f"Runner ended before confirmation: {state['error']}")
        time.sleep(0.005)
    runner.stop()
    raise AssertionError("Runner did not reach a confirmation checkpoint")


class VisionTests(unittest.TestCase):
    def test_exact_match_region_has_absolute_coordinates(self):
        image = sample_image()
        template = image.crop((43, 21, 57, 34))
        match = match_template(image, template, [30, 10, 50, 40])
        self.assertEqual((match["x"], match["y"]), (43, 21))
        self.assertGreater(match["score"], 0.999)

    def test_solid_template_does_not_report_arbitrary_perfect_match(self):
        with self.assertRaisesRegex(ValueError, "visual detail"):
            match_template(sample_image(), Image.new("RGB", (10, 10), "white"))

    def test_rejects_outside_region_and_oversized_template(self):
        image = sample_image()
        with self.assertRaises(ValueError):
            match_template(image, image, [110, 0, 20, 20])
        with self.assertRaises(ValueError):
            match_template(image, image, [0, 0, 20, 20])


class ValidationTests(unittest.TestCase):
    def test_single_cycle_is_enforced_before_execution(self):
        source = profile([{"action": "wait", "seconds": 0}])
        source["single_cycle"] = True
        source["repeat"] = 2
        with self.assertRaises(ValueError):
            Runner(FakeADB(), Path(".")).start(source)
        source["single_cycle"] = "true"
        source["repeat"] = 1
        with self.assertRaises(ValueError):
            validate_profile(source)

    def test_defaults_are_added_without_mutating_input(self):
        original = profile([{"action": "tap", "x": 8, "y": 12}])
        before = copy.deepcopy(original)
        result = validate_profile(original)
        self.assertEqual(original, before)
        self.assertEqual(result["steps"][0]["delay_after"], 0)

    def test_rejects_outside_coordinates_and_invalid_numbers(self):
        for step in [{"action": "tap", "x": 120, "y": 0}, {"action": "wait", "seconds": float("nan")}, {"action": "wait", "seconds": 10 ** 1000}, {"action": "wait", "seconds": True}, {"action": "swipe", "x": 0, "y": 0, "x2": 5, "y2": 5, "duration_ms": 0}]:
            with self.subTest(step=step), self.assertRaises(ValueError):
                validate_profile(profile([step]))

    def test_rejects_template_traversal_and_unsafe_keys(self):
        for step in [{"action": "tap_image", "template": "../outside.png"}, {"action": "keyevent", "code": "BACK;reboot"}]:
            with self.subTest(step=step), self.assertRaises(ValueError):
                validate_profile(profile([step]))

    def test_missing_template_is_reported(self):
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, "Missing template"):
            validate_profile(profile([{"action": "wait_image", "template": "missing.png"}]), Path(folder))

    def test_incomplete_visual_draft_can_be_saved_but_cannot_run(self):
        for action in ("tap_image", "wait_image"):
            for step in ({"action": action}, {"action": action, "template": ""}):
                with self.subTest(step=step), tempfile.TemporaryDirectory() as folder:
                    original = profile([step])
                    normalized = validate_profile(original, Path(folder))
                    self.assertEqual(normalized["steps"][0]["template"], "")
                    adb = FakeADB()
                    runner = Runner(adb, Path(folder))
                    with self.assertRaisesRegex(ValueError, "Chưa gán ảnh mẫu"):
                        runner.start(normalized)
                    self.assertFalse(runner.status()["running"])
                    self.assertEqual(adb.captures, 0)
                    self.assertEqual(adb.calls, [])

    def test_confirmation_prompt_and_timeout_validation(self):
        valid = validate_profile(profile([{"action": "confirm", "prompt": "  Kiểm tra phần thưởng  "}]))
        self.assertEqual(valid["steps"][0]["timeout"], 600)
        self.assertEqual(valid["steps"][0]["prompt"], "Kiểm tra phần thưởng")
        for prompt in (None, "", " \n ", "x" * 1001, False):
            with self.subTest(prompt=prompt), self.assertRaises(ValueError):
                validate_profile(profile([{"action": "confirm", "prompt": prompt}]))
        for timeout in (0, 3601, float("nan"), True, "600"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                validate_profile(profile([{"action": "confirm", "prompt": "Tiếp tục?", "timeout": timeout}]))


class RunnerTests(unittest.TestCase):
    def test_image_tap_hits_detected_center(self):
        adb = FakeADB()
        with tempfile.TemporaryDirectory() as folder:
            adb.image.crop((43, 21, 57, 35)).save(Path(folder) / "button.png")
            runner = Runner(adb, Path(folder))
            runner.start(profile([{"action": "tap_image", "template": "button.png", "timeout": 0}]))
            status = wait_finished(runner)
        self.assertIsNone(status["error"])
        self.assertEqual(adb.calls, [("tap", 50, 28)])

    def test_missing_visual_stops_without_any_input(self):
        adb = FakeADB()
        with tempfile.TemporaryDirectory() as folder:
            Image.fromarray(np.random.default_rng(8).integers(0, 256, (15, 15, 3), dtype=np.uint8)).save(Path(folder) / "button.png")
            runner = Runner(adb, Path(folder))
            runner.start(profile([{"action": "tap_image", "template": "button.png", "timeout": 0, "threshold": 0.99}, {"action": "tap", "x": 1, "y": 1}]))
            status = wait_finished(runner)
        self.assertIn("Image not found", status["error"])
        self.assertEqual(adb.calls, [])

    def test_dry_run_checks_visuals_without_input(self):
        adb = FakeADB()
        with tempfile.TemporaryDirectory() as folder:
            adb.image.crop((0, 0, 10, 10)).save(Path(folder) / "button.png")
            runner = Runner(adb, Path(folder))
            runner.start(profile([{"action": "tap", "x": 1, "y": 1}, {"action": "tap_image", "template": "button.png"}, {"action": "keyevent", "code": "BACK"}]), dry_run=True)
            status = wait_finished(runner)
        self.assertIsNone(status["error"])
        self.assertGreaterEqual(adb.captures, 4)
        self.assertEqual(adb.calls, [])

    def test_resolution_change_stops_before_input(self):
        adb = FakeADB(Image.new("RGB", (121, 80)))
        runner = Runner(adb, Path("."))
        runner.start(profile([{"action": "tap", "x": 1, "y": 1}]))
        status = wait_finished(runner)
        self.assertIn("Screen size changed", status["error"])
        self.assertEqual(adb.calls, [])

    def test_stop_interrupts_wait_and_prevents_later_tap(self):
        adb = FakeADB()
        runner = Runner(adb, Path("."))
        runner.start(profile([{"action": "wait", "seconds": 60}, {"action": "tap", "x": 1, "y": 1}]))
        deadline = time.monotonic() + 1
        while runner.status()["step_index"] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        runner.stop()
        status = wait_finished(runner)
        self.assertIsNone(status["error"])
        self.assertEqual(adb.calls, [])

    def test_only_one_workflow_and_requires_calibration(self):
        runner = Runner(FakeADB(), Path("."))
        draft = profile([{"action": "wait", "seconds": 60}])
        draft["reference_size"] = None
        with self.assertRaisesRegex(ValueError, "reference_size"):
            runner.start(draft)
        runner.start(profile([{"action": "wait", "seconds": 60}]))
        with self.assertRaises(RuntimeError):
            runner.start(profile([{"action": "wait", "seconds": 1}]))
        runner.stop()
        wait_finished(runner)

    def test_confirmation_blocks_later_input_until_explicit_approval(self):
        adb = FakeADB()
        runner = Runner(adb, Path("."))
        runner.start(profile([{"action": "confirm", "prompt": "Đã sẵn sàng?"}, {"action": "tap", "x": 10, "y": 20}]))
        pending = wait_confirmation(runner)
        self.assertEqual(pending["confirmation_prompt"], "Đã sẵn sàng?")
        self.assertEqual(adb.calls, [])
        with self.assertRaises(ValueError):
            runner.confirm("wrong-token")
        self.assertEqual(adb.calls, [])
        runner.confirm(pending["confirmation_id"])
        status = wait_finished(runner)
        self.assertIsNone(status["error"])
        self.assertEqual(adb.calls, [("tap", 10, 20)])
        self.assertFalse(status["awaiting_confirmation"])
        self.assertIsNone(status["confirmation_id"])
        with self.assertRaises(ValueError):
            runner.confirm(pending["confirmation_id"])

    def test_checkpoint_token_cannot_release_a_later_checkpoint(self):
        adb = FakeADB()
        runner = Runner(adb, Path("."))
        runner.start(profile([{"action": "confirm", "prompt": "Bước một"}, {"action": "confirm", "prompt": "Bước hai"}, {"action": "tap", "x": 10, "y": 20}]))
        first = wait_confirmation(runner)
        runner.confirm(first["confirmation_id"])
        second = wait_confirmation(runner)
        self.assertNotEqual(first["confirmation_id"], second["confirmation_id"])
        with self.assertRaises(ValueError):
            runner.confirm(first["confirmation_id"])
        self.assertEqual(adb.calls, [])
        runner.confirm(second["confirmation_id"])
        self.assertIsNone(wait_finished(runner)["error"])
        self.assertEqual(adb.calls, [("tap", 10, 20)])

    def test_stop_interrupts_confirmation_without_later_input(self):
        adb = FakeADB()
        runner = Runner(adb, Path("."))
        runner.start(profile([{"action": "confirm", "prompt": "Tiếp tục?"}, {"action": "tap", "x": 10, "y": 20}]))
        pending = wait_confirmation(runner)
        runner.stop()
        status = wait_finished(runner)
        self.assertIsNone(status["error"])
        self.assertFalse(status["awaiting_confirmation"])
        self.assertIsNone(status["confirmation_id"])
        self.assertEqual(status["confirmation_prompt"], "")
        self.assertEqual(adb.calls, [])
        with self.assertRaises(ValueError):
            runner.confirm(pending["confirmation_id"])

    def test_confirmation_token_from_previous_run_cannot_resume_new_run(self):
        runner = Runner(FakeADB(), Path("."))
        workflow = profile([{"action": "confirm", "prompt": "Tiếp tục?"}])
        runner.start(workflow)
        first = wait_confirmation(runner)
        runner.confirm(first["confirmation_id"])
        wait_finished(runner)
        runner.start(workflow)
        second = wait_confirmation(runner)
        self.assertNotEqual(first["confirmation_id"], second["confirmation_id"])
        with self.assertRaises(ValueError):
            runner.confirm(first["confirmation_id"])
        self.assertTrue(runner.status()["awaiting_confirmation"])
        runner.confirm(second["confirmation_id"])
        self.assertIsNone(wait_finished(runner)["error"])

    def test_confirmation_timeout_clears_state_and_stops_without_input(self):
        adb = FakeADB()
        runner = Runner(adb, Path("."))
        runner.start(profile([{"action": "confirm", "prompt": "Tiếp tục?", "timeout": 1}, {"action": "tap", "x": 10, "y": 20}]))
        pending = wait_confirmation(runner)
        status = wait_finished(runner)
        self.assertIn("Hết thời gian chờ xác nhận", status["error"])
        self.assertFalse(status["awaiting_confirmation"])
        self.assertIsNone(status["confirmation_id"])
        self.assertEqual(adb.calls, [])
        with self.assertRaises(ValueError):
            runner.confirm(pending["confirmation_id"])

    def test_dry_run_still_requires_confirmation_and_sends_no_input(self):
        adb = FakeADB()
        runner = Runner(adb, Path("."))
        runner.start(profile([{"action": "confirm", "prompt": "Kiểm tra trước khi tiếp tục"}, {"action": "tap", "x": 10, "y": 20}]), dry_run=True)
        pending = wait_confirmation(runner)
        self.assertTrue(pending["dry_run"])
        self.assertEqual(adb.calls, [])
        runner.confirm(pending["confirmation_id"])
        self.assertIsNone(wait_finished(runner)["error"])
        self.assertEqual(adb.calls, [])


class ADBTests(unittest.TestCase):
    @patch("thanlong.adb.subprocess.run")
    def test_executable_with_spaces_uses_argument_array(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, b"", b"")
        adb = ADB(r"C:\Program Files\LDPlayer\adb.exe", "127.0.0.1:5555")
        adb.tap(10, 20)
        self.assertEqual(run.call_args.args[0], [r"C:\Program Files\LDPlayer\adb.exe", "-s", "127.0.0.1:5555", "shell", "input", "tap", "10", "20"])
        self.assertNotIn("shell", run.call_args.kwargs)

    @patch("thanlong.adb.subprocess.run")
    def test_screenshot_requires_explicit_device(self, run):
        with self.assertRaisesRegex(ADBError, "Select"):
            ADB().screenshot()
        run.assert_not_called()

    @patch("thanlong.adb.subprocess.run")
    def test_devices_parses_unauthorized_and_model(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, b"List of devices attached\nemulator-5554 device product:test model:LDPlayer device:test\n127.0.0.1:5555 unauthorized\n", b"")
        self.assertEqual(ADB().devices(), [{"serial": "emulator-5554", "state": "device", "model": "LDPlayer"}, {"serial": "127.0.0.1:5555", "state": "unauthorized", "model": ""}])

    @patch.dict(os.environ, {"ADB_PATH": r"C:\LDPlayer\adb.exe"})
    def test_existing_environment_path_is_used(self):
        self.assertEqual(ADB().executable, r"C:\LDPlayer\adb.exe")

    def test_connect_rejects_shell_and_out_of_range_port(self):
        for address in ["127.0.0.1:5555;whoami", "127.0.0.1:99999", "--help"]:
            with self.subTest(address=address), self.assertRaises(ValueError):
                ADB().connect(address)


if __name__ == "__main__":
    unittest.main()
