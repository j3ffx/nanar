"""New versions of the Windows build: found on GitHub, installed in one click (off by default).

When the user ticks the box in the settings, Nanar asks GitHub's API for the latest release, when
it starts and then at most once a day. GitHub then sees the PC's public address and "Nanar
v<version>" as the user agent: nothing else is sent. When a newer version is out, the TV page
offers it; on a yes, Nanar downloads the zip next to its own folder, checks it against the
release's SHA-256, unzips it, and hands over to a small PowerShell script. The script waits for
Nanar to close, swaps the folders and starts the new Nanar; if it does not answer within a while,
the old folder comes back and starts instead. Run from the sources, `git pull` does it.

The checksum catches a damaged download, not a compromised release: both come from GitHub.
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
from nanar.system import powershell

REPO = "j3ffx/nanar"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOADS = f"https://github.com/{REPO}/releases/download/"
CHECK_EVERY = 24 * 3600
WAKE_EVERY = 3600.0  # how often the background thread looks whether a day has passed
MAX_UNZIPPED = 2_000_000_000  # bytes: far more than a build, far less than a full disk
ANSWER_WITHIN = 45  # seconds the new version has to answer before the old one comes back

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
    """The Windows zip of a release, as GitHub's API describes it: from this repository only."""
    version = str(data.get("tag_name") or "").lstrip("v")
    if data.get("draft") or data.get("prerelease") or version_of(version) is None:
        return None
    urls = {a.get("name"): a.get("browser_download_url") for a in data.get("assets") or []}
    name = f"nanar-{version}-windows.zip"
    zip_url, sha256_url = str(urls.get(name) or ""), str(urls.get(name + ".sha256") or "")
    if not zip_url.startswith(DOWNLOADS) or not sha256_url.startswith(DOWNLOADS):
        return None
    return Release(version, zip_url, sha256_url)


def _download(url: str, target: Path) -> None:
    raw = urllib.request.Request(url, headers={"User-Agent": f"Nanar v{__version__}"})
    try:
        with urllib.request.urlopen(raw, timeout=60) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out, 1 << 20)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise UpdateError("offline") from None


# Waits for Nanar to close, swaps its folder for the new one, and starts it; brings the old one
# back when the new one can't be put in place, or doesn't answer. A folder's rename either happens
# or doesn't, unlike Move-Item, which can leave half of a folder behind.
SWAP = r"""
param(
  [int]$ProcessId, [string]$New, [string]$Target, [string]$Version, [int]$Port,
  [int]$AnswerWithin = 45
)
$ErrorActionPreference = 'Stop'
$old = "$Target.old"
$work = Split-Path (Split-Path $New)

function Start-Nanar {
  # Not Start-Process: it reads "[HD]" in a folder's name as a wildcard.
  $info = New-Object Diagnostics.ProcessStartInfo
  $info.FileName = "$Target\Nanar.exe"
  $info.WorkingDirectory = $Target
  $info.Arguments = "--port $Port"
  $info.UseShellExecute = $true
  [Diagnostics.Process]::Start($info)
}
function Rename-Retrying($From, $To) {
  for ($i = 0; $i -lt 40; $i++) {
    try { [IO.Directory]::Move($From, $To); return $true } catch { Start-Sleep -Milliseconds 500 }
  }
  return $false
}
function Answers {
  try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
    return $health.version -eq $Version
  } catch { return $false }
}

try { Wait-Process -Id $ProcessId -Timeout 120 } catch {}
if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force }
if (-not (Rename-Retrying $Target $old)) { Start-Nanar | Out-Null; exit 1 }
$started = $null
$fine = Rename-Retrying $New $Target
if ($fine) {
  try { $started = Start-Nanar } catch { $fine = $false }
}
if ($fine) {
  $fine = $false
  for ($i = 0; $i -lt $AnswerWithin -and -not $fine; $i++) {
    Start-Sleep -Seconds 1
    $fine = Answers
  }
}
if (-not $fine) {
  if ($started) { try { Stop-Process -Id $started.Id -Force } catch {} }
  Start-Sleep -Seconds 1
  if (Test-Path -LiteralPath $Target) {
    try { Remove-Item -LiteralPath $Target -Recurse -Force } catch {}
  }
  if (Rename-Retrying $old $Target) { Start-Nanar | Out-Null }
  exit 1
}
Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
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
        self._install_lock = threading.Lock()

    def state(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "supported": self.supported,
            "enabled": self._enabled(),
            "checkedAt": self._checked_at() or None,
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
        # Once when Nanar starts (what was found last time isn't kept), then once a day.
        due = True
        while not self._stop.is_set():
            if self.supported and self._enabled() and due:
                try:
                    self.check()
                except UpdateError as error:
                    log.info("no news of updates: %s", error.code)
                except Exception:  # an odd answer from GitHub is no reason to stop looking
                    log.exception("looking for updates failed")
            poked = self._wake.wait(WAKE_EVERY)
            self._wake.clear()
            due = poked or time.time() - self._checked_at() >= CHECK_EVERY

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

    def prepare(self, install: Path, port: int) -> list[str]:
        """Downloads, checks and unzips the new version next to `install` (Nanar's folder), and
        gives the command that swaps them once Nanar has closed."""
        release = self.available
        if not self.supported or release is None:
            raise UpdateError("not_supported")
        if not self._install_lock.acquire(blocking=False):
            raise UpdateError("update_failed")  # already under way
        self.installing = True
        self._on_change()
        try:
            return self._prepare(release, install, port)
        except UpdateError:
            self.cancelled()
            raise
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            log.warning("the update failed: %s", error)
            self.cancelled()
            raise UpdateError("update_failed") from error

    def cancelled(self) -> None:
        """The install did not go through: Nanar goes on as it was."""
        self.installing = False
        if self._install_lock.locked():
            self._install_lock.release()
        self._on_change()

    def _prepare(self, release: Release, install: Path, port: int) -> list[str]:
        work = install.parent / f"{install.name}.update"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
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
            shutil.rmtree(work, ignore_errors=True)
            raise UpdateError("bad_checksum")
        unzipped = work / "new"
        with zipfile.ZipFile(archive) as zipped:
            if sum(member.file_size for member in zipped.infolist()) > MAX_UNZIPPED:
                raise UpdateError("update_failed")
            for name in zipped.namelist():  # nothing outside its own folder
                if not (unzipped / name).resolve().is_relative_to(unzipped.resolve()):
                    raise UpdateError("update_failed")
            zipped.extractall(unzipped)
        if not (unzipped / "Nanar" / "Nanar.exe").is_file():
            raise UpdateError("update_failed")
        archive.unlink()
        script = work / "swap.ps1"
        script.write_text(SWAP, encoding="utf-8")
        return swap_command(script, os.getpid(), unzipped / "Nanar", install, release.version, port)


def swap_command(
    script: Path,
    pid: int,
    new: Path,
    target: Path,
    version: str,
    port: int,
    answer_within: int = ANSWER_WITHIN,
) -> list[str]:
    return [
        powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ProcessId",
        str(pid),
        "-New",
        str(new),
        "-Target",
        str(target),
        "-Version",
        version,
        "-Port",
        str(port),
        "-AnswerWithin",
        str(answer_within),
    ]


def launch(command: list[str], folder: Path) -> None:
    """Starts the swap on its own: it outlives Nanar, which closes right after. PowerShell needs a
    console of its own, even an invisible one, or it stops at once; and it must not run from the
    folder it is about to move (`folder`: next to it)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    subprocess.Popen(
        command,
        cwd=folder,
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
