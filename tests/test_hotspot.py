from types import SimpleNamespace

from nanar.hotspot import Status, address, first, wifi_qr


def test_the_wifi_qr_code_escapes_what_its_scheme_reserves() -> None:
    assert wifi_qr("Nanar;PC", 'p:a"ss') == 'WIFI:T:WPA;S:Nanar\\;PC;P:p\\:a\\"ss;;'


def test_finds_the_address_phones_reach_on_the_hotspot() -> None:
    adapters = [
        SimpleNamespace(ips=[SimpleNamespace(ip="10.242.253.50")]),
        SimpleNamespace(
            ips=[SimpleNamespace(ip=("fe80::1", 0, 0)), SimpleNamespace(ip="192.168.137.1")]
        ),
    ]
    assert address(adapters) == "192.168.137.1"  # type: ignore[arg-type]
    assert address(adapters[:1]) is None  # type: ignore[arg-type]
    assert first(["10.0.0.2", "192.168.137.1"], "192.168.137.1") == ["192.168.137.1", "10.0.0.2"]
    assert first(["10.0.0.2"], None) == ["10.0.0.2"]


def test_phones_never_learn_the_password() -> None:
    status = Status(available=True, on=True, ssid="Nanar", passphrase="secret12")
    assert "secret12" not in str(status.public())
    assert Status(available=True, ssid="Nanar").public()["ssid"] is None  # off: not shown
