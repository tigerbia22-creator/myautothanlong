import copy
from pathlib import Path
import tempfile
import time
import unittest

from PIL import Image

from thanlong.auto_quest import (OCRQuestRunner, coordinates, find_label, has_existing_quest_notice,
                                normalize, parse_target, target_was_killed, validate_config)


def item(text, x=182, y=108, w=240, h=16, confidence=.95):
    return {"text": text, "box": [x, y, w, h], "confidence": confidence}


def config():
    return {"reference_size": [854, 480], "quest_slot": [769, 133], "return_slot": [802, 133],
            "npc_anchor": None, "auto_toggle": None, "allow_teleport": True, "repeat": 1,
            "dialog_timeout": 1, "combat_timeout": 1, "return_timeout": 1, "travel_timeout": 2, "poll_interval": .1}


class Game:
    """Independent UI simulation: input clicks change the visible game screen."""
    def __init__(self, kill_allowed=True):
        self.phase = "menu"
        self.arrived = False
        self.auto = False
        self.done = False
        self.kill_allowed = kill_allowed
        self.calls = []
        self.size = (854, 480)

    def screenshot(self):
        return Image.new("RGB", self.size)

    def tap(self, x, y):
        self.calls.append((x, y))
        if (x, y) == (769, 133):
            self.phase = "quest"
        elif (x, y) == (802, 133):
            self.phase = "teleport"
        elif 700 <= x <= 745 and 85 <= y <= 110:
            self.auto = not self.auto
        elif 520 <= x <= 620 and 270 <= y <= 310:
            self.phase = "menu"
        elif 170 <= x <= 425 and 249 <= y <= 280:
            self.phase = {"menu": "accepted", "accepted": "world", "completed": "world",
                          "teleport": "returned", "quest": "fight" if self.arrived else "moving"}.get(self.phase, self.phase)
            if self.phase == "moving":
                self.arrived = True
        elif 430 <= x <= 680 and 249 <= y <= 280 and self.phase == "menu" and self.done:
            self.phase = "completed"

    def read(self, image, region=None):
        rows = []
        if self.phase == "menu":
            rows += [item("Ngô Giới", 405, 63, 65), item("Nhận nhiệm vụ", 270, 254, 65)]
            if self.done:
                rows.append(item("Trả nhiệm vụ", 525, 254, 65))
        if self.phase == "accepted":
            rows += [item("Ngô Giới", 405, 63, 65),
                     item("Tíēn Vän Lāng. Hin có người nhìn thấy hắn xuất hiện xung quanh Nam Hái", 380, 108, 292),
                     item("(280,164). Hãy dùng", 182, 120, 81), item("Ta biết rồi", 279, 254, 60)]
        if self.phase == "quest":
            rows += [item("Trừng Ác Lệnh", 390, 63, 90), item("- Tiền Vân Lãng ở Nam Hải (280,164).", 295, 97, 180),
                     item("Triệu hồi" if self.arrived else "Đến địa điểm", 270, 254, 75),
                     item("Để sau", 525, 254, 65)]
        if self.phase == "fight":
            rows.append(item("Đánh quái" if self.auto else "AUTO", 705, 93, 36, 10))
            if self.auto:
                rows.append(item("Đã giết chết Tiền Vân Lãng" if self.kill_allowed else "Đã giết chết Thạch Lão Nhân", 374, 63, 120))
                if self.kill_allowed:
                    self.done = True
        if self.phase == "teleport":
            rows += [item("Bạch sắc định vị phù", 379, 65, 125), item("Di chuyển", 275, 254, 60)]
        if self.phase in {"returned", "world"}:
            rows.append(item("Ngô Giới", 535, 275, 65))
        if self.phase == "completed":
            rows += [item("Hoàn thành", 182, 109, 65), item("Ta biết rồi", 279, 254, 60)]
        if region:
            rx, ry, rw, rh = region
            rows = [row for row in rows if rx <= row["box"][0] + row["box"][2] / 2 <= rx + rw and ry <= row["box"][1] + row["box"][3] / 2 <= ry + rh]
        return rows


class ExistingQuestGame(Game):
    """The game refuses a new quest and exposes the previous target in the lệnh."""
    def __init__(self, *, notice_at_start=True, target_readable=True, require_grayscale=False):
        super().__init__()
        self.phase = "pending" if notice_at_start else "menu"
        self.target_readable = target_readable
        self.require_grayscale = require_grayscale
        self.grayscale_reads = 0
        self.notice_acknowledged = False
        self.quest_closed = False
        self.accept_attempts = 0
        self.notice_message = "Ngươi vẫn chưa hoàn thành nhiệm vụ lần trước, không thể nhận nhiệm vụ mới!"

    def tap(self, x, y):
        if self.phase == "pending" and 170 <= x <= 425 and 249 <= y <= 280:
            self.calls.append((x, y))
            self.notice_acknowledged = True
            self.phase = "world"
        elif self.phase == "menu" and not self.done and 170 <= x <= 425 and 249 <= y <= 280:
            self.calls.append((x, y))
            self.accept_attempts += 1
            self.phase = "pending"
        elif self.phase == "quest" and 430 <= x <= 680 and 249 <= y <= 280:
            self.calls.append((x, y))
            self.quest_closed = True
            self.phase = "world"
        else:
            super().tap(x, y)

    def read(self, image, region=None):
        if image.mode == "L":
            self.grayscale_reads += 1
        if self.phase == "pending":
            rows = [item("Ngô Giới", 405, 63, 65),
                    item(self.notice_message, 182, 108, 490),
                    item("Ta biết rồi", 279, 254, 60)]
        else:
            rows = super().read(image)
            if self.phase == "quest" and (not self.target_readable or self.require_grayscale and image.mode != "L"):
                for row in rows:
                    if row["text"].startswith("- Tiền"):
                        # Actual colored-frame OCR loses 'ở': the name/map boundary is ambiguous.
                        row["text"] = "- Tiền Vân Lãng Nam Hải (280,164)."
        if region:
            rx, ry, rw, rh = region
            rows = [row for row in rows if rx <= row["box"][0] + row["box"][2] / 2 <= rx + rw
                    and ry <= row["box"][1] + row["box"][3] / 2 <= ry + rh]
        return rows


class FastRunner(OCRQuestRunner):
    def _wait(self, seconds):
        # Simulated travel/transition time; stop semantics remain those of the real runner.
        return super()._wait(min(seconds, .002))


def finish(runner, timeout=4):
    until = time.monotonic() + timeout
    while runner.status()["running"] and time.monotonic() < until:
        time.sleep(.005)
    if runner.status()["running"]:
        runner.stop()
        raise AssertionError("OCR runner did not complete")
    return runner.status()


class OCRParsingTests(unittest.TestCase):
    def test_existing_quest_notice_requires_both_negative_markers(self):
        self.assertTrue(has_existing_quest_notice([
            item("Ngươi vẫn chưa hoàn thành nhiệm vụ lần trước,"),
            item("không thể nhận nhiệm vụ mới!", y=128),
        ]))
        for text in ["Hoàn thành nhiệm vụ lần trước, có thể nhận nhiệm vụ mới!",
                     "Ngươi vẫn chưa hoàn thành nhiệm vụ lần trước",
                     "Không thể nhận nhiệm vụ mới!", "Nhận nhiệm vụ", "Hoàn thành"]:
            self.assertFalse(has_existing_quest_notice([item(text)]), text)

    def test_existing_quest_line_keeps_explicit_name_map_boundary(self):
        target = parse_target([item("- Tiēn Vān Lāng ó Nam Hái (280,164).")])
        self.assertEqual(normalize(target["name"]), "tien van lang")
        self.assertEqual(normalize(target["map"]), "nam hai")
        with self.assertRaises(ValueError):
            parse_target([item("- Tiền Vân Lãng Nam Hải (280,164).")])

    def test_real_video_ocr_variants_parse_and_match_exact_defeat(self):
        rows = [item("Triēu đình phát cáo thị truy nã", 182, 109, 115),
                item("Tíēn Vän Lāng. Hin có người nhìn thấy hắn xuất hiện xung quanh Nam Hái", 380, 107, 292),
                item("(280,164). Hāy dùng", 182, 120, 81)]
        target = parse_target(rows)
        self.assertEqual(normalize(target["name"]), "tien van lang")
        self.assertEqual((target["map"], target["x"], target["y"]), ("nam hai", 280, 164))
        self.assertTrue(target_was_killed([item("Dā giet chet Tien Vän Lāng", confidence=.88)], target))

    def test_wrong_monster_exp_and_missing_name_do_not_complete(self):
        target = {"name": "Tiền Vân Lãng"}
        for text in ["Đã giết chết Thạch Lão Nhân", "Nhận được 6570 kinh nghiệm", "Đã giết chết Tiền Vân Long", "Tiền Vân Lãng"]:
            self.assertFalse(target_was_killed([item(text)], target), text)

    def test_accept_and_turn_in_are_distinct(self):
        rows = [item("Nhn nhim vy"), item("Trå nhięm sy", x=525)]
        self.assertEqual(find_label(rows, "Nhận nhiệm vụ", first="nhan")["text"], "Nhn nhim vy")
        self.assertEqual(find_label(rows, "Trả nhiệm vụ", first="tra")["text"], "Trå nhięm sy")
        self.assertIsNone(find_label([item("Ta biết rồi")], "Trả nhiệm vụ", first="tra"))

    def test_ambiguous_or_incomplete_target_rejected(self):
        for rows in [[item("Nhận nhiệm vụ")], [item("Truy nã Tiền Vân Lãng Nam Hải (280,164)")], [item("- Tiền Vân Lãng ở Nam Hải")]]:
            with self.assertRaises(ValueError):
                parse_target(rows)
        self.assertIsNone(coordinates("(280,164) (281,164)"))

    def test_config_requires_bound_slots_and_permission(self):
        for changes in [{"quest_slot": None}, {"return_slot": [900, 10]}, {"allow_teleport": False},
                        {"repeat": True}, {"repeat": 31}, {"combat_timeout": float("inf")}, {"combat_timeout": 10**1000}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_config({**config(), **changes})


class OCRRunnerTests(unittest.TestCase):
    def test_existing_quest_notice_at_start_resumes_without_accepting_another(self):
        game = ExistingQuestGame()
        runner = FastRunner(game, game)
        runner.start(config())
        state = finish(runner)
        self.assertIsNone(state["error"], state)
        self.assertTrue(game.notice_acknowledged)
        self.assertTrue(game.quest_closed)
        self.assertEqual(game.accept_attempts, 0)
        self.assertTrue(game.done)
        self.assertFalse(game.auto)

    def test_existing_quest_refusal_after_acceptance_resumes_same_target(self):
        game = ExistingQuestGame(notice_at_start=False)
        runner = FastRunner(game, game)
        runner.start(config())
        state = finish(runner)
        self.assertIsNone(state["error"], state)
        self.assertTrue(game.notice_acknowledged)
        self.assertEqual(game.accept_attempts, 1)
        self.assertEqual(normalize(state["target"]["name"]), "tien van lang")
        self.assertEqual(game.calls.count((802, 133)), 1)

    def test_existing_quest_reads_grayscale_fallback_before_using_target(self):
        game = ExistingQuestGame(require_grayscale=True)
        runner = FastRunner(game, game)
        runner.start(config())
        state = finish(runner)
        self.assertIsNone(state["error"], state)
        self.assertGreater(game.grayscale_reads, 0)
        self.assertTrue(game.done)

    def test_unreadable_existing_target_stops_without_moving_or_teleporting(self):
        game = ExistingQuestGame(target_readable=False)
        runner = FastRunner(game, game)
        runner.start(config())
        state = finish(runner)
        self.assertIsNotNone(state["error"])
        self.assertTrue(game.notice_acknowledged)
        self.assertFalse(game.arrived)
        self.assertNotIn((802, 133), game.calls)
        self.assertFalse(game.auto)

    def test_unrecognized_or_positive_notice_does_not_open_quest_or_teleport(self):
        for text in ["Không thể nhận nhiệm vụ mới!", "Hoàn thành nhiệm vụ lần trước, có thể nhận nhiệm vụ mới!"]:
            with self.subTest(text=text):
                game = ExistingQuestGame()
                game.notice_message = text
                runner = FastRunner(game, game)
                runner.start(config())
                state = finish(runner)
                self.assertIsNotNone(state["error"])
                self.assertNotIn((769, 133), game.calls)
                self.assertNotIn((802, 133), game.calls)
                self.assertFalse(game.done)

    def test_acceptance_narrative_already_open_resumes_without_accepting_again(self):
        game = Game()
        game.phase = "accepted"
        runner = FastRunner(game, game)
        runner.start(config())
        state = finish(runner)
        self.assertIsNone(state["error"], state)
        self.assertTrue(game.done)
        self.assertEqual(game.calls.count((802, 133)), 1)

    def test_repeat_reopens_npc_and_completes_a_second_cycle(self):
        game = Game()
        runner = FastRunner(game, game)
        runner.start({**config(), "repeat": 2})
        state = finish(runner)
        self.assertIsNone(state["error"], state)
        self.assertEqual(state["iteration"], 2)
        self.assertEqual(game.calls.count((802, 133)), 2)
        self.assertFalse(game.auto)

    def test_complete_cycle_has_no_confirmation_and_does_not_use_templates(self):
        game = Game()
        runner = FastRunner(game, game)
        runner.start(config())
        state = finish(runner)
        self.assertIsNone(state["error"], state)
        self.assertEqual(state["step_index"], 6)
        self.assertFalse(state["awaiting_confirmation"])
        self.assertIn((769, 133), game.calls)
        self.assertIn((802, 133), game.calls)
        self.assertFalse(game.auto)
        self.assertTrue(game.done)

    def test_other_kill_times_out_before_teleport(self):
        game = Game(kill_allowed=False)
        runner = FastRunner(game, game)
        runner.start(config())
        state = finish(runner)
        self.assertIn("hạ đúng tên", state["error"])
        self.assertNotIn((802, 133), game.calls)

    def test_resolution_mismatch_prevents_first_input(self):
        game = Game(); game.size = (855, 480)
        runner = FastRunner(game, game); runner.start(config())
        self.assertIn("Độ phân giải", finish(runner)["error"])
        self.assertEqual(game.calls, [])

    def test_stop_during_combat_prevents_any_later_input(self):
        game = Game(kill_allowed=False)
        runner = FastRunner(game, game); runner.start(config())
        deadline = time.monotonic() + 2
        while runner.status()["step_index"] != 3 and time.monotonic() < deadline:
            time.sleep(.002)
        runner.stop(); count = len(game.calls)
        self.assertFalse(finish(runner)["running"])
        self.assertEqual(len(game.calls), count)
        self.assertNotIn((802, 133), game.calls)


if __name__ == "__main__":
    unittest.main()
