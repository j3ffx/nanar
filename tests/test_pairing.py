import ipaddress
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from nanar.pairing import lan_addresses, load_key, remote_url, usable_addresses
from nanar.player import Track


def test_the_key_is_made_once_then_kept(tmp_path: Path) -> None:
    key = load_key(tmp_path)
    assert len(key) >= 16
    assert load_key(tmp_path) == key
    assert load_key(tmp_path, renew=True) != key


def test_the_key_travels_in_the_fragment() -> None:
    assert remote_url("192.168.1.10", 8642, "abc") == "http://192.168.1.10:8642/#k=abc"


def test_lists_only_addresses_a_phone_can_reach() -> None:
    for address in lan_addresses():
        ip = ipaddress.IPv4Address(address)
        assert not ip.is_loopback
        assert not ip.is_link_local


def test_tracks_are_named_in_french() -> None:
    def track(lang: str | None, title: str | None) -> str:
        return Track(id=3, kind="audio", lang=lang, title=title, selected=False).label

    assert track("fre", "VFF") == "Français (VFF)"
    assert track("eng", None) == "Anglais"
    assert track("fr", "Français") == "Français"
    assert track("tlh", None) == "tlh"
    assert track(None, "Commentaires") == "Commentaires"
    assert track(None, None) == "Piste 3"


def adapter(name: str, *addresses: str, prefix: int = 24) -> Any:
    ips = [SimpleNamespace(ip=a, network_prefix=prefix) for a in addresses]
    return SimpleNamespace(nice_name=name, ips=ips)


def test_a_closed_hotspot_keeps_its_address_but_no_phone_can_use_it() -> None:
    adapters = [
        adapter("Microsoft Wi-Fi Direct Virtual Adapter #2", "192.168.137.1"),
        adapter("Intel(R) Wi-Fi 6 AX201 160MHz", "10.0.0.5"),
    ]
    assert usable_addresses(adapters, "10.0.0.5", hotspot=False) == ["10.0.0.5"]
    assert usable_addresses(adapters, "10.0.0.5", hotspot=True) == ["10.0.0.5", "192.168.137.1"]


def test_a_vpn_never_reaches_the_qr_code_even_as_the_default_route() -> None:
    adapters = [
        adapter("WireGuard Tunnel", "10.8.0.2"),
        adapter("Tailscale Tunnel", "100.64.1.2", prefix=32),
        adapter("Realtek PCIe GbE", "192.168.1.20"),
    ]
    assert usable_addresses(adapters, "10.8.0.2", hotspot=False) == ["192.168.1.20"]


def test_the_default_route_comes_first_and_stays_when_nothing_else_is_left() -> None:
    adapters = [adapter("Ethernet", "192.168.56.1"), adapter("Wi-Fi", "192.168.1.20")]
    assert usable_addresses(adapters, "192.168.1.20", hotspot=False)[0] == "192.168.1.20"
    assert usable_addresses([], "10.0.0.5", hotspot=False) == ["10.0.0.5"]
