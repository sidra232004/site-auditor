import re

from .core import CategoryResult, Issue, penalty_score, text_of, truncate
from .page import Page


def _meta(page: Page, *, name: str | None = None, prop: str | None = None) -> str:
    attrs = {"name": re.compile(f"^{name}$", re.I)} if name else {"property": prop}
    tag = page.soup.find("meta", attrs=attrs)
    return (tag.get("content") or "").strip() if tag else ""


def analyze(page: Page) -> CategoryResult:
    soup = page.soup
    issues: list[Issue] = []
    passed: list[str] = []

    if page.fetch.status >= 400:
        issues.append(Issue(
            "http-status", "critical", f"Page returns HTTP {page.fetch.status}",
            "Search engines will not index a page that returns an error status.",
            "Fix the server so the page returns 200 OK.",
        ))

    title = soup.title.get_text(strip=True) if soup.title else ""
    if not title:
        issues.append(Issue(
            "title-missing", "serious", "Missing title tag",
            "The title is the clickable headline in search results.",
            "Write a unique 30–60 character title that includes your main keyword.",
        ))
    elif not 15 <= len(title) <= 65:
        issues.append(Issue(
            "title-length", "minor", f"Title is {'too short' if len(title) < 15 else 'too long'} ({len(title)} chars)",
            "Titles outside ~15–65 characters get truncated or under-use the space in search results.",
            "Aim for 30–60 characters.", examples=[truncate(title)],
        ))
    else:
        passed.append("Title length is good")

    description = _meta(page, name="description")
    if not description:
        issues.append(Issue(
            "meta-description", "serious", "Missing meta description",
            "Without one, search engines pick a random snippet of page text for your listing.",
            "Add a compelling 120–160 character meta description that encourages clicks.",
        ))
    elif not 50 <= len(description) <= 170:
        issues.append(Issue(
            "description-length", "minor", f"Meta description length ({len(description)} chars)",
            "Descriptions that are very short or long are rewritten or truncated in results.",
            "Aim for 120–160 characters.", examples=[truncate(description)],
        ))
    else:
        passed.append("Meta description is present")

    h1s = soup.find_all("h1")
    if not h1s:
        issues.append(Issue(
            "h1-missing", "moderate", "No H1 heading",
            "The H1 tells search engines and visitors what the page is about.",
            "Add one H1 that states the page's main topic.",
        ))
    elif len(h1s) > 1:
        issues.append(Issue(
            "h1-multiple", "minor", "Multiple H1 headings",
            "Several H1s dilute the page's main topic.",
            "Keep a single H1 and use H2s for sections.",
            count=len(h1s), examples=[truncate(text_of(h), 60) for h in h1s[:5]],
        ))
    else:
        passed.append("Single H1 heading")

    robots = _meta(page, name="robots").lower()
    x_robots = page.headers.get("x-robots-tag", "").lower()
    if "noindex" in robots or "noindex" in x_robots:
        issues.append(Issue(
            "noindex", "critical", "Page is blocked from search engines",
            "A noindex directive tells Google not to show this page in results.",
            "Remove noindex unless you deliberately want the page hidden.",
        ))
    else:
        passed.append("Page is indexable")

    canonical = soup.find("link", rel="canonical")
    if not canonical:
        issues.append(Issue(
            "canonical", "minor", "No canonical URL",
            "Without a canonical link, duplicate URLs (with tracking parameters etc.) split ranking signals.",
            'Add <link rel="canonical" href="…"> pointing at the preferred URL.',
        ))
    else:
        passed.append("Canonical URL set")

    missing_og = [p for p in ("og:title", "og:description", "og:image") if not _meta(page, prop=p)]
    if missing_og:
        issues.append(Issue(
            "open-graph", "minor", "Incomplete social sharing tags",
            "Links shared on Facebook, LinkedIn, Slack etc. will look plain or broken.",
            "Add Open Graph tags (og:title, og:description, og:image).",
            count=len(missing_og), examples=missing_og,
        ))
    else:
        passed.append("Open Graph tags present")

    if not soup.find("script", type="application/ld+json"):
        issues.append(Issue(
            "structured-data", "minor", "No structured data",
            "Structured data (JSON-LD) enables rich results like star ratings, FAQs and business info.",
            "Add schema.org JSON-LD for your organisation, products or articles.",
        ))
    else:
        passed.append("Structured data found")

    robots_txt = page.extras.get("robots")
    if robots_txt is not None:
        if robots_txt.ok:
            passed.append("robots.txt found")
        else:
            issues.append(Issue(
                "robots-txt", "minor", "No robots.txt file",
                "robots.txt guides crawlers and points them to your sitemap.",
                "Add a /robots.txt with a Sitemap: line.",
            ))

    sitemap = page.extras.get("sitemap")
    if sitemap is not None:
        if sitemap.ok:
            passed.append("XML sitemap found")
        else:
            issues.append(Issue(
                "sitemap", "minor", "No XML sitemap",
                "A sitemap helps search engines discover all your pages.",
                "Generate /sitemap.xml and submit it in Google Search Console.",
            ))

    word_count = len(text_of(soup.body).split()) if soup.body else 0
    if word_count < 250:
        issues.append(Issue(
            "thin-content", "moderate", f"Thin content ({word_count} words)",
            "Pages with very little text rarely rank for anything.",
            "Add useful, original copy that answers your visitors' questions.",
        ))
    else:
        passed.append(f"Good amount of content ({word_count:,} words)")

    return CategoryResult(penalty_score(issues), issues, passed)
