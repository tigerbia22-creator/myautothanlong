"""Create a Windows source release, excluding local device data and dependencies."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
NAME = "ThanLongAuto-LDPlayer-0.2.0"


def main():
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / f"{NAME}.zip"
    files = [ROOT / name for name in ("README.md", "requirements.txt", "CHAY_TREN_WINDOWS.bat", "KIEM_TRA_KET_NOI.bat")]
    for folder in ("thanlong", "tests", "scripts", "docs"):
        files.extend(path for path in (ROOT / folder).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    with ZipFile(archive, "w", ZIP_DEFLATED) as release:
        for path in sorted(files):
            content = path.read_bytes()
            if path.suffix == ".bat":
                content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            relative = path.relative_to(ROOT).as_posix()
            release.writestr(f"{NAME}/{relative}", content)
    checksum = sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    with ZipFile(archive) as release:
        assert release.testzip() is None
        assert all(".local/" not in name and ".venv/" not in name for name in release.namelist())
    print(f"{archive} ({archive.stat().st_size:,} bytes)")
    print(f"SHA256 {checksum}")


if __name__ == "__main__":
    main()
