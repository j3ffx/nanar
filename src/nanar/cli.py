"""`nanar [FOLDER]`: opens Nanar on a folder of videos (the last one when none is given).

Without any folder yet, the TV page asks for one. When Nanar is already open, a second launch
(a right click on a folder → "Ouvrir avec Nanar") hands its folder to it and stops.
"""

import contextlib
import importlib
import json
import os
import socket
import sys
import threading
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
import uvicorn

from nanar import __version__
from nanar.config import DEFAULT_PORT, Settings, data_dir
from nanar.controller import CommandError, Controller

if TYPE_CHECKING:
    from nanar.desktop.window import TvWindow
    from nanar.folders import Folders

cli = typer.Typer(add_completion=False, no_args_is_help=False, rich_markup_mode=None)


@cli.command()
def open_folder(
    folder: Annotated[
        Path | None,
        typer.Argument(
            help="Le dossier de vidéos (par défaut : le dernier ouvert).", show_default=False
        ),
    ] = None,
    demo: Annotated[
        bool, typer.Option(help="Une bibliothèque factice, sans aucun fichier.")
    ] = False,
    port: Annotated[int, typer.Option(help="Le port du serveur.")] = DEFAULT_PORT,
    headless: Annotated[
        bool, typer.Option(help="Sans fenêtre Nanar : mpv seul, piloté par l'API.")
    ] = False,
    local: Annotated[
        bool, typer.Option(help="Sans télécommande : rien n'écoute sur le réseau.")
    ] = False,
    new_key: Annotated[
        bool, typer.Option(help="Change le QR code : les téléphones déjà appairés ne le sont plus.")
    ] = False,
    dev: Annotated[
        bool, typer.Option(help="La page vient du serveur Vite (npm run dev).", hidden=True)
    ] = False,
    uninstall: Annotated[
        bool, typer.Option(help="Retire Nanar du menu Démarrer et du clic droit sur les dossiers.")
    ] = False,
    version: Annotated[bool, typer.Option("--version", help="Affiche la version.")] = False,
    self_check: Annotated[
        bool, typer.Option(help="Charge la fenêtre et libmpv, puis s'arrête.", hidden=True)
    ] = False,
) -> None:
    """Nanar : tes films sur la télé, la télécommande dans le téléphone."""
    if version:
        print(f"Nanar {__version__}")
        return
    if self_check:
        check_parts()
        return
    if uninstall:
        remove_integration()
        return
    if port_taken(port):
        hand_over(port, folder)
        return

    from nanar import demo as demo_library
    from nanar import hotspot
    from nanar.app import Network, create_app
    from nanar.discovery import HOST, Announcer
    from nanar.folders import Folders
    from nanar.library import Library
    from nanar.metadata import Metadata
    from nanar.pairing import lan_addresses, load_key
    from nanar.player import MpvSession
    from nanar.previews import Previews
    from nanar.progress import Progress
    from nanar.subtitles import Subtitles
    from nanar.thumbnails import Thumbnails

    settings_path = data_dir(demo=demo) / "settings.json"
    settings = Settings.load(settings_path)
    library = demo_library.library() if demo else Library(root="")

    # One key for the demo and the real library: a phone paired once stays paired.
    key = load_key(data_dir(), renew=new_key)
    network = Network(port=port, lan=not local)
    wifi = hotspot.NoHotspot() if local else hotspot.make()
    # On the PC's own Wi-Fi (mode hôtel), the QR code leads there.
    network.addresses = lambda: hotspot.first(
        lan_addresses(), hotspot.address() if wifi.last.on else None
    )
    if shown := os.environ.get("NANAR_SHOW_ADDRESS"):
        # Screenshots for the README: an address reserved for documentation, nothing announced.
        network.addresses = lambda: [shown]
        wifi = hotspot.NoHotspot()
    announcer = Announcer(port, network.addresses)
    if network.lan and not shown:
        announcer.start()
        network.name = lambda: HOST if announcer.active else None

    progress = Progress(data_dir(demo=demo) / "progress.db")
    controller = Controller(
        library, settings, settings_path, MpvSession, progress=progress, demo=demo
    )
    thumbnails = Thumbnails(data_dir(demo=demo) / "thumbnails", on_ready=controller.library_changed)
    controller.thumbnails = thumbnails
    controller.previews = Previews(data_dir(demo=demo) / "previews")
    metadata = Metadata(data_dir(demo=demo) / "tmdb", on_ready=controller.library_changed)
    metadata.configure(settings.tmdb_key)
    controller.metadata = metadata
    controller.subtitles = Subtitles(data_dir(demo=demo) / "subtitles")
    controller.subtitles.configure(settings.opensubtitles_key)
    if not demo:  # the demo keeps its coloured cards: frames of test patterns show nothing
        thumbnails.schedule(library)
    metadata.schedule(library)
    folders = Folders(controller, settings, None if demo else settings_path)
    if not demo:
        chosen = folder or (Path(settings.last_folder) if settings.last_folder else None)
        if chosen is not None:
            try:
                folders.open(chosen)
            except CommandError:
                print(f"{chosen} n'est pas un dossier : choisis-en un sur la télé.")
    print(f"Nanar {__version__} : {len(controller.library.videos)} vidéo(s)")

    def check_hotspot() -> None:  # a second or two (PowerShell): not in the way of the start
        with contextlib.suppress(hotspot.HotspotError):
            controller.set_hotspot(wifi.status().public())

    threading.Thread(target=check_hotspot, name="nanar-hotspot", daemon=True).start()

    app_holder: list[Desktop] = []
    app = create_app(
        controller,
        key=key,
        network=network,
        desktop=_LazyDesktop(app_holder),
        hotspot=wifi,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1" if local else "0.0.0.0", port=port, log_level="warning"
        )
    )

    def stop_all() -> None:
        controller.shutdown()
        thumbnails.stop()
        metadata.stop()
        folders.stop()
        announcer.stop()
        wifi.close()

    if headless:
        try:
            server.run()
        finally:
            stop_all()
        return

    from nanar.desktop.window import TvWindow

    page = "http://localhost:5173/tv" if dev else f"http://127.0.0.1:{port}/tv"
    window = TvWindow(page, fullscreen=settings.fullscreen)
    controller.window = window
    app_holder.append(Desktop(controller, folders, window, settings, settings_path))
    if offers_integration(settings):
        controller.set_integration_offer(True)
    thread = threading.Thread(target=server.run, name="nanar-server", daemon=True)
    thread.start()
    try:
        window.run()  # until the window is closed
    finally:
        stop_all()
        server.should_exit = True
        thread.join(timeout=5)


class Desktop:
    """What the TV page may ask of this machine (`app.Desktop`)."""

    def __init__(
        self,
        controller: Controller,
        folders: "Folders",
        window: "TvWindow",
        settings: Settings,
        settings_path: Path,
    ) -> None:
        self._controller = controller
        self._folders = folders
        self._window = window
        self._settings = settings
        self._settings_path = settings_path

    def open(self, folder: str) -> None:
        self._folders.open(folder)

    def choose(self) -> str | None:
        return self._window.choose_folder()

    def bring_to_front(self) -> None:
        if self._controller.state()["playing"] is None:  # while mpv plays, it is the front
            self._window.bring_to_front()

    def integrate(self, install: bool) -> None:
        if install and sys.platform == "win32":
            from nanar.desktop import integration

            integration.install(Path(sys.executable))
        self._settings.integration_answered = True
        self._settings.save(self._settings_path)


class _LazyDesktop:
    """The desktop, once the window exists (the API is made before it)."""

    def __init__(self, holder: list[Desktop]) -> None:
        self._holder = holder

    def _desktop(self) -> Desktop:
        if not self._holder:
            raise CommandError("no_window")
        return self._holder[0]

    def open(self, folder: str) -> None:
        self._desktop().open(folder)

    def choose(self) -> str | None:
        return self._desktop().choose()

    def bring_to_front(self) -> None:
        self._desktop().bring_to_front()

    def integrate(self, install: bool) -> None:
        self._desktop().integrate(install)


def offers_integration(settings: Settings) -> bool:
    """The Windows build, the first time (or after moving it): offer the Start menu entry and
    the folders' right-click entry. Running from the sources, never."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    from nanar.desktop import integration

    if integration.is_installed(Path(sys.executable)):
        return False
    # Said yes before, but the menus are gone or point to where Nanar was: offer again. A "no",
    # or `--uninstall`, leaves no Start menu entry behind, and is not asked again.
    return not settings.integration_answered or integration.start_menu_shortcut().is_file()


def remove_integration() -> None:
    """`--uninstall`: takes back what the offer on the TV page installed, and stops offering it.
    The rest is the unzipped folder and the data directory, which the user deletes."""
    settings_path = data_dir() / "settings.json"
    settings = Settings.load(settings_path)
    if sys.platform == "win32":
        from nanar.desktop import integration

        integration.uninstall()
    settings.integration_answered = True
    settings.save(settings_path)
    message = "Nanar n'est plus dans le menu Démarrer ni dans le clic droit sur les dossiers."
    print(message)
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        from nanar.desktop import win32

        win32.message_box("Nanar", message)


def check_parts() -> None:
    """For the release: the window's toolkit (.NET on Windows) and libmpv load, as they would
    when the window opens. A plain start can't tell: the server answers before the window."""
    from nanar.player import _load_mpv

    if sys.platform == "win32":
        # Loads .NET through pythonnet: what fails on DLLs marked as downloaded.
        importlib.import_module("webview.platforms.winforms")
    _load_mpv().MPV(vo="null", ao="null").terminate()
    print(f"Nanar {__version__}: window toolkit and libmpv load")


def port_taken(port: int) -> bool:
    """Whether something (often another Nanar) already answers on the port. Asking beats trying
    to bind it: on Windows a second bind may succeed and the server fail later, out of sight."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def hand_over(port: int, folder: Path | None) -> None:
    """Nanar is already open: hands it the folder (if any) and brings its window forward."""
    if sys.platform == "win32":
        from nanar.desktop import win32

        win32.allow_any_foreground()
    body = {"path": str(folder.expanduser().resolve()) if folder else None}
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/open",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except OSError:
        print(f"Le port {port} est pris par un autre programme que Nanar.")
        raise typer.Exit(1) from None


def main() -> None:
    # The Windows build has no console: what Nanar would print goes to a log file instead.
    if sys.stdout is None or sys.stderr is None:
        log = (data_dir() / "nanar.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    # The Windows console may not be UTF-8: never fail on an accented title.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    if sys.platform == "win32":
        from nanar.desktop import win32

        if getattr(sys, "frozen", False):
            # Unzipped from a download, the DLLs carry the Internet's mark, and .NET then
            # refuses them: unmark them before the window needs them.
            unmarked = win32.unblock_bundle(Path(getattr(sys, "_MEIPASS", ".")))
            if unmarked:
                print(f"{unmarked} DLL(s) unmarked as downloaded")
        win32.declare_dpi_aware()
        win32.declare_app_id()
    cli()


if __name__ == "__main__":  # the Windows build's entry point
    main()
