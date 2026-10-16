"""Regression tests for the issues found during the October 2026 verification pass."""

import asyncio
import dataclasses
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main, netguard
from app.audit import accessibility, engine, fetch as fetch_module, pagespeed
from app.audit.fetch import FetchResult, _build_request, fetch
from app.netguard import UnsafeURLError, assert_public_url
from tests.test_analyzers import GOOD_HTML, make_page

# ---------- analyzers ----------

SHADOW_DOM_HTML = """<!DOCTYPE html><html lang="en"><head><title>Docs</title></head><body><main>
<nav-menu><template shadowrootmode="open">
  <a href="/de/"><!--lit-part-->Deutsch<!--/lit-part--></a>
  <button type="button"><!--lit-part-->OS default<!--/lit-part--></button>
</template></nav-menu>
</main></body></html>"""


def test_text_inside_template_counts_as_accessible_name():
    """Declarative shadow DOM (used by MDN) must not produce false 'no name' issues."""
    found = {i.id for i in accessibility.analyze(make_page(SHADOW_DOM_HTML)).issues}
    assert "link-name" not in found
    assert "button-name" not in found


# ---------- PageSpeed Insights ----------

LIGHTHOUSE_OK = {
    "lighthouseResult": {
        "categories": {
            "performance": {"score": 0.91}, "accessibility": {"score": 0.88},
            "seo": {"score": 1.0}, "best-practices": {"score": 0.96},
        },
        "audits": {
            "largest-contentful-paint": {"displayValue": "2.1 s", "score": 0.82},
            "cumulative-layout-shift": {"displayValue": "0.02", "score": 1},
        },
    }
}


def psi_with(monkeypatch, status: int, body: dict, key: str | None = "secret-test-key"):
    monkeypatch.setattr(pagespeed, "settings", dataclasses.replace(pagespeed.settings, pagespeed_api_key=key))
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await pagespeed.run("https://example.com/", client=client)

    return asyncio.run(go()), seen


def test_pagespeed_parses_lighthouse_scores_and_keeps_key_out_of_url(monkeypatch):
    result, seen = psi_with(monkeypatch, 200, LIGHTHOUSE_OK)
    assert result["error"] is None
    assert result["categories"] == {"performance": 91, "accessibility": 88, "seo": 100, "best-practices": 96}
    assert {m["label"] for m in result["metrics"]} == {"LCP", "CLS"}
    assert "secret-test-key" not in str(seen[0].url)
    assert seen[0].headers["x-goog-api-key"] == "secret-test-key"


@pytest.mark.parametrize("status,body,expected", [
    (429, {"error": {"message": "Quota exceeded"}}, "quota"),
    (400, {"error": {"message": "API key not valid. Please pass a valid API key."}}, "key was rejected"),
    (500, {"error": {"message": "boom"}}, "HTTP 500"),
    (200, {"lighthouseResult": {"categories": {}}}, "no scores"),
])
def test_pagespeed_failures_are_reported_not_hidden(monkeypatch, status, body, expected):
    result, _ = psi_with(monkeypatch, status, body)
    assert expected in result["error"]
    assert result["categories"] == {}


def test_pagespeed_disabled_without_key(monkeypatch):
    result, seen = psi_with(monkeypatch, 200, LIGHTHOUSE_OK, key=None)
    assert result is None and seen == []


# ---------- network guard ----------

def test_guard_returns_vetted_ip_and_blocks_non_web_ports():
    assert asyncio.run(assert_public_url("https://93.184.215.14/")) == "93.184.215.14"
    for url in ("http://93.184.215.14:22/", "http://93.184.215.14:6379/", "http://example.com:99999/"):
        with pytest.raises(UnsafeURLError):
            asyncio.run(assert_public_url(url))


def test_ipv4_mapped_ipv6_loopback_blocked():
    with pytest.raises(UnsafeURLError):
        asyncio.run(assert_public_url("http://[::ffff:127.0.0.1]/"))


def test_requests_connect_to_pinned_ip_but_keep_hostname():
    client = httpx.AsyncClient()
    request = _build_request(client, "GET", "https://example.com:8443/path?q=1", "93.184.215.14")
    assert str(request.url) == "https://93.184.215.14:8443/path?q=1"
    assert request.headers["host"] == "example.com:8443"
    assert request.extensions["sni_hostname"] == "example.com"
    asyncio.run(client.aclose())


def test_redirect_into_private_network_is_refused(monkeypatch):
    async def fake_guard(url: str):
        if "127.0.0.1" in url:
            raise UnsafeURLError("127.0.0.1 resolves to a private address and can't be audited.")
        return "93.184.215.14"

    monkeypatch.setattr(fetch_module, "assert_public_url", fake_guard)
    hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/admin"})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await fetch(client, "https://evil.example/")

    with pytest.raises(UnsafeURLError):
        asyncio.run(go())
    assert hits == ["https://93.184.215.14/"]  # the private target was never contacted


# ---------- engine ----------

def test_http_error_pages_are_not_scored(monkeypatch):
    async def fake_fetch(client, url, **kwargs):
        return FetchResult(url=url, status=500, headers=httpx.Headers({"content-type": "text/html"}), body=b"<html></html>")

    async def no_psi(url, client=None):
        return None

    async def progress(message):
        pass

    monkeypatch.setattr(engine, "fetch", fake_fetch)
    monkeypatch.setattr(pagespeed, "run", no_psi)
    with pytest.raises(engine.AuditError, match="HTTP 500"):
        asyncio.run(engine.run_audit("https://example.com/", progress))


# ---------- API ----------

@pytest.fixture
def api(monkeypatch):
    async def allow(url):
        return "93.184.215.14"

    monkeypatch.setattr(main, "assert_public_url", allow)
    return monkeypatch


def test_slow_audit_is_stopped_by_deadline(api):
    async def hang(url, progress):
        await asyncio.sleep(30)

    api.setattr(main, "run_audit", hang)
    api.setattr(main, "settings", dataclasses.replace(main.settings, audit_timeout=0.2))
    with TestClient(main.app) as client:
        audit_id = client.post("/api/audits", json={"url": "slow.example"}).json()["id"]
        detail = client.get(f"/api/audits/{audit_id}").json()
    assert detail["status"] == "failed"
    assert "took longer than" in detail["error"]


def test_pending_audit_cap_returns_429(api):
    api.setattr(main, "settings", dataclasses.replace(main.settings, max_pending_audits=0))
    with TestClient(main.app) as client:
        response = client.post("/api/audits", json={"url": "busy.example"})
    assert response.status_code == 429


def test_audits_survive_a_backend_restart(api):
    async def quick(url, progress):
        from tests.test_api import fake_run_audit
        return await fake_run_audit(url, progress)

    api.setattr(main, "run_audit", quick)
    with TestClient(main.app) as client:
        audit_id = client.post("/api/audits", json={"url": "persist.example"}).json()["id"]
    with TestClient(main.app) as client:  # a fresh app lifespan = a restart against the same database
        detail = client.get(f"/api/audits/{audit_id}").json()
    assert detail["status"] == "done"
    assert json.dumps(detail["report"]["scores"])
