"""Validated, interruptible workflows. No game-specific steps are assumed."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import threading
import time

from PIL import Image

from .vision import match_template


ACTIONS = {"tap", "tap_image", "wait_image", "wait", "swipe", "keyevent"}
KEYS = {"BACK", "ENTER", "HOME", "MENU", "ESCAPE", "TAB"}
_TEMPLATE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,123}\.png", re.IGNORECASE)


def _number(value, label: str, minimum: float, maximum: float, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
        raise ValueError(f"{label} must be a finite number.")
    if integer and not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")
    if not minimum <= value <= maximum:
        raise ValueError(f"{label} must be between {minimum:g} and {maximum:g}.")
    return value


def template_path(template_dir: Path, name: str) -> Path:
    if not isinstance(name, str) or not _TEMPLATE_NAME.fullmatch(name):
        raise ValueError("Template must be a PNG basename using letters, numbers, dots, underscores, or hyphens.")
    base = Path(template_dir).resolve()
    result = base / name
    if result.resolve().parent != base:
        raise ValueError("Template must stay inside the templates folder.")
    return result


def validate_profile(profile: dict, template_dir: Path | None = None) -> dict:
    """Return a validated copy. Empty, uncalibrated drafts can be saved."""
    if not isinstance(profile, dict):
        raise ValueError("Profile must be an object.")
    result = copy.deepcopy(profile)
    if not isinstance(result.get("id"), str) or not 1 <= len(result["id"]) <= 120 or not re.fullmatch(r"[A-Za-z0-9_-]+", result["id"]):
        raise ValueError("Profile id must use 1–120 letters, numbers, underscores, or hyphens.")
    result.setdefault("name", result["id"])
    if not isinstance(result["name"], str) or not result["name"].strip() or len(result["name"]) > 200:
        raise ValueError("Profile name must contain 1–200 characters.")
    result.setdefault("repeat", 1)
    _number(result["repeat"], "repeat", 1, 10000, integer=True)
    result.setdefault("reference_size", None)
    reference = result["reference_size"]
    if reference is not None:
        if not isinstance(reference, (list, tuple)) or len(reference) != 2:
            raise ValueError("reference_size must be [width, height] or null.")
        for dimension in reference:
            _number(dimension, "Screen dimension", 1, 16384, integer=True)
        result["reference_size"] = list(reference)
    steps = result.get("steps", [])
    if not isinstance(steps, list) or len(steps) > 500:
        raise ValueError("Profile must contain a list of at most 500 steps.")
    result["steps"] = steps
    seen_ids = set()
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"Step {index + 1} must be an object.")
        step.setdefault("id", f"step-{index + 1}")
        if not isinstance(step["id"], str) or not 1 <= len(step["id"]) <= 120 or step["id"] in seen_ids:
            raise ValueError("Step ids must be nonempty and unique.")
        seen_ids.add(step["id"])
        action = step.get("action")
        if not isinstance(action, str) or action not in ACTIONS:
            raise ValueError(f"Step {index + 1} has an unsupported action.")
        step.setdefault("name", f"{index + 1}. {action}")
        if not isinstance(step["name"], str) or len(step["name"]) > 200:
            raise ValueError("Step name must be a string of at most 200 characters.")
        step.setdefault("delay_after", 0)
        _number(step["delay_after"], "delay_after", 0, 3600)
        if action in {"tap", "swipe"}:
            coordinate_names = ("x", "y", "x2", "y2") if action == "swipe" else ("x", "y")
            for key in coordinate_names:
                _number(step.get(key), key, 0, 16383, integer=True)
                axis = 0 if key.startswith("x") else 1
                if reference and step[key] >= reference[axis]:
                    raise ValueError(f"Step {index + 1}: {key} is outside reference_size.")
        if action == "swipe":
            step.setdefault("duration_ms", 500)
            _number(step["duration_ms"], "duration_ms", 1, 60000, integer=True)
        elif action in {"tap_image", "wait_image"}:
            name = step.get("template")
            path = template_path(template_dir or Path("."), name)
            if template_dir is not None and not path.is_file():
                raise ValueError(f"Missing template: {name}")
            step.setdefault("threshold", 0.9)
            step.setdefault("timeout", 15)
            _number(step["threshold"], "threshold", 0.1, 1)
            _number(step["timeout"], "timeout", 0, 3600)
            region = step.get("region")
            if region is not None:
                if not isinstance(region, (list, tuple)) or len(region) != 4:
                    raise ValueError("Region must be [x, y, width, height].")
                for j, value in enumerate(region):
                    _number(value, "Region value", 0 if j < 2 else 1, 16384, integer=True)
                if reference and (region[0] + region[2] > reference[0] or region[1] + region[3] > reference[1]):
                    raise ValueError("Search region lies outside reference_size.")
                step["region"] = list(region)
        elif action == "wait":
            _number(step.get("seconds"), "seconds", 0, 3600)
        elif action == "keyevent":
            if not isinstance(step.get("code"), str) or step["code"] not in KEYS:
                raise ValueError("Unsupported key. Use BACK, ENTER, HOME, MENU, ESCAPE, or TAB.")
    return result


class _Stopped(Exception):
    pass


class Runner:
    def __init__(self, adb, template_dir: Path):
        self.adb = adb
        self.template_dir = Path(template_dir)
        self._lock = threading.RLock()
        self._input_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = {"running": False, "stopping": False, "profile_id": None, "step_index": None, "step_name": "", "iteration": 0, "repeat": 0, "dry_run": False, "error": None, "logs": []}

    def status(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._state)

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def _log(self, message: str, level="info"):
        with self._lock:
            self._state["logs"].append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": level, "message": message})
            del self._state["logs"][:-300]

    def start(self, profile: dict, dry_run: bool = False):
        profile = validate_profile(profile, self.template_dir)
        if not profile["steps"]:
            raise ValueError("Add workflow steps before starting.")
        if not profile["reference_size"]:
            raise ValueError("Capture the device screen and set reference_size before starting.")
        if not isinstance(dry_run, bool):
            raise ValueError("dry_run must be true or false.")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("A workflow is already running. Stop it before starting another.")
            self._stop.clear()
            self._state = {"running": True, "stopping": False, "profile_id": profile["id"], "step_index": None, "step_name": "", "iteration": 0, "repeat": profile["repeat"], "dry_run": dry_run, "error": None, "logs": []}
            self._thread = threading.Thread(target=self._run, args=(profile, dry_run), name="thanlong-runner", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            if self._state["running"]:
                self._state["stopping"] = True
        # Wait for any input already in flight; none may begin after stop returns.
        with self._input_lock:
            pass

    def _check_stop(self):
        if self._stop.is_set():
            raise _Stopped()

    def _wait(self, seconds: float):
        if self._stop.wait(seconds):
            raise _Stopped()

    def _capture(self, reference_size):
        self._check_stop()
        image = self.adb.screenshot()
        self._check_stop()
        if list(image.size) != list(reference_size):
            raise ValueError(f"Screen size changed: expected {reference_size[0]}×{reference_size[1]}, received {image.width}×{image.height}. Recalibrate the profile.")
        return image

    def _input(self, function, *args):
        with self._input_lock:
            self._check_stop()
            function(*args)

    def _wait_image(self, step, reference_size):
        path = template_path(self.template_dir, step["template"])
        with Image.open(path) as source:
            template = source.convert("RGB")
        deadline = time.monotonic() + step["timeout"]
        best_score = -1.0
        while True:
            screen = self._capture(reference_size)
            match = match_template(screen, template, step.get("region"))
            self._check_stop()
            best_score = max(best_score, match["score"])
            if match["score"] >= step["threshold"]:
                self._log(f"Matched {step['template']}: {match['score']:.3f} at ({match['x']}, {match['y']}).")
                return match
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Image not found: {step['template']} (best score {best_score:.3f}, required {step['threshold']:.3f}). Workflow stopped without tapping.")
            self._wait(min(0.35, remaining))

    def _run(self, profile, dry_run):
        try:
            self._log("Dry run started; no input will be sent." if dry_run else "Workflow started.")
            self._capture(profile["reference_size"])
            for iteration in range(1, profile["repeat"] + 1):
                self._update(iteration=iteration)
                for index, step in enumerate(profile["steps"]):
                    self._check_stop()
                    self._update(step_index=index, step_name=step["name"])
                    action = step["action"]
                    self._log(f"{iteration}/{profile['repeat']} · {step['name']} ({action})")
                    if action in {"tap_image", "wait_image"}:
                        match = self._wait_image(step, profile["reference_size"])
                        if action == "tap_image" and not dry_run:
                            self._input(self.adb.tap, match["x"] + match["width"] // 2, match["y"] + match["height"] // 2)
                    elif action == "wait":
                        self._wait(step["seconds"])
                    else:
                        self._capture(profile["reference_size"])
                        if not dry_run:
                            if action == "tap":
                                self._input(self.adb.tap, step["x"], step["y"])
                            elif action == "swipe":
                                self._input(self.adb.swipe, step["x"], step["y"], step["x2"], step["y2"], step["duration_ms"])
                            elif action == "keyevent":
                                self._input(self.adb.keyevent, step["code"])
                    self._wait(step["delay_after"])
            self._log("Dry run completed." if dry_run else "Workflow completed.")
        except _Stopped:
            self._log("Workflow stopped by user.")
        except Exception as exc:
            self._update(error=str(exc))
            self._log(str(exc), "error")
        finally:
            self._update(running=False, stopping=False)
