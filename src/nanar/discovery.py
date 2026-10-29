"""`nanar.local`: one name for the remote, whatever the network.

The PC's address changes with the Wi-Fi (home, a hotel, a phone's hotspot), and with it the
remote's URL, the icon on the phone's home screen and its pairing (a cookie belongs to one
address). Nanar announces itself on the local network under a fixed name (multicast DNS, as
printers and AirPlay do): `http://nanar.local:8642` reaches it on any network where the phone can
resolve such names (iPhones always; Android depending on its version). The QR code keeps the IP
address as the way in that always works; the page then moves to the name when it answers.

A Wi-Fi that drops and comes back (a hotel's, between its access points) can leave the announcer
deaf with the same address: Nanar asks for its own name now and then, as a phone would, and
announces it afresh when nothing answers.
"""

import logging
import secrets
import socket
import struct
import threading
from collections.abc import Callable

from zeroconf import IPVersion, ServiceInfo, Zeroconf

HOST = "nanar.local"
SERVICE = "_http._tcp.local."
REFRESH_SECONDS = 15  # how soon a change of network is announced, and the name checked
DEAF_AFTER = 2  # checks unanswered in a row before announcing afresh
MDNS = ("224.0.0.251", 5353)

log = logging.getLogger(__name__)


def answers(address: str, host: str = HOST, timeout: float = 2.0) -> bool:
    """Whether `host` is answered on the network of `address` (one of this machine's), asked as
    a phone asks: a multicast query from an ordinary port, which mDNS answers to that port
    directly (RFC 6762, 6.7)."""
    ident = secrets.token_bytes(2)
    name = b"".join(bytes([len(label)]) + label.encode() for label in host.split(".")) + b"\0"
    query = ident + struct.pack("!HHHHH", 0, 1, 0, 0, 0) + name + struct.pack("!HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.settimeout(timeout)
        try:
            probe.bind((address, 0))
            probe.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(address))
            probe.sendto(query, MDNS)
            while True:
                reply = probe.recv(9000)
                if reply[:2] == ident and len(reply) >= 12 and struct.unpack("!H", reply[6:8])[0]:
                    return True
        except OSError:  # timed out, or this address is gone
            return False


def _zeroconf() -> Zeroconf:
    return Zeroconf(ip_version=IPVersion.V4Only)


class Announcer:
    def __init__(
        self,
        port: int,
        addresses: Callable[[], list[str]],
        *,
        probe: Callable[[str], bool] = answers,
        make: Callable[[], Zeroconf] = _zeroconf,
    ) -> None:
        self._port = port
        self._addresses = addresses
        self._probe = probe
        self._make = make
        self._unanswered = 0
        self._zeroconf: Zeroconf | None = None
        self._info: ServiceInfo | None = None
        self._announced: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        try:
            self._zeroconf = self._make()
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
                self._check()
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

    def _check(self) -> None:
        """Asks for the name on each network it is announced on; announces it afresh when one
        of them has stopped answering."""
        if not self.active:
            return
        if all(self._probe(address) for address in self._announced):
            self._unanswered = 0
            return
        self._unanswered += 1
        if self._unanswered < DEAF_AFTER:
            return
        log.warning("%s no longer answered: announcing it afresh", HOST)
        self._unanswered = 0
        deaf, self._zeroconf = self._zeroconf, None
        if deaf is not None:
            deaf.close()
        self._info = None
        self._announced = []
        self._zeroconf = self._make()
        self._refresh()
