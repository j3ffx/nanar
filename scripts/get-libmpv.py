"""Fetches libmpv for Windows into vendor/ (development, and the Windows build at release time).

    uv run python scripts/get-libmpv.py

The build is shinchiro's (https://github.com/shinchiro/mpv-winbuild-cmake), pinned by name and
SHA-256: a different file is refused. To move to a newer build, change BUILD and SHA256 together
(`gh release view -R shinchiro/mpv-winbuild-cmake` lists the files and their digests). That
project keeps only recent builds online: when the pinned one disappears, move to a newer one.
On Linux and macOS, install libmpv from the system's packages instead (libmpv2, mpv).
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

RELEASE = "20261021"
BUILD = "mpv-dev-x86_64-20261021-git-e471496c56.7z"
SHA256 = "efc719eff3dc5954b4a5efc800632808bcec01cc9034940dd14e5eb7fe9ea633"
URL = f"https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/{RELEASE}/{BUILD}"
DLL = "libmpv-2.dll"

VENDOR = Path(__file__).resolve().parent.parent / "vendor"


def main() -> int:
    target = VENDOR / DLL
    stamp = VENDOR / "libmpv.version"
    if target.exists() and stamp.exists() and stamp.read_text().strip() == BUILD:
        print(f"{DLL} is up to date ({BUILD})")
        return 0
    VENDOR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / BUILD
        print(f"Downloading {URL}")
        with urllib.request.urlopen(URL, timeout=120) as response, archive.open("wb") as out:
            shutil.copyfileobj(response, out)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != SHA256:
            print(f"x {BUILD}: SHA-256 {digest}, expected {SHA256}", file=sys.stderr)
            return 1
        # Windows' own tar is bsdtar (libarchive), which reads 7z with its BCJ2 filter.
        tar = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "tar.exe"
        subprocess.run([str(tar), "-xf", str(archive), "-C", tmp, DLL], check=True)
        shutil.copyfile(Path(tmp) / DLL, target)
    stamp.write_text(BUILD + "\n")
    print(f"{DLL} -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
