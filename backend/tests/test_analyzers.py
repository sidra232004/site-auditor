import asyncio

import httpx
import pytest

from app.audit import accessibility, best_practices, design, links, performance, seo
from app.audit.colors import contrast_ratio, extract_colors, parse_color
from app.audit.fetch import FetchResult, ProbeResult
from app.audit.page import parse_page
from app.netguard import UnsafeURLError, assert_public_url, normalize_url

BAD_HTML = """
<html><head>
  <script src="/js/jquery-1.12.4.min.js"></script>
  <meta name="viewport" content="width=device-width, user-scalable=no">
</head><body>
  <h1>Welcome</h1><h3>Skipped</h3>
  <img src="/hero.jpg">
  <a href="/about"></a>
  <a href="/contact">click here</a>
  <a href="https://other.example/dead">Partner</a>
  <button><i class="icon"></i></button>
  <input type="email" placeholder="Email">
  <p style="color:#999;background:#aaa">Faint text</p>
  <center>Lorem ipsum dolor sit amet</center>
  <footer>© 2015 Acme</footer>
</body></html>
"""

GOOD_HTML = """<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acme Plumbing — 24/7 emergency plumbers in Leeds</title>
  <meta name="description" content="Fast, friendly, fully-insured plumbers serving Leeds since 1998. Call now for same-day repairs, boiler servicing and free quotes.">
  <link rel="canonical" href="https://acme.example/">
  <link rel="icon" href="/favicon.svg">
  <meta property="og:title" content="Acme"><meta property="og:description" content="x"><meta property="og:image" content="/og.png">
  <script type="application/ld+json">{}</script>
  <script src="/app.js" defer></script>
</head><body><main>
  <h1>Emergency plumbers</h1><h2>Services</h2>
  <img src="/van.webp" alt="Our van" width="400" height="300">
  <label for="e">Email</label><input id="e" type="email">
  <button class="btn">Get a quote</button>
  <p>""" + ("word " * 300) + """</p>
</main></body></html>"""


def make_page(html: str, url: str = "https://acme.example/", headers: dict | None = None):
    result = FetchResult(
        url=url, status=200, headers=httpx.Headers(headers or {"content-type": "text/html"}),
        body=html.encode(), ttfb_ms=200, total_ms=400, wire_bytes=len(html),
    )
    return parse_page(url, result)


def ids(result) -> set[str]:
    return {i.id for i in result.issues}


def test_accessibility_flags_common_failures():
    found = ids(accessibility.analyze(make_page(BAD_HTML)))
    assert {"html-lang", "document-title", "image-alt", "form-label", "button-name",
            "link-name", "vague-links", "heading-order", "zoom-disabled", "landmark-main",
            "color-contrast"} <= found


def test_accessibility_clean_page_scores_100():
    result = accessibility.analyze(make_page(GOOD_HTML))
    assert result.issues == []
    assert result.score == 100


def test_seo_checks():
    assert {"title-missing", "meta-description", "canonical", "thin-content"} <= ids(seo.analyze(make_page(BAD_HTML)))
    assert seo.analyze(make_page(GOOD_HTML)).score == 100


def test_noindex_is_critical():
    page = make_page(GOOD_HTML.replace("<head>", '<head><meta name="robots" content="noindex">'))
    issue = next(i for i in seo.analyze(page).issues if i.id == "noindex")
    assert issue.severity == "critical"


def test_best_practices_http_and_old_jquery():
    page = make_page(BAD_HTML, url="http://acme.example/")
    found = ids(best_practices.analyze(page))
    assert {"https", "vulnerable-library", "doctype", "csp"} <= found


def test_best_practices_secure_headers_pass():
    headers = {
        "content-type": "text/html; charset=utf-8",
        "strict-transport-security": "max-age=31536000",
        "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin",
    }
    assert best_practices.analyze(make_page(GOOD_HTML, headers=headers)).issues == []


def test_design_suggestions():
    page = make_page(BAD_HTML)
    found = ids(design.analyze(page, design.collect(page)))
    assert {"deprecated-html", "placeholder-text", "stale-copyright"} <= found
    good = make_page(GOOD_HTML)
    assert "not-responsive" not in ids(design.analyze(good, design.collect(good)))


def test_links_classifies_broken_blocked_and_redirects():
    page = make_page(BAD_HTML)
    page.probes = {
        "https://acme.example/about": ProbeResult("https://acme.example/about", 200),
        "https://acme.example/contact": ProbeResult("https://acme.example/contact", 200, redirected=True),
        "https://other.example/dead": ProbeResult("https://other.example/dead", 404),
        "https://acme.example/hero.jpg": ProbeResult("https://acme.example/hero.jpg", 404),
    }
    result, summary = links.analyze(page)
    assert summary["broken"] == 1 and summary["redirect"] == 1 and summary["ok"] == 1
    assert {"broken-links", "broken-resources"} <= ids(result)
    assert summary["items"][0]["state"] == "broken"

    page.probes["https://other.example/dead"] = ProbeResult("https://other.example/dead", 999)
    _, summary = links.analyze(page)
    assert summary["broken"] == 0 and summary["blocked"] == 1


def test_performance_metrics_and_render_blocking():
    page = make_page(BAD_HTML)
    page.probes = {"https://acme.example/hero.jpg": ProbeResult("https://acme.example/hero.jpg", 200, size=900_000)}
    metrics = performance.collect_metrics(page)
    assert metrics["request_count"] == 3
    found = ids(performance.analyze(page, metrics))
    assert {"render-blocking", "large-images", "unsized-images"} <= found


def test_colors():
    assert parse_color("#fff") == (255, 255, 255)
    assert parse_color("rgb(0, 0, 0)") == (0, 0, 0)
    assert round(contrast_ratio((0, 0, 0), (255, 255, 255))) == 21
    assert extract_colors("a{color:#FFF} b{color:#ffffff;background:rgb(1,2,3)}")[0] == "#ffffff"


@pytest.mark.parametrize("raw,expected", [
    ("example.com", "https://example.com/"),
    ("  HTTP://Example.com/path?q=1#frag ", "http://example.com/path?q=1"),
])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "ftp://example.com", "javascript:alert(1)", "https://user:pw@example.com", "nodot"])
def test_normalize_url_rejects(raw):
    with pytest.raises(UnsafeURLError):
        normalize_url(raw)


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.5/", "http://169.254.169.254/latest", "http://[::1]/"])
def test_private_targets_blocked(url):
    with pytest.raises(UnsafeURLError):
        asyncio.run(assert_public_url(url))
