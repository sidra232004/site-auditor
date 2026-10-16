"""Parsed page plus everything discovered on it, shared by all analyzers."""

from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from .fetch import FetchResult, ProbeResult

SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "#")


@dataclass
class Resource:
    url: str
    kind: str  # script | stylesheet | image | other


@dataclass
class Page:
    requested_url: str
    fetch: FetchResult
    soup: BeautifulSoup
    html: str
    resources: list[Resource] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    probes: dict[str, ProbeResult] = field(default_factory=dict)
    stylesheets: list[str] = field(default_factory=list)  # bodies of the first few external CSS files
    # robots.txt, sitemap.xml and favicon.ico probes (None when not checked)
    extras: dict[str, ProbeResult | None] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return self.fetch.url

    @property
    def headers(self) -> httpx.Headers:
        return self.fetch.headers

    @property
    def is_https(self) -> bool:
        return self.url.startswith("https://")

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""

    def is_internal(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return host.removeprefix("www.") == self.host.removeprefix("www.")


def parse_page(requested_url: str, result: FetchResult) -> Page:
    html = result.body.decode(_detect_encoding(result), errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    page = Page(requested_url=requested_url, fetch=result, soup=soup, html=html)
    base_tag = soup.find("base", href=True)
    base = urljoin(result.url, base_tag["href"]) if base_tag else result.url
    page.resources = _discover_resources(soup, base)
    page.links = _discover_links(soup, base)
    return page


def _detect_encoding(result: FetchResult) -> str:
    content_type = result.headers.get("content-type", "")
    if "charset=" in content_type:
        charset = content_type.split("charset=")[-1].split(";")[0].strip().strip("\"'")
        try:
            "".encode(charset)
            return charset
        except LookupError:
            pass
    return "utf-8"


def _absolute(base: str, value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value or value.lower().startswith(SKIP_SCHEMES):
        return None
    url = urldefrag(urljoin(base, value))[0]
    return url if url.startswith(("http://", "https://")) else None


def _discover_resources(soup: BeautifulSoup, base: str) -> list[Resource]:
    found: dict[str, Resource] = {}

    def add(value: str | None, kind: str) -> None:
        url = _absolute(base, value)
        if url and url not in found:
            found[url] = Resource(url, kind)

    for tag in soup.find_all("script", src=True):
        add(tag["src"], "script")
    for tag in soup.find_all("link", href=True):
        rel = {r.lower() for r in tag.get("rel", [])}
        if "stylesheet" in rel:
            add(tag["href"], "stylesheet")
        elif rel & {"icon", "apple-touch-icon"}:
            add(tag["href"], "image")
    for tag in soup.find_all("img"):
        src = tag.get("src") or tag.get("data-src")
        if not src and tag.get("srcset"):
            src = tag["srcset"].split(",")[0].split()[0]
        add(src, "image")
    for tag in soup.find_all(["video", "audio", "source"], src=True):
        add(tag["src"], "other")
    return list(found.values())


def _discover_links(soup: BeautifulSoup, base: str) -> list[str]:
    seen: dict[str, None] = {}
    for tag in soup.find_all("a", href=True):
        url = _absolute(base, tag["href"])
        if url:
            seen.setdefault(url, None)
    return list(seen)
