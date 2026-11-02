"""New versions: GitHub's answers and the downloads are the tests' own."""

import hashlib
import http.server
import json
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest

from nanar import updates
from nanar.online import OnlineError, Request
from nanar.system import powershell
from nanar.updates import Release, UpdateError, Updates, release_of, version_of

ZIP = "https://github.com/j3ffx/nanar/releases/download/v0.5.0/nanar-0.5.0-windows.zip"


def github(version: str) -> dict[str, Any]:
    zip_name = f"nanar-{version}-windows.zip"
    return {
        "tag_name": f"v{version}",
        "assets": [
            {
                "name": zip_name,
                "browser_download_url": f"https://github.com/j3ffx/nanar/releases/download/v0.5.0/{zip_name}",
            },
            {
                "name": zip_name + ".sha256",
                "browser_download_url": f"https://github.com/j3ffx/nanar/releases/download/v0.5.0/{zip_name}.sha256",
            },
        ],
    }


def make(answer: object, *, files: dict[str, bytes] | None = None) -> tuple[Updates, list[float]]:
    checked: list[float] = []

    def get(request: Request) -> bytes:
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer).encode()

    def download(url: str, target: Path) -> None:
        target.write_bytes((files or {})[url])

    found = Updates(
        enabled=lambda: True,
        checked_at=lambda: 0.0,
        mark_checked=checked.append,
        on_change=lambda: None,
        get=get,
        download=download,
        supported=True,
    )
    return found, checked


def test_reads_versions_and_releases() -> None:
    assert version_of("v0.10.2") == (0, 10, 2)
    assert version_of("0.5.0-rc1") is None
    release = release_of(github("0.5.0"))
    assert release == Release(
        "0.5.0",
        "https://github.com/j3ffx/nanar/releases/download/v0.5.0/nanar-0.5.0-windows.zip",
        "https://github.com/j3ffx/nanar/releases/download/v0.5.0/nanar-0.5.0-windows.zip.sha256",
    )
    assert release_of({**github("0.5.0"), "prerelease": True}) is None
    assert release_of({"tag_name": "v0.5.0", "assets": []}) is None


def test_offers_only_a_newer_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updates, "__version__", "0.4.0")
    newer, checked = make(github("0.5.0"))
    assert newer.check() is not None
    assert newer.state()["available"] == "0.5.0"
    assert checked  # once a day: the time is kept
    same, _ = make(github("0.4.0"))
    assert same.check() is None
    offline, _ = make(OnlineError("offline"))
    with pytest.raises(UpdateError, match="offline"):
        offline.check()


def zipped(files: dict[str, bytes]) -> bytes:
    import io

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out.getvalue()


def test_prepares_the_new_folder_next_to_the_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updates, "__version__", "0.4.0")
    archive = zipped({"Nanar/Nanar.exe": b"exe", "Nanar/_internal/x.dll": b"dll"})
    digest = hashlib.sha256(archive).hexdigest()
    found, _ = make(
        github("0.5.0"),
        files={
            ZIP: archive,
            ZIP + ".sha256": f"{digest}  x.zip\n".encode(),
        },
    )
    found.check()
    install = tmp_path / "Programs" / "Nanar"
    install.mkdir(parents=True)
    command = found.prepare(install, 8642)
    work = tmp_path / "Programs" / "Nanar.update"
    assert (work / "new" / "Nanar" / "Nanar.exe").read_bytes() == b"exe"
    assert (work / "swap.ps1").is_file()
    assert command[command.index("-Target") + 1] == str(install)
    assert found.state()["installing"]
    found.cancelled()
    assert not found.state()["installing"]


def test_refuses_a_download_that_does_not_match_its_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updates, "__version__", "0.4.0")
    found, _ = make(
        github("0.5.0"),
        files={
            ZIP: zipped({"Nanar/Nanar.exe": b"exe"}),
            ZIP + ".sha256": b"0" * 64 + b"  x.zip\n",
        },
    )
    found.check()
    install = tmp_path / "Nanar"
    install.mkdir()
    with pytest.raises(UpdateError, match="bad_checksum"):
        found.prepare(install, 8642)
    assert not found.state()["installing"]


def test_refuses_downloads_from_anywhere_else() -> None:
    data: dict[str, Any] = github("0.5.0")
    data["assets"][0]["browser_download_url"] = "https://evil.test/x.zip"
    assert release_of(data) is None


def fake_install(root: Path) -> tuple[Path, Path, Path]:
    """Two folders of made-up Nanars, and the real swap script."""
    programs = root / "Le film d'hier [HD]"
    target, new = programs / "Nanar", programs / "Nanar.update" / "new" / "Nanar"
    target.mkdir(parents=True)
    new.mkdir(parents=True)
    (target / "which.txt").write_text("old")
    (new / "which.txt").write_text("new")
    for folder in (target, new):  # any program that starts and stops at once
        shutil.copy(Path(powershell()).parents[2] / "hostname.exe", folder / "Nanar.exe")
    script = programs / "Nanar.update" / "swap.ps1"
    script.write_text(updates.SWAP, encoding="utf-8")
    return target, new, script


def run_swap(target: Path, new: Path, script: Path, port: int, within: int) -> None:
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    command = updates.swap_command(script, gone.pid, new, target, "0.5.0", port, within)
    subprocess.run(command, check=False, timeout=90, cwd=target.parent)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows build only")
def test_the_swap_puts_the_new_version_in_place_once_it_answers(tmp_path: Path) -> None:
    target, new, script = fake_install(tmp_path)

    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps({"version": "0.5.0"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        run_swap(target, new, script, server.server_address[1], 10)
    finally:
        server.shutdown()
    assert (target / "which.txt").read_text() == "new"
    assert not target.with_name("Nanar.old").exists()
    assert not target.with_name("Nanar.update").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows build only")
def test_the_swap_brings_the_old_version_back_when_the_new_one_does_not_answer(
    tmp_path: Path,
) -> None:
    target, new, script = fake_install(tmp_path)
    run_swap(target, new, script, 9, 2)  # nothing answers on that port
    assert (target / "which.txt").read_text() == "old"
    assert (target / "Nanar.exe").is_file()
    assert not target.with_name("Nanar.old").exists()
