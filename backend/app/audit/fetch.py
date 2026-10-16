import asyncio
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from ..config import settings
from ..netguard import UnsafeURLError, assert_public_url

MAX_REDIRECTS = 6


class FetchError(Exception):
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    headers: httpx.Headers
    body: bytes = b""
    redirects: list[str] = field(default_factory=list)
    ttfb_ms: float = 0.0
    total_ms: float = 0.0
    wire_bytes: int = 0
    truncated: bool = False


@dataclass
class ProbeResult:
    url: str
    status: int | None
    final_url: str | None = None
    redirected: bool = False
    content_type: str | None = None
    size: int | None = None
    cache_control: str | None = None
    expires: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and self.status < 400

    @property
    def blocked(self) -> bool:
        """Servers that refuse bots (401/403/429, LinkedIn's 999): not proof the link is broken."""
        return self.status in (401, 403, 429, 999)


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=False,  # followed manually so every hop is SSRF-checked
        timeout=httpx.Timeout(settings.request_timeout, connect=8.0),
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
        limits=httpx.Limits(max_connections=settings.probe_concurrency * 2),
    )


async def fetch(
    client: httpx.AsyncClient, url: str, *, method: str = "GET", read_body: bool = True
) -> FetchResult:
    redirects: list[str] = []
    current = url
    started = time.perf_counter()
    for _ in range(MAX_REDIRECTS + 1):
        pinned_ip = await assert_public_url(current)
        request = _build_request(client, method, current, pinned_ip)
        try:
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise FetchError(_describe_error(exc)) from exc
        ttfb = (time.perf_counter() - started) * 1000
        if response.is_redirect and "location" in response.headers:
            await response.aclose()
            redirects.append(current)
            current = urljoin(current, response.headers["location"])
            continue
        result = FetchResult(
            url=current,
            status=response.status_code,
            headers=response.headers,
            redirects=redirects,
            ttfb_ms=ttfb,
        )
        try:
            if read_body:
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > settings.max_page_bytes:
                        result.truncated = True
                        break
                result.body = b"".join(chunks)
                result.wire_bytes = response.num_bytes_downloaded
        except httpx.HTTPError as exc:
            raise FetchError(_describe_error(exc)) from exc
        finally:
            await response.aclose()
        result.total_ms = (time.perf_counter() - started) * 1000
        return result
    raise FetchError(f"Too many redirects (more than {MAX_REDIRECTS}).")


async def probe(client: httpx.AsyncClient, url: str) -> ProbeResult:
    """Check a URL without downloading it: HEAD, falling back to GET for servers that reject HEAD."""
    try:
        result = await fetch(client, url, method="HEAD", read_body=False)
        if result.status in (403, 404, 405, 501):
            result = await fetch(client, url, method="GET", read_body=False)
    except (FetchError, UnsafeURLError) as exc:
        return ProbeResult(url=url, status=None, error=str(exc))
    length = result.headers.get("content-length")
    return ProbeResult(
        url=url,
        status=result.status,
        final_url=result.url,
        redirected=bool(result.redirects),
        content_type=(result.headers.get("content-type") or "").split(";")[0].strip() or None,
        size=int(length) if length and length.isdigit() else None,
        cache_control=result.headers.get("cache-control"),
        expires=result.headers.get("expires"),
    )


async def probe_many(client: httpx.AsyncClient, urls: list[str]) -> dict[str, ProbeResult]:
    semaphore = asyncio.Semaphore(settings.probe_concurrency)

    async def run(u: str) -> ProbeResult:
        async with semaphore:
            return await probe(client, u)

    results = await asyncio.gather(*(run(u) for u in urls))
    return {r.url: r for r in results}


def _build_request(client: httpx.AsyncClient, method: str, url: str, ip: str | None) -> httpx.Request:
    """Build a request that connects to the vetted IP but still presents the real hostname.

    The Host header keeps virtual hosting working, and sni_hostname makes TLS send the real name
    and verify the certificate against it, so HTTPS security is unchanged.
    """
    if ip is None:
        return client.build_request(method, url)
    parts = urlsplit(url)
    host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{host}:{parts.port}" if parts.port else host
    pinned = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
    extensions = {"sni_hostname": parts.hostname} if parts.scheme == "https" else {}
    return client.build_request(
        method, pinned, headers={"Host": parts.netloc.rsplit("@", 1)[-1]}, extensions=extensions
    )


def _describe_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "The server took too long to respond."
    if isinstance(exc, httpx.ConnectError):
        if "CERTIFICATE" in str(exc).upper():
            return "The site's HTTPS certificate is invalid or expired, so browsers would show a security warning."
        return "Could not connect to the server."
    return f"Network error: {exc.__class__.__name__}"
