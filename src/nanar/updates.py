"""New versions of the Windows build: found on GitHub, installed in one click (off by default).

When the user ticks the box in the settings, Nanar asks GitHub's API for the latest release, at
most once a day: that request (the address of the PC, and "Nanar v<version>" as its user agent)
is all it sends. When a newer version is out, the TV page offers it; on a yes, Nanar downloads
the zip next to its own folder, checks it against the release's SHA-256, unzips it, and hands
over to a small PowerShell script that waits for Nanar to close, swaps the folders, and starts
the new Nanar (the old one again if the swap failed). Run from the sources, `git pull` does it.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanar import __version__
from nanar.online import OnlineError, Request, fetch

REPO = "j3ffx/nanar"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECK_EVERY = 24 * 3600
WAKE_EVERY = 3600.0  # how often the background thread looks whether a day has passed

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Release:
    version: str
    zip_url: str
    sha256_url: str


class UpdateError(Exception):
    """`code`: "offline", "bad_checksum", "update_failed", "not_supported"."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def version_of(text: str) -> tuple[int, ...] | None:
    """(0, 4, 0) from "v0.4.0" or "0.4.0"; None for anything else (a pre-release)."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def release_of(data: dict[str, Any]) -> Release | None:
    """The Windows zip of a release, as GitHub's API describes it."""
    version = str(data.get("tag_name") or "").lstrip("v")
    if data.get("draft") or data.get("prerelease") or version_of(version) is None:
        return None
    urls = {a.get("name"): a.get("browser_download_url") for a in data.get("assets") or []}
    name = f"nanar-{version}-windows.zip"
    if not urls.get(name) or not urls.get(name + ".sha256"):
        return None
    return Release(version, str(urls[name]), str(urls[name + ".sha256"]))


def _download(url: str, target: Path) -> None:
    raw = urllib.request.Request(url, headers={"User-Agent": f"Nanar v{__version__}"})
    try:
        with urllib.request.urlopen(raw, timeout=60) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out, 1 << 20)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UpdateError("offline") from None


# Waits for Nanar to close, swaps its folder for the new one, and starts it.
_SWAP = r"""
param([int]$ProcessId, [string]$New, [string]$Target)
Wait-Process -Id $ProcessId -Timeout 120 -ErrorAction SilentlyContinue
$old = "$Target.old"
if (Test-Path $old) { Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue }
for ($i = 0; $i -lt 40 -and (Test-Path $Target); $i++) {
  try { Move-Item $Target $old -ErrorAction Stop } catch { Start-Sleep -Milliseconds 500 }
}
if (Test-Path $Target) { Start-Process (Join-Path $Target 'Nanar.exe'); exit }
Move-Item $New $Target
Start-Process (Join-Path $Target 'Nanar.exe')
Start-Sleep -Seconds 5
Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Split-Path (Split-Path $New)) -Recurse -Force -ErrorAction SilentlyContinue
"""


class Updates:
    def __init__(
        self,
        *,
        enabled: Callable[[], bool],
        checked_at: Callable[[], float],
        mark_checked: Callable[[float], None],
        on_change: Callable[[], None],
        get: Callable[[Request], bytes] = fetch,
        download: Callable[[str, Path], None] = _download,
        supported: bool | None = None,
    ) -> None:
        self._enabled = enabled
        self._checked_at = checked_at
        self._mark_checked = mark_checked
        self._on_change = on_change
        self._get = get
        self._download = download
        self.supported = (
            supported
            if supported is not None
            else sys.platform == "win32" and bool(getattr(sys, "frozen", False))
        )
        self.available: Release | None = None
        self.installing = False
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def state(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "enabled": self._enabled(),
            "available": self.available.version if self.available else None,
            "installing": self.installing,
        }

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._watch, name="nanar-updates", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def poke(self) -> None:
        """The box was just ticked: look now rather than within the hour."""
        self._wake.set()

    def _watch(self) -> None:
        while not self._stop.is_set():
            if self._enabled() and time.time() - self._checked_at() >= CHECK_EVERY:
                try:
                    self.check()
                except UpdateError as error:
                    log.info("no news of updates: %s", error.code)
            self._wake.wait(WAKE_EVERY)
            self._wake.clear()

    def check(self) -> Release | None:
        """Asks GitHub for the latest release; keeps it when it is newer than this Nanar."""
        try:
            data = self._get(Request(LATEST, {"Accept": "application/vnd.github+json"}))
        except OnlineError as error:
            raise UpdateError("offline") from error
        release = release_of(json.loads(data))
        self._mark_checked(time.time())
        mine = version_of(__version__) or (0,)
        theirs = version_of(release.version) if release else None
        self.available = release if theirs and theirs > mine else None
        self._on_change()
        return self.available

    def prepare(self, install: Path) -> list[str]:
        """Downloads, checks and unzips the new version next to `install` (Nanar's folder), and
        gives the command that swaps them once Nanar has closed."""
        release = self.available
        if not self.supported or release is None:
            raise UpdateError("not_supported")
        work = install.parent / f"{install.name}.update"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        self.installing = True
        self._on_change()
        try:
            archive = work / "nanar.zip"
            self._download(release.zip_url, archive)
            checksum = work / "nanar.zip.sha256"
            self._download(release.sha256_url, checksum)
            expected = checksum.read_text(encoding="ascii", errors="replace").split()[:1]
            digest = hashlib.sha256()
            with archive.open("rb") as file:
                for block in iter(lambda: file.read(1 << 20), b""):
                    digest.update(block)
            if not expected or digest.hexdigest() != expected[0].lower():
                raise UpdateError("bad_checksum")
            unzipped = work / "new"
            with zipfile.ZipFile(archive) as zipped:
                for member in zipped.namelist():  # nothing outside its own folder
                    if not (unzipped / member).resolve().is_relative_to(unzipped.resolve()):
                        raise UpdateError("update_failed")
                zipped.extractall(unzipped)
            if not (unzipped / "Nanar" / "Nanar.exe").is_file():
                raise UpdateError("update_failed")
            archive.unlink()
            script = work / "swap.ps1"
            script.write_text(_SWAP, encoding="utf-8")
        except (OSError, zipfile.BadZipFile) as error:
            self.installing = False
            self._on_change()
            raise UpdateError("update_failed") from error
        except UpdateError:
            self.installing = False
            self._on_change()
            raise
        return [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-ProcessId",
            str(os.getpid()),
            "-New",
            str(unzipped / "Nanar"),
            "-Target",
            str(install),
        ]


def launch(command: list[str]) -> None:
    """Starts the swap on its own: it outlives Nanar, which closes right after."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen(command, creationflags=flags, close_fds=True)
