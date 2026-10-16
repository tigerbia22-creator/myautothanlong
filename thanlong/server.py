"""Loopback-only control panel. No game credentials or game protocol access."""
from __future__ import annotations

import argparse
import base64
import binascii
import copy
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import uuid
import webbrowser

from PIL import Image

from .adb import ADB, ADBError
from .automation import Runner, template_path, validate_profile
from .presets import PRESET_ID, build_preset, list_presets
from .ocr import OCRReader
from .auto_quest import OCRQuestRunner, validate_config

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = ROOT.parent / ".local"
PROFILE_NAMES = {"trung_ac": "Trừng ác", "tang_bao_do": "Tàng bảo đồ"}
MAX_BODY = 16 * 1024 * 1024
MAX_TEMPLATE_BYTES = 4 * 1024 * 1024
MAX_TEMPLATE_TOTAL = 10 * 1024 * 1024
MAX_TEMPLATE_PIXELS = 16_777_216
TEMPLATE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,123}\.png\Z")


def find_adb() -> str:
    explicit = os.environ.get("ADB_PATH")
    if explicit:
        return explicit
    found = shutil.which("adb")
    if found:
        return found
    if os.name == "nt":
        for path in [r"C:\LDPlayer\LDPlayer9\adb.exe",
                     r"C:\LDPlayer\LDPlayer4.0\adb.exe",
                     r"C:\XuanZhi\LDPlayer\adb.exe",
                     r"D:\LDPlayer\LDPlayer9\adb.exe"]:
            if Path(path).is_file():
                return path
    return "adb"


def write_json(path: Path, value: dict) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


def integer(value, name, low=0, high=16383):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name}: cần số nguyên trong khoảng {low}–{high}.")
    return value


class Controller:
    def __init__(self, data_dir: Path, adb_path: str | None = None, ocr_reader=None):
        self.data_dir = Path(data_dir)
        self.template_dir = self.data_dir / "templates"
        self.profile_dir = self.data_dir / "profiles"
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.device = {"adb_path": find_adb(), "serial": None, "address": "127.0.0.1:5555"}
        settings = self.data_dir / "device.json"
        if settings.exists():
            stored = json.loads(settings.read_text(encoding="utf-8"))
            for key in self.device:
                if key in stored:
                    self.device[key] = stored[key]
        if adb_path:
            self.device["adb_path"] = adb_path
        self.adb = ADB(self.device["adb_path"], self.device["serial"])
        self.runner = Runner(self.adb, self.template_dir)
        self.ocr = ocr_reader or OCRReader()
        self.ai_runner = OCRQuestRunner(self.adb, self.ocr)
        self.last_mode = "manual"
        self.ai_config = {"reference_size": None, "quest_slot": None, "return_slot": None,
                          "npc_anchor": None, "auto_toggle": None, "return_map": "Tô Châu", "repeat": 1, "allow_teleport": False}
        ai_path = self.data_dir / "ai_config.json"
        if ai_path.is_file():
            try:
                saved = json.loads(ai_path.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    self.ai_config.update(saved)
            except (OSError, ValueError):
                pass
        self.devices = []
        self.device_error = None
        self.last_image = None
        self.last_serial = None
        self.last_capture_id = None
        self.profiles = {}
        for profile_id, name in PROFILE_NAMES.items():
            path = self.profile_dir / f"{profile_id}.json"
            if path.exists():
                profile = json.loads(path.read_text(encoding="utf-8"))
                profile["id"] = profile_id
                self.profiles[profile_id] = validate_profile(profile, self.template_dir)
            else:
                self.profiles[profile_id] = {
                    "id": profile_id, "name": name,
                    "description": "Chưa có luồng được xác minh từ clip. Hãy ghi thao tác trên LDPlayer trước khi chạy.",
                    "reference_size": None, "repeat": 1, "steps": [],
                }

    def _idle(self):
        if self.runner.status()["running"] or self.ai_runner.status()["running"]:
            raise ValueError("Hãy dừng auto trước khi đổi thiết bị hoặc chỉnh thao tác.")

    def state(self):
        with self.lock:
            return {"device": {**self.device, "error": self.device_error},
                    "devices": copy.deepcopy(self.devices),
                    "profiles": copy.deepcopy(list(self.profiles.values())),
                    "runner": self.ai_runner.status() if self.last_mode == "ai" else self.runner.status(),
                    "ai": self.ai_state(),
                    "connected": any(d["serial"] == self.device["serial"] and d["state"] == "device"
                                     for d in self.devices)}

    def set_device(self, body):
        with self.lock:
            self._idle()
            path = body.get("adb_path", self.device["adb_path"])
            if not isinstance(path, str) or not path.strip() or len(path) > 4096 or "\x00" in path:
                raise ValueError("Đường dẫn adb không hợp lệ.")
            address = body.get("address", self.device["address"])
            if not isinstance(address, str):
                raise ValueError("Địa chỉ ADB không hợp lệ.")
            serial = body.get("serial") or None
            if serial is not None and (not isinstance(serial, str) or len(serial) > 256):
                raise ValueError("Mã thiết bị không hợp lệ.")
            if not isinstance(body.get("connect", False), bool):
                raise ValueError("connect cần là true hoặc false.")
            candidate = ADB(path, serial)
            try:
                if body.get("connect"):
                    match = re.fullmatch(r"(?:127\.0\.0\.1|localhost):([0-9]{1,5})", address)
                    if not match or not 1 <= int(match.group(1)) <= 65535:
                        raise ValueError("LDPlayer: dùng 127.0.0.1:cổng hoặc localhost:cổng.")
                    candidate.connect(address)
                devices = candidate.devices()
                ready = [d["serial"] for d in devices if d["state"] == "device"]
                if serial is None and body.get("connect"):
                    if address in ready:
                        serial = address
                    elif address.startswith("localhost:") and address.replace("localhost:", "127.0.0.1:", 1) in ready:
                        serial = address.replace("localhost:", "127.0.0.1:", 1)
                    else:
                        raise ValueError("Đã gửi kết nối nhưng địa chỉ này chưa có trạng thái device. Hãy làm mới và chọn đúng phiên.")
                if serial is None and self.device["serial"] in ready:
                    serial = self.device["serial"]
                if serial is None and len(ready) == 1:
                    serial = ready[0]
                if serial is not None and serial not in ready:
                    raise ValueError("Thiết bị chưa sẵn sàng. Kiểm tra ADB và chọn lại đúng phiên LDPlayer.")
            except (ADBError, ValueError) as exc:
                self.device_error = str(exc)
                raise
            candidate.serial = serial
            self.device = {"adb_path": path, "serial": serial, "address": address}
            self.devices = devices
            self.device_error = None
            self.adb = candidate
            self.runner = Runner(candidate, self.template_dir)
            self.ai_runner = OCRQuestRunner(candidate, self.ocr)
            self.last_mode = "manual"
            self.last_image = None
            self.last_serial = None
            self.last_capture_id = None
            write_json(self.data_dir / "device.json", self.device)
            return self.state()

    def capture(self):
        with self.lock:
            image = self.adb.screenshot().convert("RGB")
            if image.width > 16384 or image.height > 16384:
                raise ValueError("Ảnh màn hình vượt kích thước hỗ trợ.")
            self.last_image = image.copy()
            self.last_serial = self.device["serial"]
            self.last_capture_id = uuid.uuid4().hex
            return image

    def _check_capture(self, body):
        if self.last_image is None or self.last_serial != self.device["serial"]:
            raise ValueError("Chụp màn hình của thiết bị đã chọn trước khi ghi thao tác.")
        if not self.last_capture_id or body.get("capture_id") != self.last_capture_id:
            raise ValueError("Ảnh đang xem đã cũ hoặc thuộc phiên khác. Chụp lại màn hình trước khi bấm hoặc gán ảnh.")

    def manual_input(self, body, swipe=False):
        with self.lock:
            self._idle()
            self._check_capture(body)
            current = self.adb.screenshot()
            if current.size != self.last_image.size:
                raise ValueError("Độ phân giải đã thay đổi. Hãy chụp lại màn hình.")
            x = integer(body.get("x"), "x", high=current.width - 1)
            y = integer(body.get("y"), "y", high=current.height - 1)
            if swipe:
                x2 = integer(body.get("x2"), "x2", high=current.width - 1)
                y2 = integer(body.get("y2"), "y2", high=current.height - 1)
                duration = integer(body.get("duration_ms", 300), "duration_ms", 1, 60000)
                self.adb.swipe(x, y, x2, y2, duration)
            else:
                self.adb.tap(x, y)
            return {"ok": True}

    def save_template(self, body):
        with self.lock:
            self._idle()
            self._check_capture(body)
            x = integer(body.get("x"), "x", high=self.last_image.width - 1)
            y = integer(body.get("y"), "y", high=self.last_image.height - 1)
            width = integer(body.get("width"), "width", 4, self.last_image.width - x)
            height = integer(body.get("height"), "height", 4, self.last_image.height - y)
            if width * height > MAX_TEMPLATE_PIXELS:
                raise ValueError("Ảnh mẫu tối đa 16 megapixel. Hãy chọn vùng nút nhỏ hơn.")
            crop = self.last_image.crop((x, y, x + width, y + height))
            encoded = io.BytesIO()
            crop.save(encoded, format="PNG")
            if encoded.tell() > MAX_TEMPLATE_BYTES:
                raise ValueError("Ảnh mẫu tối đa 4 MiB. Hãy chọn vùng nhỏ hơn.")
            name = uuid.uuid4().hex + ".png"
            (self.template_dir / name).write_bytes(encoded.getvalue())
            return {"template": name, "width": width, "height": height}

    def save_profile(self, profile_id, body):
        with self.lock:
            self._idle()
            if profile_id not in PROFILE_NAMES:
                raise ValueError("Hồ sơ không tồn tại.")
            body = copy.deepcopy(body)
            body["id"] = profile_id
            if body.get("preset_id") == PRESET_ID and (body.get("repeat", 1) != 1 or isinstance(body.get("repeat"), bool)):
                raise ValueError("Kịch bản theo clip chỉ chạy một vòng. Hãy kiểm tra kết quả trước khi bắt đầu vòng tiếp theo.")
            normalized = validate_profile(body, self.template_dir)
            self._portable_bundle(normalized)
            write_json(self.profile_dir / f"{profile_id}.json", normalized)
            self.profiles[profile_id] = normalized
            return copy.deepcopy(normalized)

    def export_profile(self, profile_id):
        with self.lock:
            profile = copy.deepcopy(self.profiles[profile_id])
            return self._portable_bundle(profile)

    def _portable_bundle(self, profile):
        names = {step["template"] for step in profile["steps"] if step["action"] in {"tap_image", "wait_image"} and step.get("template")}
        templates = {}
        total = 0
        for name in sorted(names):
            path = template_path(self.template_dir, name)
            size = path.stat().st_size
            total += size
            if size > MAX_TEMPLATE_BYTES or total > MAX_TEMPLATE_TOTAL:
                raise ValueError("Mỗi ảnh mẫu tối đa 4 MiB, tổng ảnh một hồ sơ tối đa 10 MiB.")
            with Image.open(path) as image:
                if image.format != "PNG" or image.width < 4 or image.height < 4 or image.width * image.height > MAX_TEMPLATE_PIXELS:
                    raise ValueError("Ảnh mẫu cần là PNG từ 4×4 đến 16 megapixel.")
            templates[name] = base64.b64encode(path.read_bytes()).decode("ascii")
        bundle = {"format": "thanlong-profile", "version": 1, "profile": profile, "templates": templates}
        if len(json.dumps({"bundle": bundle}, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_BODY:
            raise ValueError("Hồ sơ vượt giới hạn nhập/xuất 16 MiB. Giảm ảnh mẫu hoặc chia thành hồ sơ nhỏ hơn.")
        return bundle

    def import_profile(self, body):
        with self.lock:
            self._idle()
            bundle = body.get("bundle")
            if not isinstance(bundle, dict) or bundle.get("format") != "thanlong-profile" or bundle.get("version") != 1:
                raise ValueError("Tệp hồ sơ không đúng định dạng thanlong-profile v1.")
            profile = bundle.get("profile")
            if not isinstance(profile, dict) or profile.get("id") not in PROFILE_NAMES:
                raise ValueError("Hồ sơ chỉ hỗ trợ trung_ac hoặc tang_bao_do.")
            profile = validate_profile(profile)
            templates = bundle.get("templates", {})
            if not isinstance(templates, dict) or len(templates) > 500:
                raise ValueError("Danh sách ảnh mẫu không hợp lệ.")
            needed = {step["template"] for step in profile["steps"] if step["action"] in {"tap_image", "wait_image"} and step.get("template")}
            if needed != set(templates):
                raise ValueError("Các ảnh mẫu trong tệp không khớp với các bước của hồ sơ.")
            staged = []
            mapping = {}
            try:
                for old, encoded in templates.items():
                    if not isinstance(old, str) or not TEMPLATE_NAME.fullmatch(old) or not isinstance(encoded, str):
                        raise ValueError("Tên hoặc nội dung ảnh mẫu không hợp lệ.")
                    try:
                        raw = base64.b64decode(encoded, validate=True)
                    except (ValueError, binascii.Error) as exc:
                        raise ValueError("Ảnh mẫu base64 không hợp lệ.") from exc
                    if len(raw) > MAX_TEMPLATE_BYTES:
                        raise ValueError("Ảnh mẫu quá lớn (tối đa 4 MiB).")
                    with Image.open(io.BytesIO(raw)) as source:
                        if source.format != "PNG" or source.width < 4 or source.height < 4 or source.width * source.height > MAX_TEMPLATE_PIXELS:
                            raise ValueError("Cần ảnh mẫu PNG từ 4×4, tối đa 16 megapixel.")
                        image = source.convert("RGB")
                    new = uuid.uuid4().hex + ".png"
                    dest = self.template_dir / new
                    staged.append(dest)
                    image.save(dest, "PNG")
                    mapping[old] = new
                for step in profile["steps"]:
                    if step["action"] in {"tap_image", "wait_image"} and step.get("template"):
                        step["template"] = mapping[step["template"]]
                return self.save_profile(profile["id"], profile)
            except Exception:
                for path in staged:
                    path.unlink(missing_ok=True)
                raise

    def run(self, body):
        with self.lock:
            self._idle()
            profile_id = body.get("profile_id")
            if profile_id not in self.profiles:
                raise ValueError("Chọn hồ sơ trước khi chạy.")
            dry_run = body.get("dry_run", False)
            if not isinstance(dry_run, bool):
                raise ValueError("dry_run cần là true hoặc false.")
            self.runner.start(copy.deepcopy(self.profiles[profile_id]), dry_run=dry_run)
            self.last_mode = "manual"
            return self.runner.status()

    def stop(self):
        with self.lock:
            self.runner.stop()
            self.ai_runner.stop()
            return self.ai_runner.status() if self.last_mode == "ai" else self.runner.status()

    def confirm(self, body):
        with self.lock:
            self.runner.confirm(body.get("confirmation_id"))
            return self.runner.status()

    def load_preset(self, preset_id):
        with self.lock:
            self._idle()
            draft = build_preset(preset_id, self.profiles["trung_ac"])
            return self.save_profile("trung_ac", draft)

    def ai_state(self):
        configured = False
        try:
            validate_config(self.ai_config)
            configured = self.ai_config.get("device_serial") == self.device["serial"] and bool(self.device["serial"])
        except (ValueError, TypeError):
            pass
        return {**self.ocr.info(), "config": copy.deepcopy(self.ai_config), "configured": configured}

    def save_ai_config(self, body):
        with self.lock:
            self._idle()
            self._check_capture(body)
            if not isinstance(body.get("config"), dict):
                raise ValueError("Thiếu cấu hình OCR.")
            source = copy.deepcopy(body["config"])
            source["reference_size"] = list(self.last_image.size)
            source["device_serial"] = self.device["serial"]
            config = validate_config(source)
            write_json(self.data_dir / "ai_config.json", config)
            self.ai_config = config
            return self.ai_state()

    def read_ai(self, body):
        with self.lock:
            self._idle()
            self._check_capture(body)
            image = self.last_image.copy()
        return self.ocr.probe(image)

    def run_ai(self):
        with self.lock:
            self._idle()
            if not self.ocr.info()["ready"]:
                raise ValueError("Bấm Kiểm tra OCR trên ảnh hiện tại trước khi chạy tự động.")
            config = validate_config(self.ai_config)
            if not self.device["serial"] or config.get("device_serial") != self.device["serial"]:
                raise ValueError("Chọn lại hai ô vật phẩm và lưu OCR cho đúng thiết bị hiện tại.")
            self.ai_runner.start(config)
            self.last_mode = "ai"
            return self.ai_runner.status()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, controller):
        super().__init__(address, Handler)
        self.controller = controller
        self.token = secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, fmt, *args):
        # Do not log request bodies, device settings, or session tokens.
        pass

    def send_bytes(self, status, data, content_type="application/json; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def json_reply(self, value, status=200, headers=None):
        data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_bytes(status, data, headers=headers)

    def check_host(self):
        port = self.server.server_port
        if self.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            raise PermissionError("Chỉ chấp nhận giao diện trên máy tính này.")

    def read_body(self):
        if not secrets.compare_digest(self.headers.get("X-ThanLong-Token", ""), self.server.token):
            raise PermissionError("Phiên điều khiển không hợp lệ. Hãy tải lại trang.")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}"}:
            raise PermissionError("Nguồn yêu cầu không hợp lệ.")
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("Yêu cầu phải là application/json.")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_BODY:
            raise ValueError("Yêu cầu rỗng hoặc vượt giới hạn 16 MiB.")
        def reject_constant(value):
            raise ValueError(f"Số JSON không hữu hạn: {value}")
        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("Số JSON phải hữu hạn.")
            return number
        body = json.loads(self.rfile.read(length), parse_constant=reject_constant, parse_float=finite_float)
        if not isinstance(body, dict):
            raise ValueError("Nội dung JSON cần là một đối tượng.")
        return body

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def dispatch(self, method):
        try:
            self.check_host()
            path = urlsplit(self.path).path
            ctl = self.server.controller
            if method == "GET":
                if path == "/api/state":
                    return self.json_reply(ctl.state())
                if path == "/api/presets":
                    return self.json_reply(list_presets())
                if path == "/api/screenshot":
                    with ctl.lock:
                        image = ctl.capture()
                        capture_id = ctl.last_capture_id
                        buffer = io.BytesIO()
                        image.save(buffer, "PNG")
                    return self.send_bytes(200, buffer.getvalue(), "image/png", headers={"X-ThanLong-Capture": capture_id})
                if path.startswith("/api/templates/"):
                    name = path.removeprefix("/api/templates/")
                    if not TEMPLATE_NAME.fullmatch(name):
                        raise ValueError("Tên ảnh mẫu không hợp lệ.")
                    return self.send_bytes(200, template_path(ctl.template_dir, name).read_bytes(), "image/png")
                if path.startswith("/api/export/"):
                    profile_id = path.removeprefix("/api/export/")
                    return self.json_reply(ctl.export_profile(profile_id), headers={
                        "Content-Disposition": f'attachment; filename="{profile_id}.json"'})
                files = {"/": ("index.html", "text/html; charset=utf-8"),
                         "/index.html": ("index.html", "text/html; charset=utf-8"),
                         "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                         "/style.css": ("style.css", "text/css; charset=utf-8"),
                         "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
                         "/static/style.css": ("style.css", "text/css; charset=utf-8")}
                if path in files:
                    name, mime = files[path]
                    data = (ROOT / "static" / name).read_bytes()
                    if name == "index.html":
                        data = data.replace(b"__SESSION_TOKEN__", self.server.token.encode("ascii"))
                    return self.send_bytes(200, data, mime)
            else:
                body = self.read_body()
                if path == "/api/device":
                    return self.json_reply(ctl.set_device(body))
                if path == "/api/ai/config":
                    return self.json_reply(ctl.save_ai_config(body))
                if path == "/api/ai/read":
                    return self.json_reply(ctl.read_ai(body))
                if path == "/api/ai/run":
                    return self.json_reply(ctl.run_ai())
                if path == "/api/screenshot":
                    with ctl.lock:
                        image = ctl.capture()
                        capture_id = ctl.last_capture_id
                    return self.json_reply({"width": image.width, "height": image.height, "capture_id": capture_id})
                if path == "/api/tap":
                    return self.json_reply(ctl.manual_input(body))
                if path == "/api/swipe":
                    return self.json_reply(ctl.manual_input(body, swipe=True))
                if path == "/api/template":
                    return self.json_reply(ctl.save_template(body))
                if path == "/api/import":
                    return self.json_reply(ctl.import_profile(body))
                if path.startswith("/api/presets/"):
                    return self.json_reply(ctl.load_preset(path.removeprefix("/api/presets/")))
                if path.startswith("/api/profiles/"):
                    return self.json_reply(ctl.save_profile(path.removeprefix("/api/profiles/"), body))
                if path == "/api/run":
                    return self.json_reply(ctl.run(body))
                if path == "/api/stop":
                    return self.json_reply(ctl.stop())
                if path == "/api/confirm":
                    return self.json_reply(ctl.confirm(body))
            return self.json_reply({"error": "Không tìm thấy đường dẫn."}, status=404)
        except PermissionError as exc:
            self.json_reply({"error": str(exc)}, status=403)
        except (ValueError, KeyError, TypeError) as exc:
            self.json_reply({"error": str(exc)}, status=400)
        except (ADBError, RuntimeError) as exc:
            self.json_reply({"error": str(exc)}, status=409)
        except FileNotFoundError:
            self.json_reply({"error": "Không tìm thấy tệp được yêu cầu."}, status=404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            print(f"Lỗi máy chủ: {type(exc).__name__}: {exc}")
            self.json_reply({"error": "Không xử lý được yêu cầu. Xem cửa sổ lệnh để biết chi tiết."}, status=500)


def main():
    parser = argparse.ArgumentParser(description="Thần Long Auto — bảng điều khiển LDPlayer cục bộ")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--adb", help="Đường dẫn adb.exe của LDPlayer")
    parser.add_argument("--open", action="store_true", help="Mở trình duyệt trên máy này")
    args = parser.parse_args()
    controller = Controller(args.data_dir, args.adb)
    server = LocalServer(("127.0.0.1", args.port), controller)
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"Thần Long Auto: {address}")
    print("Chỉ điều khiển LDPlayer trên máy này. Ctrl+C để dừng máy chủ và auto.")
    if args.open:
        webbrowser.open(address)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        server.server_close()


if __name__ == "__main__":
    main()
