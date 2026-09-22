# SPDX-License-Identifier: MIT
"""Tests for installer host network discovery and preflight validation."""

from __future__ import annotations

from pathlib import Path

from installer import network


def test_normalise_candidates_filters_non_lan_and_duplicates() -> None:
    candidates = network._normalise_candidates(
        [
            network.IPv4Address("lo", "127.0.0.1"),
            network.IPv4Address("link", "169.254.1.2"),
            network.IPv4Address("en0", "192.168.0.142"),
            network.IPv4Address("en0", "192.168.0.142"),
            network.IPv4Address("eth0", "10.0.0.15"),
            network.IPv4Address("public", "8.8.8.8"),
            network.IPv4Address("carrier", "100.64.0.1"),
        ]
    )

    assert candidates == [
        network.IPv4Address("eth0", "10.0.0.15"),
        network.IPv4Address("en0", "192.168.0.142"),
    ]


def test_is_private_ipv4_only_accepts_rfc1918_addresses() -> None:
    assert network._is_private_ipv4("192.168.0.142")
    assert not network._is_private_ipv4("8.8.8.8")
    assert not network._is_private_ipv4("100.64.0.1")


def test_parse_platform_outputs() -> None:
    linux = "2: en0    inet 192.168.0.142/24 brd 192.168.0.255 scope global"
    assert network._parse_ip_output(linux) == [
        network.IPv4Address("en0", "192.168.0.142")
    ]

    macos = "en0: flags=8863<UP>\n\tinet 10.0.0.15 netmask 0xffffff00"
    assert network._parse_ifconfig_output(macos) == [
        network.IPv4Address("en0", "10.0.0.15")
    ]

    windows = (
        "Ethernet adapter Wi-Fi:\n   IPv4 Address. . . . . . . . . . . : 172.16.0.20"
    )
    assert network._parse_windows_ipconfig(windows) == [
        network.IPv4Address("Ethernet adapter Wi-Fi", "172.16.0.20")
    ]


def test_network_preflight_accepts_local_and_rejects_missing_bind(
    tmp_path: Path, monkeypatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SPX_BIND_BACNET_GATEWAY=192.168.0.142\n" "SPX_BIND_MQTT_BROKER=127.0.0.1\n",
        encoding="utf-8",
    )
    candidates = [network.IPv4Address("en0", "192.168.0.142")]
    monkeypatch.setattr(network, "discover_ipv4_addresses", lambda: candidates)

    assert network.main(["--env-file", str(env_path)]) == 0

    env_path.write_text("SPX_BIND_BACNET_GATEWAY=10.10.10.10\n", encoding="utf-8")
    assert network.main(["--env-file", str(env_path)]) == 1
