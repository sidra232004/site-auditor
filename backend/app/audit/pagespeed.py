"""Optional enrichment with Google PageSpeed Insights (real Lighthouse lab data from Google's servers)."""

import logging
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger(__name__)
ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = ("performance", "accessibility", "seo", "best-practices")
AUDITS = {
    "first-contentful-paint": "FCP",
    "largest-contentful-paint": "LCP",
    "total-blocking-time": "TBT",
    "cumulative-layout-shift": "CLS",
    "speed-index": "Speed Index",
}


def _failure(message: str) -> dict[str, Any]:
    return {"strategy": "mobile", "error": message, "categories": {}, "metrics": []}


async def run(url: str, client: httpx.AsyncClient | None = None) -> dict[str, Any] | None:
    """Returns None when not configured, a dict with `error` when Google fails, else Lighthouse results."""
    if not settings.pagespeed_api_key:
        return None
    params = [("url", url), ("strategy", "mobile")] + [("category", c) for c in CATEGORIES]
    # The key travels in a header, never in the URL, so it can't leak into logs or error messages.
    headers = {"X-Goog-Api-Key": settings.pagespeed_api_key}
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=90)
    try:
        response = await client.get(ENDPOINT, params=params, headers=headers)
        data = response.json()
    except httpx.TimeoutException:
        return _failure("Google PageSpeed Insights timed out.")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("PageSpeed Insights request failed: %s", exc.__class__.__name__)
        return _failure("Could not reach Google PageSpeed Insights.")
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code != 200:
        message = (data.get("error") or {}).get("message", "") if isinstance(data, dict) else ""
        log.warning("PageSpeed Insights returned HTTP %s", response.status_code)
        if response.status_code == 429:
            return _failure("Google PageSpeed Insights daily quota is used up. Try again tomorrow.")
        if response.status_code in (400, 403) and "key" in message.lower():
            return _failure("The PageSpeed API key was rejected. Check PAGESPEED_API_KEY.")
        if response.status_code == 400:
            return _failure("Google Lighthouse could not load this page.")
        return _failure(f"Google PageSpeed Insights returned an error (HTTP {response.status_code}).")

    lighthouse = data.get("lighthouseResult", {})
    categories = {
        key: round(cat["score"] * 100)
        for key, cat in lighthouse.get("categories", {}).items()
        if isinstance(cat.get("score"), (int, float))
    }
    if not categories:
        return _failure("Google Lighthouse returned no scores for this page.")
    metrics = [
        {"id": audit_id, "label": label, "value": audit.get("displayValue"), "score": audit.get("score")}
        for audit_id, label in AUDITS.items()
        if (audit := lighthouse.get("audits", {}).get(audit_id))
    ]
    return {"strategy": "mobile", "error": None, "categories": categories, "metrics": metrics}
