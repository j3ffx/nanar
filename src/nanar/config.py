"""Where Nanar keeps its data, and the settings it remembers between runs."""

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import platformdirs

DEFAULT_PORT = 8642


def data_dir(*, demo: bool = False) -> Path:
    """The user's data directory (NANAR_DATA_DIR overrides it); the demo keeps its own."""
    override = os.environ.get("NANAR_DATA_DIR")
    base = (
        Path(override) if override else Path(platformdirs.user_data_dir("nanar", appauthor=False))
    )
    path = base / "demo" if demo else base
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Settings:
    """What Nanar remembers: the last folder opened and how the window was left."""

    last_folder: str | None = None
    fullscreen: bool = False
    # Languages tried in order, for the audio and for the subtitles (ISO 639 codes and the
    # names release groups use). Subtitles in the language of the audio are left off.
    audio_languages: list[str] = field(default_factory=lambda: ["fr", "fre", "fra", "en", "eng"])
    subtitle_languages: list[str] = field(default_factory=lambda: ["fr", "fre", "fra"])

    @classmethod
    def load(cls, path: Path) -> "Settings":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
