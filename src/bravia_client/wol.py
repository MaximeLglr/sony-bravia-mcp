from __future__ import annotations

import socket

from .errors import BadRequest


def send_magic_packet(mac_hex: str) -> None:
    if len(mac_hex) != 12:
        raise BadRequest(f"Invalid MAC address: {mac_hex}")
    packet = b"\xff" * 6 + bytes.fromhex(mac_hex) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):
            sock.sendto(packet, ("255.255.255.255", port))
