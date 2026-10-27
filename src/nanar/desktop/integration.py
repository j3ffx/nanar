"""Nanar in Windows' menus: a Start menu entry, and "Ouvrir avec Nanar" on folders.

Only for the user (HKCU and their own Start menu folder), never machine-wide, and only when the
user said yes on the TV page. Both point to the executable where it is now: after moving the
unzipped folder, saying yes again points them to the new place.
"""

import contextlib
import os
import subprocess
import sys
from pathlib import Path

assert sys.platform == "win32"  # also tells mypy to check this module for Windows only

import winreg  # noqa: E402

MENU_KEYS = (
    # A right click on a folder, and on the background of an open folder.
    (r"Software\Classes\Directory\shell\Nanar", '"{exe}" "%1"'),
    (r"Software\Classes\Directory\Background\shell\Nanar", '"{exe}" "%V"'),
)


def start_menu_shortcut() -> Path:
    programs = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return programs / "Nanar.lnk"


def install(exe: Path) -> None:
    for key_path, command in MENU_KEYS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "Ouvrir avec Nanar")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, f"{exe},0")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command.format(exe=exe))
    _make_shortcut(start_menu_shortcut(), exe)


def uninstall() -> None:
    for key_path, _ in MENU_KEYS:
        for sub in (key_path + r"\command", key_path):
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
    start_menu_shortcut().unlink(missing_ok=True)


def is_installed(exe: Path) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEYS[0][0] + r"\command") as key:
            value, _ = winreg.QueryValueEx(key, "")
    except FileNotFoundError:
        return False
    return str(value).startswith(f'"{exe}"') and start_menu_shortcut().is_file()


def _make_shortcut(link: Path, exe: Path) -> None:
    """A .lnk file, through the shell's own COM object (PowerShell ships with Windows)."""
    link.parent.mkdir(parents=True, exist_ok=True)

    def quoted(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut("
        + quoted(link)
        + "); $s.TargetPath = "
        + quoted(exe)
        + "; $s.WorkingDirectory = "
        + quoted(exe.parent)
        + "; $s.IconLocation = "
        + quoted(exe)
        + "; $s.Description = 'Tes films sur la télé'; $s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
