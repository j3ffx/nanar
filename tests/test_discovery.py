import socket
from typing import Any

from zeroconf import ServiceInfo

from nanar import discovery
from nanar.discovery import Announcer, answers
from nanar.pairing import lan_addresses


class FakeZeroconf:
    def __init__(self) -> None:
        self.registered: list[Any] = []
        self.closed = False

    def register_service(self, info: Any, allow_name_change: bool = False) -> None:
        self.registered.append(info)

    def update_service(self, info: Any) -> None:
        self.registered.append(info)

    def unregister_service(self, info: Any) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_announces_afresh_once_the_name_stopped_answering() -> None:
    made: list[FakeZeroconf] = []
    heard = [True]

    def make() -> Any:
        made.append(FakeZeroconf())
        return made[-1]

    announcer = Announcer(8642, lambda: ["192.168.1.10"], probe=lambda _: heard[0], make=make)
    announcer.start()  # its own checks wait 15 s: the ones below come first
    try:
        announcer._check()
        assert len(made) == 1  # answered: nothing to do
        heard[0] = False
        announcer._check()
        assert len(made) == 1  # once is not enough (a lost packet)
        announcer._check()
        assert len(made) == 2
        assert made[0].closed
        assert announcer.active
        assert made[1].registered  # announced again, on the same address
    finally:
        announcer.stop()


def test_one_network_still_answering_is_no_reason_to_start_over() -> None:
    made: list[FakeZeroconf] = []

    def make() -> Any:
        made.append(FakeZeroconf())
        return made[-1]

    announcer = Announcer(
        8642, lambda: ["192.168.1.10", "10.0.0.5"], probe=lambda a: a == "10.0.0.5", make=make
    )
    announcer.start()
    try:
        announcer._check()
        announcer._check()
        assert len(made) == 1
    finally:
        announcer.stop()


def test_another_network_gets_a_new_announcement_on_new_sockets() -> None:
    made: list[FakeZeroconf] = []
    addresses = ["192.168.1.10"]

    def make() -> Any:
        made.append(FakeZeroconf())
        return made[-1]

    announcer = Announcer(8642, lambda: list(addresses), probe=lambda _: True, make=make)
    announcer.start()
    try:
        addresses[0] = "10.0.0.5"
        announcer._refresh()
        assert len(made) == 2
        assert made[0].closed
        assert announcer.active
    finally:
        announcer.stop()


def test_a_failed_new_start_is_tried_again() -> None:
    made: list[FakeZeroconf] = []
    broken = [False]

    def make() -> Any:
        if broken[0]:
            raise OSError("port taken")
        made.append(FakeZeroconf())
        return made[-1]

    announcer = Announcer(8642, lambda: ["192.168.1.10"], probe=lambda _: False, make=make)
    announcer.start()
    try:
        broken[0] = True
        announcer._check()
        announcer._check()
        assert not announcer.active
        broken[0] = False
        announcer._refresh()
        assert announcer.active
    finally:
        announcer.stop()


def test_asks_for_a_name_as_a_phone_would() -> None:
    addresses = lan_addresses()
    if not addresses:
        return  # no network here (CI may have none that carries multicast)
    zeroconf = discovery._zeroconf()
    info = ServiceInfo(
        discovery.SERVICE,
        f"NanarTest.{discovery.SERVICE}",
        port=8659,
        addresses=[socket.inet_aton(a) for a in addresses],
        server="nanar-probe-test.local.",
    )
    try:
        zeroconf.register_service(info, allow_name_change=True)
        if not answers(addresses[0], "nanar-probe-test.local"):
            return  # this network drops multicast: nothing to learn here
        assert not answers(addresses[0], "nanar-absent-test.local", timeout=0.5)
    finally:
        zeroconf.unregister_service(info)
        zeroconf.close()
