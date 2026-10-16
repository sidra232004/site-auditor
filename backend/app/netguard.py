"""Guards against server-side request forgery: only public http(s) targets are fetched."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

from .config import settings


class UnsafeURLError(ValueError):
    pass


def normalize_url(raw: str) -> str:
    """Turn user input like 'example.com' into a canonical absolute URL."""
    value = raw.strip()
    if not value:
        raise UnsafeURLError("Please enter a URL.")
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http and https URLs can be audited.")
    if not parts.hostname or "." not in parts.hostname and parts.hostname != "localhost":
        raise UnsafeURLError("That doesn't look like a valid website address.")
    if parts.username or parts.password:
        raise UnsafeURLError("URLs with embedded credentials are not allowed.")
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))


# Only ports websites are normally served on, so the auditor can't be pointed at mail,
# database or SSH ports on public hosts.
ALLOWED_PORTS = frozenset({80, 443, 8000, 8008, 8080, 8443, 8888})


async def assert_public_url(url: str) -> str | None:
    """Validate a URL and return the vetted IP address the request must connect to.

    Returns None only when private targets are explicitly allowed (local development).
    Callers connect to the returned IP rather than resolving the name again, so a DNS
    server can't answer "public" for this check and "127.0.0.1" for the real request.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURLError(f"Refusing to fetch non-http URL: {url}")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeURLError("That URL has an invalid port number.") from exc
    if settings.allow_private_targets:
        return None
    if port not in ALLOWED_PORTS:
        raise UnsafeURLError(f"Port {port} isn't a web port and can't be audited.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, port, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve host {parts.hostname}") from exc
    addresses = [ipaddress.ip_address(str(info[4][0]).split("%", 1)[0]) for info in infos]
    for ip in addresses:
        if not ip.is_global:
            raise UnsafeURLError(f"{parts.hostname} resolves to a private address and can't be audited.")
    if not addresses:
        raise UnsafeURLError(f"Could not resolve host {parts.hostname}")
    return str(addresses[0])
