"""Bounded OCR state machine for the observed Trừng Ác route."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from difflib import SequenceMatcher
import math
import re
import threading
import time
import unicodedata


def normalize(text):
    text = str(text).replace("đ", "d").replace("Đ", "D")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def joined(items):
    rows = []
    for item in sorted(items, key=lambda i: i["box"][1]):
        if item.get("confidence", 0) < .55:
            continue
        center = item["box"][1] + item["box"][3] / 2
        row = next((row for row in rows if abs(row["center"] - center) <= .45 * max(row["height"], item["box"][3])), None)
        if row is None:
            row = {"center": center, "height": item["box"][3], "items": []}
            rows.append(row)
        row["items"].append(item)
    return " ".join(item["text"] for row in sorted(rows, key=lambda r: r["center"]) for item in sorted(row["items"], key=lambda i: i["box"][0]))


def coordinates(text):
    matches = re.findall(r"[\[(]\s*(\d{1,4})\s*[,;:]\s*(\d{1,4})\s*[\])]", text)
    pairs = {(int(x), int(y)) for x, y in matches}
    return next(iter(pairs)) if len(pairs) == 1 else None


def parse_target(items):
    """Parse the acceptance narrative; never guess a name/map boundary."""
    raw = joined(items)
    xy = coordinates(raw)
    text = normalize(raw)
    # The acceptance popup has a sentence boundary between name and narrative.
    name = None
    for part in [item["text"] for item in items if item.get("confidence", 0) >= .65] + [raw]:
        if "." not in part:
            continue
        prefix, suffix = part.split(".", 1)
        if not normalize(suffix).startswith(("hi", "hen")):
            continue
        prefix = re.split(r"[-–]", prefix)[-1].strip()
        words = normalize(prefix).split()
        if 2 <= len(words) <= 5 and not set(words) & {"truy", "nhiem", "hien", "dinh", "trieu"}:
            name = prefix
            break
    map_match = re.search(r"\bxung quanh\s+([a-z ]{2,35}?)\s+\d{1,4}\s+\d{1,4}(?:\s|$)", text)
    if map_match is None:
        map_match = re.search(r"\b(?:tai|o)\s+([a-z ]{2,35}?)\s+\d{1,4}\s+\d{1,4}(?:\s|$)", text)
    if not name or not map_match or xy is None:
        # Supports unambiguous quest lines when the OCR retained 'ở'.
        line = re.search(r"[-–]\s*(.+?)\s+[ởóòôo]\s+(.+?)\s*[\[(]\s*\d+", raw, re.IGNORECASE)
        if not line or xy is None:
            raise ValueError("Chưa đọc chắc tên mục tiêu, bản đồ và tọa độ. Hãy tăng độ rõ chữ rồi thử Kiểm tra OCR.")
        name, map_name = line.group(1).strip(), line.group(2).strip()
    else:
        map_name = map_match.group(1)
    if "-" in name or "–" in name:
        name = re.split(r"[-–]", name)[-1].strip()
    if len(normalize(name).split()) < 2 or len(normalize(map_name)) < 3:
        raise ValueError("Tên mục tiêu hoặc bản đồ OCR chưa đủ rõ.")
    return {"name": name, "map": map_name, "x": xy[0], "y": xy[1]}


def target_was_killed(items, target):
    wanted = normalize(target["name"])
    for item in items:
        if item.get("confidence", 0) < .6:
            continue
        text = normalize(item["text"])
        match = re.search(r"\bda (?:giet|guet) chet (.+)$", text)
        if match:
            actual = match.group(1).strip()
            if actual == wanted:
                return True
    return False


def find_label(items, phrase, *, first=None, minimum=.78):
    query = normalize(phrase)
    candidates = []
    aliases = {"nhan": {"nhan", "nhn", "nhaninhiem"}, "tra": {"tra", "ta"}, "den": {"den"},
               "trieu": {"trieu"}, "ta": {"ta"}, "di": {"di", "dich"}}
    for item in items:
        if item.get("confidence", 0) < .55:
            continue
        value = normalize(item["text"])
        if not value:
            continue
        if first and value.split()[0] not in aliases.get(first, {first}):
            continue
        score = SequenceMatcher(None, value, query).ratio()
        if score >= minimum:
            candidates.append((score, item))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .04:
        raise ValueError(f"OCR thấy nhiều lựa chọn gần giống '{phrase}'; dừng để tránh bấm nhầm.")
    return candidates[0][1]


def validate_config(source):
    if not isinstance(source, dict):
        raise ValueError("Cấu hình OCR cần là một đối tượng.")
    cfg = copy.deepcopy(source)
    size = cfg.get("reference_size")
    if not isinstance(size, list) or len(size) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 16384 for v in size):
        raise ValueError("Chụp màn hình để đặt kích thước tham chiếu OCR.")
    for key in ("quest_slot", "return_slot", "npc_anchor", "auto_toggle"):
        value = cfg.get(key)
        if value is None and key in {"npc_anchor", "auto_toggle"}:
            continue
        if not isinstance(value, list) or len(value) != 2 or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < size[i] for i, v in enumerate(value)):
            raise ValueError(f"Chọn vị trí {key} trên ảnh màn hình.")
    if cfg["quest_slot"] == cfg["return_slot"]:
        raise ValueError("Ô Trừng Ác Lệnh và ô định vị phù phải khác nhau.")
    if cfg.get("allow_teleport") is not True:
        raise ValueError("Cần chuẩn bị và xác nhận phù đã lưu gần Ngô Giới trước khi chạy.")
    cfg.setdefault("repeat", 1)
    if isinstance(cfg["repeat"], bool) or not isinstance(cfg["repeat"], int) or not 1 <= cfg["repeat"] <= 30:
        raise ValueError("Số vòng OCR cần trong khoảng 1–30.")
    cfg.setdefault("return_map", "Tô Châu")
    if not isinstance(cfg["return_map"], str) or not 1 <= len(cfg["return_map"]) <= 60:
        raise ValueError("Tên bản đồ trở về không hợp lệ.")
    for key, default in (("travel_timeout", 900), ("combat_timeout", 180), ("dialog_timeout", 30), ("return_timeout", 90), ("poll_interval", .35), ("travel_poll_interval", 8)):
        value = cfg.setdefault(key, default)
        low, high = (.1, 3) if key == "poll_interval" else (2, 30) if key == "travel_poll_interval" else (1, 1800)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError(f"{key} cần là số hữu hạn trong khoảng {low}–{high}.")
    return cfg


class _Stopped(Exception):
    pass


class OCRQuestRunner:
    def __init__(self, adb, reader):
        self.adb, self.reader = adb, reader
        self._lock = threading.RLock()
        self._input_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._state = self._initial()

    @staticmethod
    def _initial():
        return {"running": False, "stopping": False, "profile_id": "trung_ac", "step_index": 0,
                "step_name": "", "iteration": 0, "repeat": 0, "dry_run": False, "error": None,
                "mode": "ai", "logs": [], "target": None, "awaiting_confirmation": False,
                "confirmation_prompt": "", "confirmation_id": None}

    def status(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def _update(self, **kwargs):
        with self._lock:
            self._state.update(kwargs)

    def _log(self, message, level="info"):
        with self._lock:
            self._state["logs"].append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": level, "message": message})
            del self._state["logs"][:-300]

    def start(self, config):
        config = validate_config(config)
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("OCR tự động đang chạy.")
            self._stop.clear()
            self._state = self._initial()
            self._state.update(running=True, repeat=config["repeat"])
            self._thread = threading.Thread(target=self._run, args=(config,), daemon=True, name="thanlong-ai")
            self._thread.start()

    def stop(self):
        self._stop.set()
        with self._lock:
            if self._state["running"]:
                self._state["stopping"] = True
        with self._input_lock:
            pass

    def _check(self):
        if self._stop.is_set():
            raise _Stopped()

    def _wait(self, seconds):
        if self._stop.wait(seconds):
            raise _Stopped()

    def _capture(self, cfg):
        self._check()
        image = self.adb.screenshot()
        self._check()
        if list(image.size) != cfg["reference_size"]:
            raise ValueError("Độ phân giải đã thay đổi. Dừng OCR và chọn lại vị trí trên ảnh mới.")
        return image

    def _items(self, cfg, rect):
        image = self._capture(cfg)
        w, h = image.size
        x, y, rw, rh = rect
        region = [round(x * w), round(y * h), max(1, round(rw * w)), max(1, round(rh * h))]
        region[2] = min(region[2], w - region[0]); region[3] = min(region[3], h - region[1])
        items = self.reader.read(image, region)
        self._check()
        return items

    def _tap(self, cfg, point):
        self._capture(cfg)
        with self._input_lock:
            self._check()
            self.adb.tap(*point)

    def _tap_label(self, cfg, item):
        x, y, w, h = item["box"]
        self._log(f"OCR bấm '{item['text']}' ({item['confidence']:.2f}).")
        self._tap(cfg, [x + w // 2, y + h // 2])
        self._wait(.4)

    def _stage(self, number, name):
        self._update(step_index=number, step_name=name)
        self._log(name)

    def _until(self, cfg, rect, predicate, timeout, message):
        deadline = time.monotonic() + timeout
        last_text = ""
        while True:
            items = self._items(cfg, rect)
            last_text = joined(items)
            found = predicate(items)
            if found:
                return found
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{message}. OCR gần nhất: {last_text[:240] or '(không đọc được chữ)'}. Auto đã dừng.")
            self._wait(cfg["poll_interval"])

    def _header(self, cfg, phrase, minimum=.7, timeout=None):
        return self._until(cfg, (.32, .10, .4, .09), lambda items: find_label(items, phrase, minimum=minimum),
                           timeout or cfg["dialog_timeout"], f"Không đọc được tiêu đề {phrase}")

    def _button(self, cfg, phrase, first, minimum=.75):
        rect = (.5, .49, .3, .15) if first == "tra" else (.2, .49, .6, .29)
        item = self._until(cfg, rect, lambda items: find_label(items, phrase, first=first, minimum=minimum),
                           cfg["dialog_timeout"], f"Không thấy nút {phrase}")
        self._tap_label(cfg, item)

    def _open_npc(self, cfg, returning=False):
        if returning:
            deadline = time.monotonic() + cfg["return_timeout"]
            while True:
                header = self._items(cfg, (.32, .10, .4, .09))
                if find_label(header, "Ngô Giới", minimum=.8):
                    return
                body = self._items(cfg, (.2, .25, .65, .5))
                npc = find_label(body, "Ngô Giới", minimum=.85)
                if npc:
                    self._tap_label(cfg, npc)
                    self._header(cfg, "Ngô Giới", .8)
                    return
                if cfg.get("npc_anchor"):
                    hud = self._items(cfg, (.88, .025, .12, .09))
                    if find_label(hud, cfg["return_map"], minimum=.85):
                        self._tap(cfg, cfg["npc_anchor"])
                        self._header(cfg, "Ngô Giới", .8)
                        return
                if time.monotonic() >= deadline:
                    raise TimeoutError("Chưa đọc được Ngô Giới sau khi dịch chuyển; không bấm Trả nhiệm vụ.")
                self._wait(cfg["poll_interval"])
        header = self._items(cfg, (.32, .10, .4, .09))
        if find_label(header, "Ngô Giới", minimum=.8):
            return
        if cfg.get("npc_anchor"):
            self._tap(cfg, cfg["npc_anchor"])
        else:
            npc = self._until(cfg, (.2, .25, .65, .5), lambda items: find_label(items, "Ngô Giới", minimum=.85),
                              cfg["return_timeout"] if returning else cfg["dialog_timeout"], "Không tìm được hội thoại Ngô Giới; có thể chọn điểm NPC một lần")
            self._tap_label(cfg, npc)
        self._header(cfg, "Ngô Giới", .8)

    def _auto_state(self, cfg):
        items = self._items(cfg, (.80, .13, .09, .12))
        for item in items:
            value = normalize(item["text"])
            if item.get("confidence", 0) < .6:
                continue
            if value == "auto":
                return False, item
            if "quai" in value.split():
                return True, item
        return None, None

    def _set_auto(self, cfg, enabled):
        active, item = self._auto_state(cfg)
        if active is None:
            raise ValueError("Chưa đọc chắc trạng thái AUTO/Đánh quái. Tăng độ rõ chữ trước khi chạy.")
        if active == enabled:
            return
        point = cfg.get("auto_toggle")
        if point:
            self._tap(cfg, point)
        else:
            self._tap_label(cfg, item)
        self._until(cfg, (.80, .13, .09, .12), lambda unused: self._auto_state(cfg)[0] is enabled,
                    cfg["dialog_timeout"], "Không xác nhận được trạng thái auto đánh quái")

    def _travel_and_summon(self, cfg, target):
        deadline = time.monotonic() + cfg["travel_timeout"]
        while True:
            self._tap(cfg, cfg["quest_slot"])
            self._header(cfg, "Trừng Ác Lệnh", .65)
            body = self._items(cfg, (.2, .19, .6, .13))
            xy = coordinates(joined(body))
            if xy != (target["x"], target["y"]):
                raise ValueError("Tọa độ trong Trừng Ác Lệnh không khớp mục tiêu đã nhận hoặc OCR chưa rõ.")
            items = self._items(cfg, (.2, .49, .6, .15))
            summon = find_label(items, "Triệu hồi", first="trieu", minimum=.8)
            if summon:
                self._tap_label(cfg, summon)
                return
            move = find_label(items, "Đến địa điểm", first="den", minimum=.8)
            if not move:
                raise ValueError("Không thấy Đến địa điểm hoặc Triệu hồi trong đúng Trừng Ác Lệnh.")
            self._tap_label(cfg, move)
            if time.monotonic() >= deadline:
                raise TimeoutError("Hết thời gian chờ tới nơi và hiện nút Triệu hồi.")
            self._wait(cfg["travel_poll_interval"])

    def _run(self, cfg):
        try:
            for iteration in range(1, cfg["repeat"] + 1):
                self._update(iteration=iteration, target=None)
                self._stage(0, "Mở Ngô Giới và nhận nhiệm vụ")
                self._open_npc(cfg)
                self._button(cfg, "Nhận nhiệm vụ", "nhan")
                self._stage(1, "Đọc tên mục tiêu, bản đồ và tọa độ")
                target = self._until(cfg, (.2, .19, .6, .17), self._parse_or_none,
                                     cfg["dialog_timeout"], "Không đọc chắc thông tin truy nã")
                self._update(target=target)
                self._log(f"Mục tiêu: {target['name']} · {target['map']} ({target['x']},{target['y']}).")
                self._button(cfg, "Ta biết rồi", "ta")
                self._stage(2, "Di chuyển; chờ đúng lệnh cho phép Triệu hồi")
                self._travel_and_summon(cfg, target)
                self._stage(3, "Theo dõi chiến đấu và thông báo hạ đúng mục tiêu")
                self._set_auto(cfg, True)
                self._until(cfg, (.35, .025, .35, .2), lambda items: target_was_killed(items, target),
                            cfg["combat_timeout"], "Chưa thấy thông báo hạ đúng tên mục tiêu")
                self._set_auto(cfg, False)
                self._stage(4, "Dùng định vị phù đã chuẩn bị để trở về")
                self._tap(cfg, cfg["return_slot"])
                self._header(cfg, "Bạch sắc định vị phù", .65)
                self._button(cfg, "Di chuyển", "di", .75)
                self._wait(2)
                self._stage(5, "Tìm Ngô Giới và trả nhiệm vụ")
                self._open_npc(cfg, returning=True)
                self._button(cfg, "Trả nhiệm vụ", "tra")
                self._until(cfg, (.2, .19, .6, .2), lambda items: find_label(items, "Hoàn thành", minimum=.8),
                            cfg["dialog_timeout"], "Chưa đọc được xác nhận Hoàn thành")
                self._button(cfg, "Ta biết rồi", "ta")
                self._log(f"Đã hoàn thành vòng {iteration}/{cfg['repeat']} theo các trạng thái OCR.")
            self._stage(6, "Đã hoàn tất số vòng cấu hình")
        except _Stopped:
            self._log("Đã dừng OCR theo yêu cầu.")
        except Exception as exc:
            self._update(error=str(exc))
            self._log(str(exc), "error")
        finally:
            self._update(running=False, stopping=False)

    @staticmethod
    def _parse_or_none(items):
        try:
            return parse_target(items)
        except ValueError:
            return None
