"""Whether Windows' firewall keeps the phones out, as a phone that finds nothing says nothing.

Windows asks about a program the first time it listens, and each box ticked covers one kind of
network: allowed on the hotel's "public" Wi-Fi, Nanar stays blocked at home on a "private" one, with
no question this time. Nanar only reads the rules: changing them takes an administrator, and the
user's yes (the TV page says where). In doubt it says nothing: a rule may open the port rather than
the program, which it can't read without an administrator, and the phone connected proves it anyway.
"""

import base64
import json
import logging
import os
import subprocess
import sys
from typing import Any

from nanar.system import powershell

log = logging.getLogger(__name__)

TIMEOUT = 30.0  # seconds: PowerShell itself may take ten to start

# The networks the PC is on, the firewall of each kind of network, and the rules for the program.
_SCRIPT = """
$ErrorActionPreference = 'Stop'
$profiles = @(Get-NetConnectionProfile)
$online = @($profiles | Where-Object { $_.IPv4Connectivity.ToString() -eq 'Internet' })
if ($online.Count -gt 0) { $profiles = $online }  # not the virtual adapters beside a real one
$rules = @(Get-NetFirewallApplicationFilter |
  Where-Object { $_.Program -eq $env:NANAR_PROGRAM } |
  Get-NetFirewallRule |
  Where-Object { $_.Direction.ToString() -eq 'Inbound' -and $_.Enabled.ToString() -eq 'True' })
ConvertTo-Json -Depth 3 -Compress -InputObject @{
  networks = @($profiles | ForEach-Object { $_.NetworkCategory.ToString() })
  off = @(Get-NetFirewallProfile |
    Where-Object { $_.Enabled.ToString() -eq 'False' } |
    ForEach-Object { $_.Name.ToString() })
  rules = @($rules | ForEach-Object {
    @{ action = $_.Action.ToString(); profile = $_.Profile.ToString() } })
}
"""


def _covers(rule: dict[str, str], kind: str) -> bool:
    """A rule's profile reads "Any", or "Private" or "Domain, Private"."""
    profile = rule.get("profile", "")
    return profile == "Any" or kind in [part.strip() for part in profile.split(",")]


def blocked_network(report: dict[str, Any]) -> str | None:
    """The kind of network ("Private", "Public", "Domain") where the phones are kept out."""
    rules: list[dict[str, str]] = report.get("rules") or []
    if not rules:
        return None  # never asked, or the question is on the screen: Windows speaks for itself
    for network in report.get("networks") or []:
        kind = "Domain" if network.startswith("Domain") else network
        if kind in (report.get("off") or []):
            continue
        covering = [rule for rule in rules if _covers(rule, kind)]
        allowed = any(rule.get("action") == "Allow" for rule in covering)
        if not allowed or any(rule.get("action") == "Block" for rule in covering):
            return str(kind)  # as for Windows, a rule that blocks wins over one that allows
    return None


def check(program: str) -> str | None:
    """Reads the rules for this program now; takes seconds. None when all looks well, or unknown."""
    if sys.platform != "win32":
        return None
    encoded = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")
    try:
        done = subprocess.run(
            [powershell(), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            timeout=TIMEOUT,
            env=os.environ | {"NANAR_PROGRAM": program},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        report = json.loads(done.stdout.decode("utf-8", errors="replace").strip() or "{}")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        log.warning("could not read the firewall's rules")
        return None
    return blocked_network(report) if isinstance(report, dict) else None
