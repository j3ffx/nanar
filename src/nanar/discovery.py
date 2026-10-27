"""`nanar.local`: one name for the remote, whatever the network.

The PC's address changes with the Wi-Fi (home, a hotel, a phone's hotspot), and with it the
remote's URL, the icon on the phone's home screen and its pairing (a cookie belongs to one
address). Nanar announces itself on the local network under a fixed name (multicast DNS, as
printers and AirPlay do): `http://nanar.local:8642` reaches it on any network where the phone can
resolve such names (iPhones always; Android depending on its version). The QR code keeps the IP
address as the way in that always works; the page then moves to the name when it answers.
"""

import logging
import socket
import threading
from collections.abc import Callable

from zeroconf import IPVersion, ServiceInfo, Zeroconf

HOST = "nanar.local"
SERVICE = "_http._tcp.local."
REFRESH_SECONDS = 15  # how soon a change of network is announced

log = logging.getLogger(__name__)


class Announcer:
    def __init__(self, port: int, addresses: Callable[[], list[str]]) -> None:
        self._port = port
        self._addresses = addresses
        self._zeroconf: Zeroconf | None = None
        self._info: ServiceInfo | None = None
        self._announced: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        except OSError as error:  # port 5353 unavailable: the IP address still works
            log.warning("mDNS unavailable, no %s: %s", HOST, error)
            return
        self._refresh()
        self._thread = threading.Thread(target=self._watch, name="nanar-mdns", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._zeroconf is None:
            return
        if self._info is not None:
            self._zeroconf.unregister_service(self._info)
        self._zeroconf.close()
        self._zeroconf = None

    @property
    def active(self) -> bool:
        return self._zeroconf is not None and self._info is not None

    def _watch(self) -> None:
        while not self._stop.wait(REFRESH_SECONDS):
            try:
                self._refresh()
            except Exception:  # never let the remote's name take Nanar down
                log.exception("mDNS refresh failed")

    def _refresh(self) -> None:
        addresses = self._addresses()
        if not addresses or addresses == self._announced or self._zeroconf is None:
            return
        info = ServiceInfo(
            SERVICE,
            f"Nanar.{SERVICE}",
            port=self._port,
            addresses=[socket.inet_aton(a) for a in addresses],
            server=f"{HOST}.",
            properties={"path": "/"},
        )
        if self._info is None:
            self._zeroconf.register_service(info, allow_name_change=True)
        else:
            self._zeroconf.update_service(info)
        self._info = info
        self._announced = addresses
