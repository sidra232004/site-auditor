import re
from typing import Any

from .page import Page
from .core import CategoryResult, Issue, linear_score, penalty_score, truncate

# (metric, good, poor, weight). Thresholds are measured from our server, so TTFB
# includes DNS + TLS setup and is more forgiving than a browser's TTFB.
METRICS: list[tuple[str, float, float, float]] = [
    ("ttfb_ms", 600, 2500, 0.30),
    ("load_ms", 1000, 5000, 0.20),
    ("page_weight_kb", 1500, 6000, 0.25),
    ("request_count", 40, 150, 0.15),
    ("dom_elements", 1000, 4000, 0.10),
]

LARGE_IMAGE_BYTES = 300 * 1024
MODERN_IMAGE = re.compile(r"\.(webp|avif)(\?|$)", re.I)
LEGACY_IMAGE = re.compile(r"\.(jpe?g|png|bmp|gif)(\?|$)", re.I)


def collect_metrics(page: Page) -> dict[str, Any]:
    breakdown: dict[str, dict[str, int]] = {}
    html_bytes = page.fetch.wire_bytes or len(page.fetch.body)
    breakdown["html"] = {"count": 1, "bytes": html_bytes}
    unknown_sizes = 0
    for res in page.resources:
        probe = page.probes.get(res.url)
        entry = breakdown.setdefault(res.kind, {"count": 0, "bytes": 0})
        entry["count"] += 1
        if probe and probe.size is not None:
            entry["bytes"] += probe.size
        else:
            unknown_sizes += 1
    weight = sum(e["bytes"] for e in breakdown.values())
    largest = sorted(
        (
            {"url": r.url, "kind": r.kind, "bytes": page.probes[r.url].size}
            for r in page.resources
            if r.url in page.probes and page.probes[r.url].size
        ),
        key=lambda r: r["bytes"],
        reverse=True,
    )[:8]
    return {
        "ttfb_ms": round(page.fetch.ttfb_ms),
        "load_ms": round(page.fetch.total_ms),
        "html_bytes": html_bytes,
        "html_uncompressed_bytes": len(page.fetch.body),
        "page_weight_kb": round(weight / 1024, 1),
        "request_count": 1 + len(page.resources),
        "dom_elements": len(page.soup.find_all(True)),
        "redirects": len(page.fetch.redirects),
        "unknown_sizes": unknown_sizes,
        "breakdown": [{"kind": k, **v} for k, v in breakdown.items()],
        "largest_resources": largest,
    }


def analyze(page: Page, metrics: dict[str, Any]) -> CategoryResult:
    issues: list[Issue] = []
    passed: list[str] = []

    metric_score = sum(
        linear_score(metrics[name], good, poor) * weight for name, good, poor, weight in METRICS
    )

    if metrics["ttfb_ms"] > 1500:
        issues.append(Issue(
            "slow-server", "serious", "Slow server response",
            f"The server took {metrics['ttfb_ms']} ms to start responding.",
            "Add server-side caching, use a CDN, or upgrade hosting. Aim for under 600 ms.",
        ))
    else:
        passed.append("Server responds quickly")

    if metrics["page_weight_kb"] > 3000:
        issues.append(Issue(
            "heavy-page", "serious", "Page is very heavy",
            f"Discovered resources total {metrics['page_weight_kb']:,.0f} KB.",
            "Compress images, remove unused scripts, and lazy-load below-the-fold content.",
        ))
    else:
        passed.append("Page weight is reasonable")

    if metrics["request_count"] > 80:
        issues.append(Issue(
            "many-requests", "moderate", "Too many requests",
            f"The page loads at least {metrics['request_count']} files.",
            "Bundle scripts and styles, use SVG sprites, and drop unused third-party tags.",
        ))

    encoding = page.headers.get("content-encoding", "")
    if len(page.fetch.body) > 2048 and not encoding:
        issues.append(Issue(
            "no-compression", "serious", "HTML is not compressed",
            "The server sends HTML uncompressed, so visitors download more data than needed.",
            "Enable gzip or Brotli compression on the web server or CDN.",
        ))
    else:
        passed.append("Text compression enabled")

    if metrics["redirects"] > 1:
        issues.append(Issue(
            "redirect-chain", "moderate", "Redirect chain before the page loads",
            f"The URL went through {metrics['redirects']} redirects: "
            + " → ".join(page.fetch.redirects + [page.url]),
            "Link directly to the final URL and collapse redirects into a single hop.",
        ))

    head = page.soup.head
    blocking = [
        s["src"] for s in (head.find_all("script", src=True) if head else [])
        if not s.has_attr("async") and not s.has_attr("defer") and s.get("type") != "module"
    ]
    if blocking:
        issues.append(Issue(
            "render-blocking", "moderate", "Render-blocking scripts",
            "Scripts in <head> without async or defer stop the page from rendering until they load.",
            "Add `defer` (or `async` for independent scripts) to these script tags.",
            count=len(blocking), examples=[truncate(b) for b in blocking[:5]],
        ))
    else:
        passed.append("No render-blocking scripts")

    images = page.soup.find_all("img")
    unsized = [i for i in images if not (i.get("width") and i.get("height"))]
    if unsized:
        issues.append(Issue(
            "unsized-images", "moderate", "Images without dimensions",
            "Images missing width and height cause the layout to jump as they load (CLS).",
            "Set width and height attributes (or CSS aspect-ratio) on every image.",
            count=len(unsized), examples=[truncate(i.get("src") or "") for i in unsized[:5]],
        ))

    not_lazy = [i for i in images[3:] if i.get("loading") != "lazy"]
    if len(not_lazy) >= 3:
        issues.append(Issue(
            "no-lazy-loading", "minor", "Offscreen images load eagerly",
            "Images further down the page download immediately, competing with visible content.",
            'Add loading="lazy" to images below the fold.',
            count=len(not_lazy), examples=[truncate(i.get("src") or "", 90) for i in not_lazy[:5]],
        ))

    large = [
        r for r in page.resources
        if r.kind == "image" and (p := page.probes.get(r.url)) and (p.size or 0) > LARGE_IMAGE_BYTES
    ]
    if large:
        issues.append(Issue(
            "large-images", "serious", "Oversized images",
            f"{len(large)} image(s) are larger than 300 KB.",
            "Resize to the displayed size and convert to WebP or AVIF.",
            count=len(large),
            examples=[f"{truncate(r.url, 90)} ({page.probes[r.url].size // 1024} KB)" for r in large[:5]],
        ))

    image_urls = [r.url for r in page.resources if r.kind == "image"]
    legacy = [u for u in image_urls if LEGACY_IMAGE.search(u)]
    if len(legacy) >= 4 and not any(MODERN_IMAGE.search(u) for u in image_urls):
        issues.append(Issue(
            "legacy-image-formats", "minor", "No modern image formats",
            "All images use JPEG/PNG/GIF, which are typically 25–50% larger than WebP or AVIF.",
            "Serve WebP or AVIF, with <picture> fallbacks if needed.",
            count=len(legacy), examples=[truncate(u, 90) for u in legacy[:5]],
        ))

    static = [
        r for r in page.resources
        if (p := page.probes.get(r.url)) and p.ok and not _is_cached(p.cache_control, p.expires)
    ]
    if len(static) >= 3:
        issues.append(Issue(
            "no-caching", "moderate", "Static files lack cache headers",
            "Returning visitors must re-download these files on every visit.",
            "Serve static assets with `Cache-Control: public, max-age=31536000, immutable` "
            "and fingerprinted filenames.",
            count=len(static), examples=[truncate(r.url, 90) for r in static[:5]],
        ))
    elif page.resources:
        passed.append("Static assets are cacheable")

    score = round(0.75 * metric_score + 0.25 * penalty_score(issues))
    return CategoryResult(score, issues, passed)


def _is_cached(cache_control: str | None, expires: str | None) -> bool:
    if cache_control:
        cc = cache_control.lower()
        if "no-store" in cc or "no-cache" in cc:
            return False
        match = re.search(r"max-age=(\d+)", cc)
        if match:
            return int(match.group(1)) >= 3600
    return bool(expires)
