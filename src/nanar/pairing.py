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


# Adapters no phone sits behind: virtual machines, containers, WSL, Bluetooth.
VIRTUAL_ADAPTERS = re.compile(
    r"hyper-v|vethernet|wsl|virtualbox|vmware|docker|bluetooth|loopback|tap-windows|wintun",
    re.IGNORECASE,
)


def lan_addresses() -> list[str]:
    """This machine's IPv4 addresses that a phone on the same network may reach, the one of the
    default route first. Read again on each call: the PC may change networks while Nanar runs."""
    primary: str | None = None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            # Connecting a UDP socket sends nothing: it only picks the outgoing interface.
            probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed anywhere
            primary = probe.getsockname()[0]
    except OSError:
        pass
    found = [primary] if primary else []
    for adapter in ifaddr.get_adapters():
        if VIRTUAL_ADAPTERS.search(adapter.nice_name):
            continue
        found += [ip.ip for ip in adapter.ips if isinstance(ip.ip, str)]
    usable = []
    for address in found:
        ip = ipaddress.IPv4Address(address)
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or address in usable:
            continue
        usable.append(address)
    return usable


def remote_url(address: str, port: int, key: str) -> str:
    """What the QR code holds. The key is in the fragment, which browsers never send to a server
    (nor keep in a proxy's or a router's logs): the page reads it and pairs."""
    return f"http://{address}:{port}/#k={key}"
