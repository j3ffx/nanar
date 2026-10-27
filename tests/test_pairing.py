import ipaddress
from pathlib import Path

from nanar.pairing import lan_addresses, load_key, remote_url
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
