"""Transport-level guards shared by the HTTP servers."""
from __future__ import annotations

import ipaddress
from typing import Optional

from fastapi import Request


def is_loopback(host: Optional[str]) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_local_request(request: Request) -> bool:
    return is_loopback(request.client.host if request.client else None)


def is_insecure_remote_request(request: Request) -> bool:
    """True for plain-HTTP requests from another machine. Traffic from a
    TLS-terminating reverse proxy/tunnel on this host arrives from loopback
    (or, with uvicorn --proxy-headers, carries scheme=https) and is allowed."""
    return not is_local_request(request) and request.url.scheme != "https"
