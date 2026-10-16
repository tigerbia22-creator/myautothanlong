"""Local read-only connection checks; no game profiles or credentials collected."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def check_http(port):
    url = f"http://127.0.0.1:{port}/api/state"
    # Loopback traffic must stay on this machine even with a configured HTTP proxy.
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with client.open(url, timeout=5) as response:
            state = json.loads(response.read(1024 * 1024))
        if not isinstance(state, dict) or not isinstance(state.get("runner"), dict):
            raise ValueError("Phan hoi khong dung dinh dang Thần Long Auto")
        return [f"May chu Python: DANG CHAY (cong {port})",
                f"Thiet bi da chon: {state.get('device', {}).get('serial') or '(chua chon)'}",
                f"Trang thai ket noi ADB gan nhat: {bool(state.get('connected'))}",
                f"Auto dang chay: {bool(state['runner'].get('running'))}"]
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return [f"May chu Python: KHONG LIEN LAC DUOC (cong {port})",
                f"Chi tiet: {exc}",
                "Mo CHAY_TREN_WINDOWS.bat va GIU cua so lenh mo, sau do Ctrl+F5 tren trinh duyet."]


def find_adb():
    stored = ROOT / ".local" / "device.json"
    if stored.is_file():
        try:
            path = json.loads(stored.read_text(encoding="utf-8")).get("adb_path")
            if isinstance(path, str) and path:
                return path
        except (OSError, ValueError, AttributeError):
            pass
    explicit = os.environ.get("ADB_PATH")
    if explicit:
        return explicit
    found = shutil.which("adb")
    if found:
        return found
    for path in [r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\XuanZhi\LDPlayer\adb.exe"]:
        if Path(path).is_file():
            return path
    return "adb"


def check_adb(path):
    lines = [f"Chuong trinh ADB: {path}"]
    try:
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        result = subprocess.run([path, "devices", "-l"], capture_output=True, timeout=15, check=False, **options)
        lines.append(f"adb devices -l: exit {result.returncode}")
        lines.append(result.stdout.decode("utf-8", errors="replace").strip() or "(khong co stdout)")
        if result.stderr:
            lines.append(result.stderr.decode("utf-8", errors="replace").strip())
        lines.append("Neu chua co device: bat ADB local trong LDPlayer, khoi dong lai gia lap va bam Lam moi thiet bi.")
    except FileNotFoundError:
        lines.append("Khong tim thay adb.exe. Nhap dung duong dan adb.exe di kem LDPlayer.")
    except (OSError, subprocess.TimeoutExpired) as exc:
        lines.append(f"Khong chay duoc ADB: {exc}")
    return lines


def main():
    parser = argparse.ArgumentParser(description="Kiem tra may chu Python va ADB tren may nay")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--adb")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port phai trong khoang 1..65535")
    lines = ["THAN LONG AUTO - KIEM TRA KET NOI", f"Python: {sys.version.split()[0]}",
             "Chi kiem tra HTTP noi bo va danh sach ADB; khong chup man hinh hay doc du lieu game.", ""]
    lines += check_http(args.port)
    lines += [""] + check_adb(args.adb or find_adb())
    report = "\n".join(lines) + "\n"
    output = ROOT / "THONG_TIN_KET_NOI.txt"
    output.write_text(report, encoding="utf-8")
    print(report)
    print(f"Da luu: {output}")


if __name__ == "__main__":
    main()
