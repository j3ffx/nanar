# PyInstaller spec for the Windows build: a folder holding Nanar.exe and everything it needs
# (Python, libmpv, the pages), zipped by scripts/build-windows.py. See CLAUDE.md → Releases.
# ruff: noqa
import re
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
from PyInstaller.utils.win32 import versioninfo as vi

ROOT = Path(SPECPATH).parent  # noqa: F821 (given by PyInstaller)
PACKAGE = ROOT / "src" / "nanar"

datas = [
    (str(PACKAGE / "web" / "static"), "nanar/web/static"),
    (str(PACKAGE / "assets"), "nanar/assets"),
]
# guessit and babelfish read their rules and language tables from data files.
datas += collect_data_files("guessit") + collect_data_files("babelfish")
datas += copy_metadata("nanar")  # nanar.__version__ reads it

# Name and version in the file's properties: what Windows shows, and what code signing checks.
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
NUMBERS = tuple(int(n) for n in re.findall(r"\d+", VERSION)[:3]) + (0,)
STRINGS = {
    "CompanyName": "Nanar",
    "FileDescription": "Nanar",
    "FileVersion": VERSION,
    "InternalName": "Nanar",
    "LegalCopyright": "GPL-3.0",
    "OriginalFilename": "Nanar.exe",
    "ProductName": "Nanar",
    "ProductVersion": VERSION,
}
version_info = vi.VSVersionInfo(
    ffi=vi.FixedFileInfo(filevers=NUMBERS, prodvers=NUMBERS),
    kids=[
        vi.StringFileInfo(
            [vi.StringTable("040904B0", [vi.StringStruct(k, v) for k, v in STRINGS.items()])]
        ),
        vi.VarFileInfo([vi.VarStruct("Translation", [0x0409, 1200])]),
    ],
)

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
    version=version_info,
    console=False,  # a window, no console behind it
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Nanar", upx=False)
