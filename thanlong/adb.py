"""Small, shell-free Android Debug Bridge client for LDPlayer and Android."""

from __future__ import annotations

import io
import os
import re
import subprocess
from typing import Any

from PIL import Image


class ADBError(RuntimeError):
    """An ADB operation could not be completed."""


class ADB:
    def __init__(self, executable: str = "adb", serial: str | None = None):
        self.executable = os.environ.get("ADB_PATH", "adb") if executable == "adb" else executable
        if not isinstance(self.executable, str) or not self.executable.strip():
            raise ValueError("ADB executable must be a nonempty path or command name.")
        if serial is not None:
            self._validate_serial(serial)
        self.serial = serial

    @staticmethod
    def _validate_serial(serial: str) -> None:
        if not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9_\[\]][A-Za-z0-9_.:\-\[\]]{0,255}", serial):
            raise ValueError("Invalid ADB device serial.")

    def _run(self, args: list[str], *, selected: bool = False, timeout: float = 15) -> subprocess.CompletedProcess:
        command = [self.executable]
        if selected:
            if not self.serial:
                raise ADBError("Select an ADB device before capturing the screen or sending input.")
            self._validate_serial(self.serial)
            command += ["-s", self.serial]
        command += args
        options: dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout, check=False, **options)
        except FileNotFoundError as exc:
            raise ADBError("ADB was not found. Set ADB_PATH to LDPlayer's adb.exe or install Android Platform Tools.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ADBError(f"ADB timed out after {timeout:g} seconds.") from exc
        except OSError as exc:
            raise ADBError(f"Could not start ADB: {exc}") from exc
        if result.returncode:
            message = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
            raise ADBError(message[:1500] or f"ADB exited with code {result.returncode}.")
        return result

    def devices(self) -> list[dict[str, str]]:
        output = self._run(["devices", "-l"]).stdout.decode("utf-8", errors="replace")
        found = []
        for line in output.splitlines():
            fields = line.strip().split()
            if len(fields) < 2 or fields[1] not in {"device", "offline", "unauthorized", "recovery", "bootloader", "sideload", "no"}:
                continue
            model = next((field.split(":", 1)[1] for field in fields[2:] if field.startswith("model:")), "")
            state = "no permissions" if fields[1] == "no" else fields[1]
            found.append({"serial": fields[0], "state": state, "model": model})
        return found

    def connect(self, address: str) -> str:
        if not isinstance(address, str) or not re.fullmatch(r"(?:[A-Za-z0-9][A-Za-z0-9.-]*|\[[0-9A-Fa-f:]+\]):[0-9]{1,5}", address):
            raise ValueError("Enter an ADB address such as 127.0.0.1:5555.")
        port = int(address.rsplit(":", 1)[1])
        if not 1 <= port <= 65535:
            raise ValueError("ADB port must be between 1 and 65535.")
        message = self._run(["connect", address], timeout=20).stdout.decode("utf-8", errors="replace").strip()
        if any(part in message.lower() for part in ("failed", "unable", "cannot", "refused", "timed out")):
            raise ADBError(message[:1500])
        return message

    def screenshot(self) -> Image.Image:
        data = self._run(["exec-out", "screencap", "-p"], selected=True).stdout
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG":
                    raise ValueError("ADB did not return a PNG screenshot.")
                return image.convert("RGB")
        except (OSError, ValueError) as exc:
            raise ADBError("Could not decode the device screenshot. Check that the selected device is ready.") from exc

    @staticmethod
    def _integer(value: int, minimum: int, maximum: int, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{label} must be an integer between {minimum} and {maximum}.")
        return value

    def tap(self, x: int, y: int) -> None:
        x = self._integer(x, 0, 16383, "x")
        y = self._integer(y, 0, 16383, "y")
        self._run(["shell", "input", "tap", str(x), str(y)], selected=True)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 500) -> None:
        values = [self._integer(value, 0, 16383, label) for value, label in zip((x1, y1, x2, y2), ("x", "y", "x2", "y2"))]
        duration_ms = self._integer(duration_ms, 1, 60000, "duration_ms")
        self._run(["shell", "input", "swipe", *map(str, values), str(duration_ms)], selected=True, timeout=max(15, duration_ms / 1000 + 5))

    def keyevent(self, code: str) -> None:
        keys = {"BACK", "ENTER", "HOME", "MENU", "ESCAPE", "TAB"}
        if not isinstance(code, str) or code not in keys:
            raise ValueError("Unsupported key. Use BACK, ENTER, HOME, MENU, ESCAPE, or TAB.")
        self._run(["shell", "input", "keyevent", "KEYCODE_" + code], selected=True)
