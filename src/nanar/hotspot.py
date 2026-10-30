"""Mode hôtel: the PC opens a Wi-Fi of its own, which the phone joins to reach Nanar.

Hotel Wi-Fis often keep their guests' devices apart: the phone can't see the PC on them. Windows
can share the PC's connection as a hotspot (Settings, "Point d'accès sans fil mobile"); Nanar
turns it on when asked on the TV page, shows its name and password as a QR code that phones join
in one scan, and turns it off again when Nanar closes, if Nanar turned it on.

Windows only, through its own WinRT API, called from PowerShell (which ships with Windows): no
dependency of Nanar's own. The password is held in memory for the TV page's QR code, never
written to a log or sent to a phone.
"""

import base64
import ipaddress
import json
import logging
import subprocess
import sys
import threading
from dataclasses import dataclass

import ifaddr

log = logging.getLogger(__name__)

# The network Windows gives its hotspot (Internet Connection Sharing).
HOTSPOT_NETWORK = ipaddress.IPv4Network("192.168.137.0/24")
TIMEOUT = 40.0  # seconds: turning it on takes a few, PowerShell a second or two to start


@dataclass(frozen=True)
class Status:
    available: bool  # this PC can open a hotspot now (it has a connection to share)
    on: bool = False
    ssid: str | None = None
    passphrase: str | None = None
    code: str | None = None  # why not: "no_internet", "unavailable", "failed"

    def public(self) -> dict[str, object]:
        """What the live state says (phones included): never the password."""
        return {"available": self.available, "on": self.on, "ssid": self.ssid if self.on else None}


class HotspotError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def wifi_qr(ssid: str, passphrase: str) -> str:
    """What a phone's camera reads to join a Wi-Fi (the "WIFI:" scheme Android and iOS know)."""

    def escaped(text: str) -> str:
        for char in '\\;,:"':
            text = text.replace(char, "\\" + char)
        return text

    return f"WIFI:T:WPA;S:{escaped(ssid)};P:{escaped(passphrase)};;"


def address(adapters: list[ifaddr.Adapter] | None = None) -> str | None:
    """This PC's address on its hotspot, where phones that joined it find Nanar."""
    for adapter in adapters if adapters is not None else ifaddr.get_adapters():
        for ip in adapter.ips:
            if isinstance(ip.ip, str) and ipaddress.IPv4Address(ip.ip) in HOTSPOT_NETWORK:
                return ip.ip
    return None


def first(addresses: list[str], preferred: str | None) -> list[str]:
    """`addresses` with `preferred` first: the QR code holds the first one."""
    if preferred is None:
        return addresses
    return [preferred, *(a for a in addresses if a != preferred)]


class NoHotspot:
    """Elsewhere than Windows, or for tests: nothing to open."""

    def status(self) -> Status:
        return Status(available=False, code="unavailable")

    def turn(self, on: bool) -> Status:
        raise HotspotError("unavailable")

    def close(self) -> None:
        pass

    @property
    def last(self) -> Status:
        return self.status()


# Run by PowerShell. Every call opens the manager anew: the hotspot belongs to the connection
# shared, and the PC may have changed networks since.
_SCRIPT = r"""
param([string]$Action)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
  $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
  $task.Wait(-1) | Out-Null
  $task.Result
}
function WinRT($ns, $name) { "$ns.$name, $ns, ContentType = WindowsRuntime" -as [type] }
$info = WinRT 'Windows.Networking.Connectivity' 'NetworkInformation'
$tm = WinRT 'Windows.Networking.NetworkOperators' 'NetworkOperatorTetheringManager'
$result = WinRT 'Windows.Networking.NetworkOperators' 'NetworkOperatorTetheringOperationResult'
$out = [ordered]@{ available = $false; on = $false; ssid = $null; passphrase = $null; code = $null }
$profile = $info::GetInternetConnectionProfile()
if ($null -eq $profile) {
  $out.code = 'no_internet'
} elseif ($tm::GetTetheringCapabilityFromConnectionProfile($profile).ToString() -ne 'Enabled') {
  $out.code = 'unavailable'
} else {
  $m = $tm::CreateFromConnectionProfile($profile)
  $out.available = $true
  $state = $m.TetheringOperationalState.ToString()
  if ($Action -eq 'on' -and $state -ne 'On') {
    $r = Await ($m.StartTetheringAsync()) $result
    if ($r.Status.ToString() -ne 'Success') { $out.code = 'failed' }
  } elseif ($Action -eq 'off' -and $state -ne 'Off') {
    $r = Await ($m.StopTetheringAsync()) $result
    if ($r.Status.ToString() -ne 'Success') { $out.code = 'failed' }
  }
  for ($i = 0; $i -lt 20 -and $m.TetheringOperationalState.ToString() -eq 'InTransition'; $i++) {
    Start-Sleep -Milliseconds 500
  }
  $out.on = $m.TetheringOperationalState.ToString() -eq 'On'
  $config = $m.GetCurrentAccessPointConfiguration()
  $out.ssid = $config.Ssid
  $out.passphrase = $config.Passphrase
}
$out | ConvertTo-Json -Compress
"""


class WindowsHotspot:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last = Status(available=False)
        self._ours = False  # turned on by Nanar: turned off when it closes

    @property
    def last(self) -> Status:
        """The status found by the last call (the password included, for the QR code)."""
        return self._last

    def status(self) -> Status:
        return self._run("status")

    def turn(self, on: bool) -> Status:
        before = self._last.on
        status = self._run("on" if on else "off")
        if status.code is not None:
            raise HotspotError(status.code)
        if on and not before and status.on:
            self._ours = True
        if not on:
            self._ours = False
        return status

    def close(self) -> None:
        if self._ours:
            try:
                self._run("off")
            except HotspotError:
                log.warning("the hotspot Nanar opened could not be closed")
            self._ours = False

    def _run(self, action: str) -> Status:
        script = f"& {{ {_SCRIPT} }} '{action}'"
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        with self._lock:
            try:
                done = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                    capture_output=True,
                    timeout=TIMEOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
                raw = json.loads(done.stdout.decode("utf-8", errors="replace").strip() or "{}")
            except (OSError, subprocess.TimeoutExpired, ValueError):
                # The output holds the password: it is not logged.
                log.warning("the hotspot did not answer (%s)", action)
                raise HotspotError("failed") from None
            status = Status(
                available=bool(raw.get("available")),
                on=bool(raw.get("on")),
                ssid=raw.get("ssid") or None,
                passphrase=raw.get("passphrase") or None,
                code=raw.get("code") or (None if raw else "failed"),
            )
            self._last = status
            return status


def make() -> "WindowsHotspot | NoHotspot":
    return WindowsHotspot() if sys.platform == "win32" else NoHotspot()
