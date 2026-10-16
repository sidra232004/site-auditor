import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

from ..config import settings
from ..netguard import UnsafeURLError
from . import accessibility, best_practices, design, links, pagespeed, performance, seo
from .fetch import FetchError, fetch, make_client, probe_many
from .page import Page, parse_page

ProgressCallback = Callable[[str], Awaitable[None]]

WEIGHTS = {
    "performance": 0.25,
    "accessibility": 0.20,
    "seo": 0.15,
    "best_practices": 0.15,
    "design": 0.15,
    "links": 0.10,
}


class AuditError(Exception):
    pass


async def run_audit(url: str, progress: ProgressCallback) -> dict[str, Any]:
    # Lighthouse runs in parallel with our own checks; it's cancelled however the audit ends.
    psi_task = asyncio.create_task(pagespeed.run(url))
    try:
        return await _audit(url, progress, psi_task)
    finally:
        if not psi_task.done():
            psi_task.cancel()


async def _audit(
    url: str, progress: ProgressCallback, psi_task: "asyncio.Task[dict[str, Any] | None]"
) -> dict[str, Any]:
    async with make_client() as client:
        await progress("Loading page")
        try:
            result = await fetch(client, url)
        except FetchError as exc:
            raise AuditError(str(exc)) from exc
        if result.status >= 400:
            kind = "server error" if result.status >= 500 else "error"
            raise AuditError(
                f"The site responded with HTTP {result.status} ({kind}), so there's no real page to audit."
            )
        content_type = result.headers.get("content-type", "")
        if "html" not in content_type and not result.body.lstrip()[:200].lower().startswith((b"<!doctype", b"<html")):
            raise AuditError(f"That URL returned {content_type or 'unknown content'}, not a web page.")

        await progress("Parsing HTML")
        page = parse_page(url, result)

        resource_urls = [r.url for r in page.resources[: settings.max_resources]]
        link_urls = page.links[: settings.max_links]
        extras = {
            "robots": urljoin(page.url, "/robots.txt"),
            "sitemap": urljoin(page.url, "/sitemap.xml"),
            "favicon": urljoin(page.url, "/favicon.ico"),
        }
        await progress(f"Checking {len(resource_urls)} resources and {len(link_urls)} links")
        targets = list(dict.fromkeys(resource_urls + link_urls + list(extras.values())))
        page.probes = await probe_many(client, targets)
        page.extras = {name: page.probes.get(u) for name, u in extras.items()}

        await progress("Reading stylesheets")
        page.stylesheets = await _fetch_stylesheets(client, page)

    await progress("Analysing results")
    metrics = performance.collect_metrics(page)
    design_info = design.collect(page)
    link_result, link_summary = links.analyze(page)
    categories = {
        "performance": performance.analyze(page, metrics),
        "accessibility": accessibility.analyze(page),
        "seo": seo.analyze(page),
        "best_practices": best_practices.analyze(page),
        "design": design.analyze(page, design_info),
        "links": link_result,
    }
    scores = {name: cat.score for name, cat in categories.items()}
    scores["overall"] = round(sum(scores[n] * w for n, w in WEIGHTS.items()))

    if not psi_task.done():
        await progress("Waiting for Google Lighthouse")
    psi = await psi_task

    soup = page.soup
    description = soup.find("meta", attrs={"name": "description"})
    return {
        "requested_url": url,
        "final_url": page.url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "status_code": result.status,
        "page": {
            "title": soup.title.get_text(strip=True) if soup.title else None,
            "description": description.get("content") if description else None,
            "server": result.headers.get("server"),
            "content_type": result.headers.get("content-type"),
            "truncated": result.truncated,
            "redirects": result.redirects,
        },
        "scores": scores,
        "metrics": metrics,
        "links": link_summary,
        "design": design_info,
        "categories": {name: cat.to_dict() for name, cat in categories.items()},
        "issue_counts": _issue_counts(categories),
        "pagespeed": psi,
    }


async def _fetch_stylesheets(client: httpx.AsyncClient, page: Page, limit: int = 4) -> list[str]:
    """Download the first few working stylesheets so design checks see the real fonts and colors."""
    urls = [
        r.url for r in page.resources
        if r.kind == "stylesheet" and (p := page.probes.get(r.url)) and p.ok
    ][:limit]

    async def get(url: str) -> str:
        try:
            result = await fetch(client, url)
        except (FetchError, UnsafeURLError):
            return ""
        return result.body.decode("utf-8", errors="replace") if result.status < 400 else ""

    return [css for css in await asyncio.gather(*(get(u) for u in urls)) if css]


def _issue_counts(categories: dict[str, Any]) -> dict[str, int]:
    counts = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    for cat in categories.values():
        for issue in cat.issues:
            counts[issue.severity] += 1
    return counts
