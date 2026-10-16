import pytest
from fastapi.testclient import TestClient

from app import main
from tests.test_analyzers import GOOD_HTML

FAKE_REPORT_URL = "https://acme.example/"


async def fake_run_audit(url, progress):
    """Run the real analyzers over fixture HTML instead of hitting the network."""
    from app.audit import accessibility, best_practices, design, links, performance, seo
    from app.audit.engine import WEIGHTS, _issue_counts
    from tests.test_analyzers import make_page

    await progress("Analysing results")
    page = make_page(GOOD_HTML)
    metrics = performance.collect_metrics(page)
    info = design.collect(page)
    link_result, summary = links.analyze(page)
    cats = {
        "performance": performance.analyze(page, metrics),
        "accessibility": accessibility.analyze(page),
        "seo": seo.analyze(page),
        "best_practices": best_practices.analyze(page),
        "design": design.analyze(page, info),
        "links": link_result,
    }
    scores = {k: v.score for k, v in cats.items()}
    scores["overall"] = round(sum(scores[k] * w for k, w in WEIGHTS.items()))
    return {
        "requested_url": url, "final_url": FAKE_REPORT_URL, "fetched_at": "2026-10-15T10:00:00+00:00",
        "status_code": 200, "page": {}, "scores": scores, "metrics": metrics, "links": summary,
        "design": info, "categories": {k: v.to_dict() for k, v in cats.items()},
        "issue_counts": _issue_counts(cats), "pagespeed": None,
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "run_audit", fake_run_audit)

    async def allow(url):
        return None

    monkeypatch.setattr(main, "assert_public_url", allow)
    with TestClient(main.app) as c:
        yield c


def test_full_audit_lifecycle(client):
    created = client.post("/api/audits", json={"url": "acme.example"})
    assert created.status_code == 202
    audit_id = created.json()["id"]

    detail = client.get(f"/api/audits/{audit_id}").json()
    assert detail["status"] == "done"
    assert detail["report"]["scores"]["overall"] == detail["overall_score"]

    pdf = client.get(f"/api/audits/{audit_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    second = client.post("/api/audits", json={"url": "https://acme.example/two"}).json()["id"]
    rows = client.get(f"/api/compare?ids={audit_id},{second}").json()
    assert [r["id"] for r in rows] == [audit_id, second]
    assert "ttfb_ms" in rows[0]["metrics"]

    listed = client.get("/api/audits").json()
    assert any(a["id"] == audit_id for a in listed)
    assert listed[0]["created_at"].endswith(("Z", "+00:00"))
    assert client.delete(f"/api/audits/{audit_id}").status_code == 204
    assert client.get(f"/api/audits/{audit_id}").status_code == 404


def test_rejects_bad_url(client):
    assert client.post("/api/audits", json={"url": "ftp://nope.example"}).status_code == 422
