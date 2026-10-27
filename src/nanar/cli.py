"""`nanar [FOLDER]`: opens Nanar on a folder of videos (the last one when none is given)."""

import socket
import sys
import threading
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from nanar import __version__
from nanar.config import DEFAULT_PORT, Settings, data_dir

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
    version: Annotated[bool, typer.Option("--version", help="Affiche la version.")] = False,
) -> None:
    """Nanar : tes films sur la télé, la télécommande dans le téléphone."""
    if version:
        print(f"Nanar {__version__}")
        return

    from nanar import demo as demo_library
    from nanar.app import Network, create_app
    from nanar.controller import Controller
    from nanar.discovery import HOST, Announcer
    from nanar.library import scan
    from nanar.pairing import load_key
    from nanar.player import MpvSession
    from nanar.progress import Progress
    from nanar.thumbnails import Thumbnails
    from nanar.watcher import FolderWatcher

    settings_path = data_dir(demo=demo) / "settings.json"
    settings = Settings.load(settings_path)
    if demo:
        library = demo_library.library()
    else:
        chosen = folder or (Path(settings.last_folder) if settings.last_folder else None)
        if chosen is None:
            raise typer.BadParameter("indique le dossier de tes vidéos : nanar D:\\Films")
        chosen = chosen.expanduser().resolve()
        if not chosen.is_dir():
            raise typer.BadParameter(f"{chosen} n'est pas un dossier")
        settings.last_folder = str(chosen)
        settings.save(settings_path)
        library = scan(chosen)
    print(f"Nanar {__version__} : {len(library.videos)} vidéo(s) dans {library.root}")
    if port_taken(port):
        print(f"Nanar est déjà ouvert (le port {port} est pris) : ferme l'autre fenêtre d'abord.")
        raise typer.Exit(1)

    # One key for the demo and the real library: a phone paired once stays paired.
    key = load_key(data_dir(), renew=new_key)
    network = Network(port=port, lan=not local)
    announcer = Announcer(port, network.addresses)
    if network.lan:
        announcer.start()
        network.name = lambda: HOST if announcer.active else None
        addresses = ", ".join(f"http://{a}:{port}" for a in network.addresses())
        print(f"Télécommande : scanne le QR code sur la télé ({addresses or 'aucun réseau'})")

    progress = Progress(data_dir(demo=demo) / "progress.db")
    controller = Controller(
        library, settings, settings_path, MpvSession, progress=progress, demo=demo
    )
    thumbnails = Thumbnails(data_dir(demo=demo) / "thumbnails", on_ready=controller.library_changed)
    controller.thumbnails = thumbnails
    thumbnails.schedule(library)
    watcher = None if demo else FolderWatcher(Path(library.root), controller.set_library)
    if watcher is not None:
        watcher.start()
    app = create_app(controller, key=key, network=network)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1" if local else "0.0.0.0", port=port, log_level="warning"
        )
    )
    if headless:
        try:
            server.run()
        finally:
            controller.shutdown()
            thumbnails.stop()
            if watcher is not None:
                watcher.stop()
            announcer.stop()
        return

    from nanar.desktop.window import TvWindow

    page = "http://localhost:5173/tv" if dev else f"http://127.0.0.1:{port}/tv"
    window = TvWindow(page, fullscreen=settings.fullscreen)
    controller.window = window
    thread = threading.Thread(target=server.run, name="nanar-server", daemon=True)
    thread.start()
    try:
        window.run()  # until the window is closed
    finally:
        controller.shutdown()
        thumbnails.stop()
        if watcher is not None:
            watcher.stop()
        announcer.stop()
        server.should_exit = True
        thread.join(timeout=5)


def port_taken(port: int) -> bool:
    """Whether something (often another Nanar) already answers on the port. Asking beats trying
    to bind it: on Windows a second bind may succeed and the server fail later, out of sight."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    # The Windows console may not be UTF-8: never fail on an accented title.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    if sys.platform == "win32":
        from nanar.desktop import win32

        win32.declare_dpi_aware()
        win32.declare_app_id()
    cli()
