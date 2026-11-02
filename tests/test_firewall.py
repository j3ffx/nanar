from typing import Any

import pytest

from nanar.firewall import blocked_network


def rule(profile: str, action: str = "Allow") -> dict[str, str]:
    return {"action": action, "profile": profile}


@pytest.mark.parametrize(
    ("report", "blocked"),
    [
        # Allowed on the hotel's Wi-Fi only, and now at home: the case Windows doesn't ask about.
        ({"networks": ["Private"], "rules": [rule("Public")]}, "Private"),
        ({"networks": ["Public"], "rules": [rule("Public")]}, None),
        ({"networks": ["Private"], "rules": [rule("Private, Public")]}, None),
        ({"networks": ["Private"], "rules": [rule("Any")]}, None),
        ({"networks": ["DomainAuthenticated"], "rules": [rule("Public")]}, "Domain"),
        # A rule that blocks wins, as for Windows ("Annuler" on its question writes one).
        ({"networks": ["Public"], "rules": [rule("Any"), rule("Public", "Block")]}, "Public"),
        # Windows asks by itself about a program it has no rule for.
        ({"networks": ["Private"], "rules": []}, None),
        # That firewall is off.
        ({"networks": ["Private"], "off": ["Private"], "rules": [rule("Public")]}, None),
        # One network is enough to keep a phone out.
        ({"networks": ["Public", "Private"], "rules": [rule("Public")]}, "Private"),
        # Nothing read: nothing said.
        ({}, None),
    ],
)
def test_says_which_network_keeps_the_phones_out(report: dict[str, Any], blocked: str) -> None:
    assert blocked_network(report) == blocked
