"""New versions: GitHub's answers and the downloads are the tests' own."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from nanar import updates
from nanar.online import OnlineError, Request
from nanar.updates import Release, UpdateError, Updates, release_of, version_of


def github(version: str) -> dict[str, object]:
    zip_name = f"nanar-{version}-windows.zip"
    return {
        "tag_name": f"v{version}",
        "assets": [
            {"name": zip_name, "browser_download_url": f"https://dl.test/{zip_name}"},
            {
                "name": zip_name + ".sha256",
                "browser_download_url": f"https://dl.test/{zip_name}.sha256",
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
        "https://dl.test/nanar-0.5.0-windows.zip",
        "https://dl.test/nanar-0.5.0-windows.zip.sha256",
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
            "https://dl.test/nanar-0.5.0-windows.zip": archive,
            "https://dl.test/nanar-0.5.0-windows.zip.sha256": f"{digest}  x.zip\n".encode(),
        },
    )
    found.check()
    install = tmp_path / "Programs" / "Nanar"
    install.mkdir(parents=True)
    command = found.prepare(install)
    work = tmp_path / "Programs" / "Nanar.update"
    assert (work / "new" / "Nanar" / "Nanar.exe").read_bytes() == b"exe"
    assert (work / "swap.ps1").is_file()
    assert command[command.index("-Target") + 1] == str(install)
    assert found.state()["installing"]


def test_refuses_a_download_that_does_not_match_its_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updates, "__version__", "0.4.0")
    found, _ = make(
        github("0.5.0"),
        files={
            "https://dl.test/nanar-0.5.0-windows.zip": zipped({"Nanar/Nanar.exe": b"exe"}),
            "https://dl.test/nanar-0.5.0-windows.zip.sha256": b"0" * 64 + b"  x.zip\n",
        },
    )
    found.check()
    install = tmp_path / "Nanar"
    install.mkdir()
    with pytest.raises(UpdateError, match="bad_checksum"):
        found.prepare(install)
    assert not found.state()["installing"]
