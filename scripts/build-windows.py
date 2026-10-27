"""Builds the Windows release: dist/nanar-<version>-windows.zip and its .sha256.

    uv run python scripts/build-windows.py

Needs the pages built (npm run build) and libmpv fetched (scripts/get-libmpv.py). The zip holds
one folder, Nanar, with Nanar.exe inside: unzip it anywhere, and run Nanar.exe.
"""

import hashlib
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def main() -> int:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    if not (ROOT / "src" / "nanar" / "web" / "static" / "index.html").is_file():
        print("x the pages are not built: run npm run build first", file=sys.stderr)
        return 1
    if not (ROOT / "vendor" / "libmpv-2.dll").is_file():
        print("x libmpv is missing: run scripts/get-libmpv.py first", file=sys.stderr)
        return 1
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(ROOT / "build" / "pyinstaller"),
            str(ROOT / "packaging" / "nanar.spec"),
        ],
        check=True,
    )
    folder = DIST / "Nanar"
    archive = DIST / f"nanar-{version}-windows.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zipped.write(path, Path("Nanar") / path.relative_to(folder))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.parent / (archive.name + ".sha256")).write_text(
        f"{digest}  {archive.name}\n", encoding="ascii"
    )
    size = archive.stat().st_size / 1_000_000
    print(f"{archive.name}: {size:.0f} MB, sha256 {digest}")
    shutil.rmtree(ROOT / "build" / "pyinstaller", ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
