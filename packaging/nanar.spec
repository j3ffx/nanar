# PyInstaller spec for the Windows build: a folder holding Nanar.exe and everything it needs
# (Python, libmpv, the pages), zipped by scripts/build-windows.py. See CLAUDE.md → Releases.
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent  # noqa: F821 (given by PyInstaller)
PACKAGE = ROOT / "src" / "nanar"

datas = [
    (str(PACKAGE / "web" / "static"), "nanar/web/static"),
    (str(PACKAGE / "assets"), "nanar/assets"),
]
# guessit and babelfish read their rules and language tables from data files.
datas += collect_data_files("guessit") + collect_data_files("babelfish")
datas += copy_metadata("nanar")  # nanar.__version__ reads it

binaries = [(str(ROOT / "vendor" / "libmpv-2.dll"), ".")]

hiddenimports = (
    collect_submodules("uvicorn")  # picked by name at run time
    + collect_submodules("guessit")
    + collect_submodules("babelfish")
    + collect_submodules("zeroconf")
    + ["nanar.desktop.integration", "nanar.desktop.win32"]
)

a = Analysis(
    [str(PACKAGE / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "mypy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Nanar",
    icon=str(PACKAGE / "assets" / "nanar.ico"),
    console=False,  # a window, no console behind it
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Nanar", upx=False)
