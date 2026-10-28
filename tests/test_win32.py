import sys
from pathlib import Path

import pytest

if sys.platform != "win32":  # also tells mypy that the module is Windows-only
    pytest.skip("Windows' own file marks", allow_module_level=True)


def mark_downloaded(path: Path) -> None:
    """What a browser and the zip extraction leave on a file (Mark of the Web)."""
    Path(f"{path}:Zone.Identifier").write_text("[ZoneTransfer]\r\nZoneId=3\r\n")


def is_marked(path: Path) -> bool:
    return Path(f"{path}:Zone.Identifier").exists()


def test_unmarks_the_dlls_shipped_with_nanar(tmp_path: Path) -> None:
    from nanar.desktop import win32

    runtime = tmp_path / "_internal" / "pythonnet" / "runtime"
    runtime.mkdir(parents=True)
    dll = runtime / "Python.Runtime.dll"
    dll.write_bytes(b"MZ")
    other = tmp_path / "_internal" / "readme.txt"
    other.write_text("not a dll")
    mark_downloaded(dll)
    mark_downloaded(other)
    assert is_marked(dll)

    assert win32.unblock_bundle(tmp_path) == 1
    assert not is_marked(dll)
    assert dll.read_bytes() == b"MZ"  # the file itself is untouched
    assert is_marked(other)  # only the DLLs .NET loads
    assert win32.unblock_bundle(tmp_path) == 0  # nothing left to do
