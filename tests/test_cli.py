import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nanar.cli import cli, offers_integration
from nanar.config import Settings


def test_uninstall_removes_the_menus_and_stops_offering_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NANAR_DATA_DIR", str(tmp_path))
    removed: list[bool] = []
    if sys.platform == "win32":  # never the real registry and Start menu
        from nanar.desktop import integration

        monkeypatch.setattr(integration, "uninstall", lambda: removed.append(True))

    result = CliRunner().invoke(cli, ["--uninstall"])

    assert result.exit_code == 0, result.output
    assert "plus dans le menu Démarrer" in result.output
    assert removed == ([True] if sys.platform == "win32" else [])
    assert Settings.load(tmp_path / "settings.json").integration_answered


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows build only")
def test_offers_the_menus_again_when_an_earlier_yes_was_undone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nanar.desktop import integration

    shortcut = tmp_path / "Nanar.lnk"  # never the real registry and Start menu
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(integration, "is_installed", lambda exe: False)
    monkeypatch.setattr(integration, "start_menu_shortcut", lambda: shortcut)
    assert offers_integration(Settings())  # never asked
    assert not offers_integration(Settings(integration_answered=True))  # "no", or --uninstall
    shortcut.write_bytes(b"")
    assert offers_integration(Settings(integration_answered=True))  # "yes", menus gone since
