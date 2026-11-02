"""Pairing phones: the key shown as a QR code on the TV, and the addresses phones can reach.

There is one key per installation. Anyone who scans the QR code on the TV can drive Nanar, which
is the point: whoever sits in front of the TV holds the remote. A new key (`nanar --new-key`)
unpairs every phone.
"""

import ipaddress
import os
import re
import secrets
import socket
from collections.abc import Iterable
from pathlib import Path

import ifaddr

KEY_FILE = "remote-key"


def load_key(directory: Path, *, renew: bool = False) -> str:
    """The pairing key, created the first time (or when renewed)."""
    path = directory / KEY_FILE
    if not renew:
        try:
            key = path.read_text(encoding="ascii").strip()
            if len(key) >= 16:
                return key
        except OSError:
            pass
    key = secrets.token_urlsafe(16)
    path.write_text(key + "\n", encoding="ascii")
    if os.name == "posix":
        path.chmod(0o600)
    return key


# Adapters no phone sits behind: virtual machines, containers, WSL, Bluetooth, VPN tunnels.
VIRTUAL_ADAPTERS = re.compile(
    r"hyper-v|vethernet|wsl|virtualbox|vmware|docker|bluetooth|loopback|tap-|tun\b|wintun|"
    r"wireguard|tailscale|nordlynx|zerotier|openvpn|anyconnect|forti|pangp|globalprotect|"
    r"protonvpn|mullvad|wan miniport",
    re.IGNORECASE,
)
# Windows' hotspot: its adapter keeps this address even while the hotspot is off, and a phone that
# was told about it would try in vain to reach Nanar there.
HOTSPOT_ADAPTERS = re.compile(r"wi-?fi direct", re.IGNORECASE)
HOTSPOT_NETWORK = ipaddress.IPv4Network("192.168.137.0/24")


def lan_addresses(*, hotspot: bool = False) -> list[str]:
    """This machine's IPv4 addresses that a phone may reach, the one of the default route first;
    its hotspot's only when it is open (`hotspot`). Read again on each call: the PC may change
    networks while Nanar runs."""
    primary: str | None = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # Connecting a UDP socket sends nothing: it only picks the outgoing interface.
            probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed anywhere
            primary = probe.getsockname()[0]
    except OSError:
        pass
    return usable_addresses(ifaddr.get_adapters(), primary, hotspot=hotspot)


def usable_addresses(
    adapters: Iterable[ifaddr.Adapter], primary: str | None, *, hotspot: bool
) -> list[str]:
    """The default route's address first, when it belongs to a real adapter: with a VPN, it is
    the tunnel's. If nothing else is left, it is all there is to offer."""
    found: list[str] = []
    for adapter in adapters:
        if VIRTUAL_ADAPTERS.search(adapter.nice_name):
            continue
        for ip in adapter.ips:
            if not isinstance(ip.ip, str) or ip.network_prefix == 32:  # 32: a tunnel's
                continue
            address = ipaddress.IPv4Address(ip.ip)
            if address.is_loopback or address.is_link_local or address.is_unspecified:
                continue
            is_hotspot = (
                HOTSPOT_ADAPTERS.search(adapter.nice_name) is not None or address in HOTSPOT_NETWORK
            )
            if is_hotspot and not hotspot:
                continue
            if ip.ip not in found:
                found.append(ip.ip)
    if primary in found:
        found = [primary, *(a for a in found if a != primary)]
    elif not found and primary and not ipaddress.IPv4Address(primary).is_loopback:
        found = [primary]
    return found


def remote_url(address: str, port: int, key: str) -> str:
    """What the QR code holds. The key is in the fragment, which browsers never send to a server
    (nor keep in a proxy's or a router's logs): the page reads it and pairs."""
    return f"http://{address}:{port}/#k={key}"
