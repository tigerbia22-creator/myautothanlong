"""Observed task sequences; screenshots must be calibrated on the user's device."""
from __future__ import annotations

import copy

PRESET_ID = "trung_ac_video_1016"
REQUIRED_TEMPLATES = [
    {"key": "ngo_gioi", "label": "Tiêu đề Ngô Giới", "hint": "Chỉ chọn chữ Ngô Giới ở đầu hộp thoại, tránh tên người chơi và cảnh nền."},
    {"key": "nhan_nhiem_vu", "label": "Nhận nhiệm vụ", "hint": "Chọn chữ Nhận nhiệm vụ trong hộp thoại Ngô Giới."},
    {"key": "ta_biet_roi", "label": "Ta biết rồi", "hint": "Chọn chữ Ta biết rồi ở hộp xác nhận; dùng lại cho phần nhận và trả nhiệm vụ."},
    {"key": "trung_ac_lenh_slot", "label": "Ô vật phẩm Trừng Ác Lệnh", "hint": "Chọn biểu tượng Trừng Ác Lệnh bạn đã gán vào ô nhanh. Clip dùng ô 1; cần kiểm tra ô trên máy bạn."},
    {"key": "trung_ac_lenh", "label": "Tiêu đề Trừng Ác Lệnh", "hint": "Chỉ chọn chữ ở tiêu đề hộp truy nã."},
    {"key": "den_dia_diem", "label": "Đến địa điểm", "hint": "Chọn chữ Đến địa điểm trong Trừng Ác Lệnh."},
    {"key": "trieu_hoi", "label": "Triệu hồi", "hint": "Chọn chữ Triệu hồi khi đã tới đúng tọa độ truy nã; khác nút Đến địa điểm dù cùng vị trí."},
    {"key": "dinh_vi_phu_slot", "label": "Ô vật phẩm Bạch sắc định vị phù", "hint": "Chọn biểu tượng phù đã lưu gần Ngô Giới. Không mặc định ô 2 giống clip."},
    {"key": "dinh_vi_phu", "label": "Tiêu đề Bạch sắc định vị phù", "hint": "Chọn tiêu đề đúng vật phẩm; cần tự kiểm tra địa điểm đã lưu trước khi Di chuyển."},
    {"key": "di_chuyen", "label": "Di chuyển", "hint": "Chọn chữ Di chuyển trong hộp Bạch sắc định vị phù."},
    {"key": "tra_nhiem_vu", "label": "Trả nhiệm vụ", "hint": "Chọn đúng chữ Trả nhiệm vụ trong hộp Ngô Giới; không chọn cả khung vàng giống các nút khác."},
]


def list_presets():
    return [{"id": PRESET_ID, "name": "Trừng ác theo clip — có xác nhận",
             "profile_id": "trung_ac", "checkpoints": 4,
             "description": "Trình tự quan sát từ clip 203 giây. Cần gán ảnh mẫu trên LDPlayer; chạy một vòng với 4 điểm xác nhận.",
             "required_templates": copy.deepcopy(REQUIRED_TEMPLATES)}]


def build_preset(preset_id, current_profile=None):
    if preset_id != PRESET_ID:
        raise ValueError("Không tìm thấy kịch bản theo clip.")
    labels = {item["key"]: item for item in REQUIRED_TEMPLATES}
    steps = []

    def visual(action, key, name=None, timeout=30, delay=0.4):
        item = labels[key]
        steps.append({"id": f"video-{len(steps) + 1}", "action": action,
                      "name": name or item["label"], "template": "", "threshold": 0.9,
                      "timeout": timeout, "delay_after": delay,
                      "calibration_key": key, "calibration_hint": item["hint"]})

    def confirm(name, prompt, timeout=900):
        steps.append({"id": f"video-{len(steps) + 1}", "action": "confirm", "name": name,
                      "prompt": prompt, "timeout": timeout, "delay_after": 0})

    visual("wait_image", "ngo_gioi", "Kiểm tra đã mở đúng NPC Ngô Giới")
    visual("tap_image", "nhan_nhiem_vu")
    visual("tap_image", "ta_biet_roi", "Xác nhận đã nhận nhiệm vụ")
    visual("tap_image", "trung_ac_lenh_slot", "Mở Trừng Ác Lệnh từ ô nhanh")
    visual("wait_image", "trung_ac_lenh", "Kiểm tra hộp Trừng Ác Lệnh")
    visual("tap_image", "den_dia_diem")
    confirm("Chờ tới đúng địa điểm truy nã",
            "Chờ nhân vật tự di chuyển. Khi đã tới đúng địa điểm truy nã, tự mở Trừng Ác Lệnh và kiểm tra nút Triệu hồi. "
            "Chỉ xác nhận khi đúng vị trí; phần mềm sẽ kiểm tra hộp và bấm Triệu hồi. Không xác nhận khi còn đang di chuyển.")
    visual("wait_image", "trung_ac_lenh", "Kiểm tra lại Trừng Ác Lệnh tại đích")
    visual("tap_image", "trieu_hoi")
    confirm("Kiểm tra đã giết đúng mục tiêu và tắt auto đánh",
            "Theo dõi chiến đấu trong game. Chỉ xác nhận sau khi thấy thông báo đã giết đúng tên kẻ truy nã và đã tắt auto đánh quái. "
            "Mất mục tiêu hoặc giết quái thường chưa chứng minh nhiệm vụ đã xong. Tiếp theo phần mềm sẽ mở Bạch sắc định vị phù.")
    visual("tap_image", "dinh_vi_phu_slot", "Mở Bạch sắc định vị phù đã chuẩn bị")
    visual("wait_image", "dinh_vi_phu", "Kiểm tra đúng hộp Bạch sắc định vị phù")
    confirm("Kiểm tra điểm dịch chuyển đã lưu",
            "Kiểm tra phù đang mở đã lưu vị trí gần Ngô Giới ở Tô Châu và có thể dùng. "
            "Xác nhận sẽ cho phần mềm bấm Di chuyển và sử dụng vật phẩm này. Nếu sai điểm hoặc thiếu vật phẩm, bấm Dừng.")
    visual("tap_image", "di_chuyen")
    confirm("Chờ về Ngô Giới và mở hộp thoại",
            "Chờ dùng phù và chuyển bản đồ xong. Tới gần Ngô Giới, tự mở hội thoại NPC. "
            "Chỉ xác nhận khi thấy đúng Ngô Giới và có thể Trả nhiệm vụ.")
    visual("wait_image", "ngo_gioi", "Kiểm tra NPC trước khi trả nhiệm vụ")
    visual("tap_image", "tra_nhiem_vu")
    visual("tap_image", "ta_biet_roi", "Xác nhận sau khi trả nhiệm vụ")
    reference = copy.deepcopy((current_profile or {}).get("reference_size"))
    return {"id": "trung_ac", "name": "Trừng ác — theo clip, có xác nhận",
            "preset_id": PRESET_ID, "single_cycle": True, "repeat": 1,
            "reference_size": reference,
            "description": "Bắt đầu khi đã mở hội thoại Ngô Giới. Gán 11 ảnh mẫu từ chính LDPlayer, ưu tiên chữ nút thay vì cả khung vàng. "
                           "Kịch bản chạy một vòng, có 4 lần chờ xác nhận; chưa tự đọc mục tiêu truy nã hoặc tự biết đã giết đúng tên. "
                           "Cần chuẩn bị Trừng Ác Lệnh và Bạch sắc định vị phù lưu gần Ngô Giới. Clip chưa thể hiện Tàng bảo đồ.",
            "source": {"kind": "video_observation", "duration_seconds": 203.32,
                       "video_size": [854, 480], "game_viewport": [0, 0, 854, 450],
                       "live_game_verified": False},
            "steps": steps}
