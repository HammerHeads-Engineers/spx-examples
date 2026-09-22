# SPDX-License-Identifier: MIT
"""Small, dependency-free helpers for installer network binding choices."""

from __future__ import annotations

import ipaddress
import argparse
import platform
import re
import socket
import subprocess
from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class IPv4Address:
    """An address that can be used as a host-side Docker bind address."""

    interface: str
    address: str


def _is_private_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return isinstance(address, ipaddress.IPv4Address) and any(
        address in ipaddress.ip_network(network)
        for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    )


def _normalise_candidates(candidates: Iterable[IPv4Address]) -> List[IPv4Address]:
    result: List[IPv4Address] = []
    seen: set[str] = set()
    for candidate in candidates:
        address = str(candidate.address).strip()
        if address in seen or not _is_private_ipv4(address):
            continue
        seen.add(address)
        result.append(IPv4Address(candidate.interface.strip() or "unknown", address))
    return sorted(result, key=lambda item: (item.address, item.interface))


def _run_command(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout or ""


def _parse_ip_output(output: str) -> List[IPv4Address]:
    candidates: List[IPv4Address] = []
    pattern = re.compile(
        r"^\s*\d+:\s+(?P<interface>\S+)\s+.*?\binet\s+"
        r"(?P<address>\d+\.\d+\.\d+\.\d+)/\d+",
        re.MULTILINE,
    )
    for match in pattern.finditer(output):
        candidates.append(IPv4Address(match.group("interface"), match.group("address")))
    return candidates


def _parse_ifconfig_output(output: str) -> List[IPv4Address]:
    candidates: List[IPv4Address] = []
    current_interface = "unknown"
    interface_pattern = re.compile(r"^([A-Za-z0-9_.:-]+):\s", re.MULTILINE)
    address_pattern = re.compile(r"\binet\s+(\d+\.\d+\.\d+\.\d+)")
    for line in output.splitlines():
        interface_match = interface_pattern.match(line)
        if interface_match:
            current_interface = interface_match.group(1)
        address_match = address_pattern.search(line)
        if address_match:
            candidates.append(IPv4Address(current_interface, address_match.group(1)))
    return candidates


def _parse_windows_ipconfig(output: str) -> List[IPv4Address]:
    candidates: List[IPv4Address] = []
    current_interface = "unknown"
    for line in output.splitlines():
        stripped = line.strip()
        adapter_match = re.match(r"^([^:]+adapter\s+[^:]+):$", stripped, re.IGNORECASE)
        if adapter_match:
            current_interface = adapter_match.group(1)
        match = re.search(r"IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", line)
        if match:
            candidates.append(IPv4Address(current_interface, match.group(1)))
    return candidates


def _socket_candidates() -> List[IPv4Address]:
    candidates: List[IPv4Address] = []
    try:
        hostnames = {socket.gethostname(), socket.getfqdn()}
        for hostname in hostnames:
            for entry in socket.getaddrinfo(hostname, None, socket.AF_INET):
                address = entry[4][0]
                candidates.append(IPv4Address("hostname", address))
    except OSError:
        pass
    return candidates


def discover_ipv4_addresses() -> List[IPv4Address]:
    """Return stable, private IPv4 candidates suitable for LAN binding."""

    system = platform.system().lower()
    candidates: List[IPv4Address] = []
    if system == "windows":
        candidates.extend(_parse_windows_ipconfig(_run_command(["ipconfig"])))
    else:
        candidates.extend(
            _parse_ip_output(_run_command(["ip", "-o", "-4", "addr", "show"]))
        )
        candidates.extend(_parse_ifconfig_output(_run_command(["ifconfig"])))
    candidates.extend(_socket_candidates())
    return _normalise_candidates(candidates)


def is_local_bind_address(
    address: str, candidates: Sequence[IPv4Address] | None = None
) -> bool:
    """Check that a configured non-loopback bind address is still assigned locally."""

    value = str(address).strip()
    if value in {"", "127.0.0.1", "localhost", "0.0.0.0", "::"}:
        return True
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    available = (
        list(candidates) if candidates is not None else discover_ipv4_addresses()
    )
    return any(item.address == value for item in available)


def _read_bindings(env_path: str) -> List[tuple[str, str]]:
    bindings: List[tuple[str, str]] = []
    try:
        with open(env_path, "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        raise SystemExit(f"Cannot read environment file {env_path}: {exc}") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.startswith("SPX_BIND_") or key == "BACNET_BIND_ADDR":
            bindings.append((key, value))
    return bindings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate SPX host network bind addresses."
    )
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args(argv)

    candidates = discover_ipv4_addresses()
    errors = [
        f"{key}={value} is not assigned to this host"
        for key, value in _read_bindings(args.env_file)
        if not is_local_bind_address(value, candidates)
    ]
    if errors:
        for error in errors:
            print(f"[spx-network] {error}")
        print(
            "[spx-network] Update the affected bind variable in .env or rerun the wizard."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
