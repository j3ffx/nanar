"""Takes the README's screenshots from the demo, with Edge headless (it ships with Windows).

    uv run python scripts/screenshots.py

The demo runs on a throwaway data directory and shows a documentation address (192.0.2.10), so
no real address, key or film ever lands in the images.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BASE = "http://127.0.0.1:8642"
EDGE = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / (
    r"Microsoft\Edge\Application\msedge.exe"
)


def post(path: str, body: dict[str, object]) -> None:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=10).close()


def get(path: str) -> dict[str, object]:
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        data: dict[str, object] = json.load(response)
        return data


def shot(url: str, name: str, size: str) -> None:
    subprocess.run(
        [
            str(EDGE),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={size}",
            "--virtual-time-budget=10000",
            f"--screenshot={DOCS / name}",
            url,
        ],
        check=True,
        capture_output=True,
    )
    print(name)


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="nanar-screenshots-", ignore_cleanup_errors=True
    ) as data:
        env = os.environ | {"NANAR_DATA_DIR": data, "NANAR_SHOW_ADDRESS": "192.0.2.10"}
        nanar = subprocess.Popen(
            [sys.executable, "-m", "nanar", "--demo", "--headless"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(6)
            shot(f"{BASE}/tv", "capture-tele.png", "1600,900")
            shot(f"{BASE}/bibliotheque", "capture-bibliotheque.png", "500,1000")
            library = get("/api/library")
            groups = library["groups"]
            assert isinstance(groups, dict)
            series = next(g for g in groups.values() if g["kind"] == "series")
            post("/api/play", {"videoId": series["videos"][1], "start": 0})
            time.sleep(8)
            shot(f"{BASE}/", "capture-telecommande.png", "500,1000")
            post("/api/command", {"action": "stop"})
        finally:
            nanar.terminate()
            nanar.wait(10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
