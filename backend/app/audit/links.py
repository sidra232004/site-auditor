from typing import Any

from .core import CategoryResult, Issue, truncate
from .page import Page


def analyze(page: Page) -> tuple[CategoryResult, dict[str, Any]]:
    items: list[dict[str, Any]] = []
    broken: list[dict[str, Any]] = []
    blocked = redirected = 0
    for url in page.links:
        probe = page.probes.get(url)
        if probe is None:
            continue
        state = "ok"
        if probe.blocked:
            state, blocked = "blocked", blocked + 1
        elif not probe.ok:
            state = "broken"
        elif probe.redirected:
            state, redirected = "redirect", redirected + 1
        item = {
            "url": url,
            "status": probe.status,
            "state": state,
            "internal": page.is_internal(url),
            "error": probe.error,
            "final_url": probe.final_url if probe.redirected else None,
        }
        items.append(item)
        if state == "broken":
            broken.append(item)

    broken_resources = [
        {"url": r.url, "kind": r.kind, "status": p.status, "error": p.error}
        for r in page.resources
        if (p := page.probes.get(r.url)) and not p.ok and not p.blocked
    ]

    issues: list[Issue] = []
    passed: list[str] = []
    if broken:
        internal = sum(1 for b in broken if b["internal"])
        issues.append(Issue(
            "broken-links", "critical" if len(broken) > 5 else "serious",
            f"{len(broken)} broken link{'s' if len(broken) != 1 else ''}",
            f"{internal} internal and {len(broken) - internal} external links lead to errors or dead pages, "
            "frustrating visitors and wasting search engines' crawl budget.",
            "Update or remove these links, or add redirects for moved pages.",
            count=len(broken),
            examples=[f"{b['status'] or b['error']} — {truncate(b['url'], 90)}" for b in broken[:8]],
        ))
    elif items:
        passed.append(f"All {len(items)} checked links work")

    if broken_resources:
        issues.append(Issue(
            "broken-resources", "serious", "Missing images, scripts or styles",
            "These files fail to load, so parts of the page may look or behave broken.",
            "Fix the paths or remove the references.",
            count=len(broken_resources),
            examples=[f"{r['status'] or r['error']} — {truncate(r['url'], 90)}" for r in broken_resources[:8]],
        ))
    elif page.resources:
        passed.append("All page resources load")

    if redirected >= 3:
        issues.append(Issue(
            "redirected-links", "minor", "Links pointing at redirects",
            "Each redirect adds a round trip before the visitor reaches the page.",
            "Update links to point at their final destination.",
            count=redirected,
            examples=[f"{truncate(i['url'], 60)} → {truncate(i['final_url'] or '', 60)}"
                      for i in items if i['state'] == 'redirect'][:5],
        ))

    score = 100 - min(60, len(broken) * 8) - min(40, len(broken_resources) * 10) - min(10, redirected)
    summary = {
        "found": len(page.links),
        "checked": len(items),
        "ok": sum(1 for i in items if i["state"] == "ok"),
        "redirect": redirected,
        "broken": len(broken),
        "blocked": blocked,
        "internal": sum(1 for i in items if i["internal"]),
        "external": sum(1 for i in items if not i["internal"]),
        "broken_resources": broken_resources,
        "items": sorted(items, key=lambda i: ["broken", "blocked", "redirect", "ok"].index(i["state"])),
    }
    return CategoryResult(max(0, score), issues, passed), summary
