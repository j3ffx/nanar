"""The system's own programs, by their full path: run by name, Windows would look in the current
folder first, and a film folder is no place to find a program in."""

import os
from pathlib import Path


def powershell() -> str:
    root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    return str(Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
