import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nanar.cli import cli
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
