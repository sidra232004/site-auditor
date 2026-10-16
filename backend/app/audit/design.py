"""Heuristic UX and visual-design suggestions derived from markup and CSS."""

import re
from datetime import date
from typing import Any

from .colors import extract_colors
from .core import CategoryResult, Issue, penalty_score, text_of, truncate
from .page import Page

DEPRECATED_TAGS = ["font", "center", "marquee", "blink", "big", "strike", "tt", "frameset", "frame"]
GENERIC_FONTS = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "inherit",
                 "initial", "-apple-system", "blinkmacsystemfont", "ui-sans-serif", "ui-serif",
                 "ui-monospace", "emoji", "math", "unset", "var"}
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
ICON_OR_CODE_FONT_RE = re.compile(
    r"icon|awesome|glyph|material symbols|dashicons|consolas|courier|menlo|monaco|"
    r"\bcode\b|mono\b|fira code|inconsolata", re.I,
)
WEIGHT_SUFFIX_RE = re.compile(
    r"(?:[\s_-]*(?:thin|hairline|extralight|ultralight|light|regular|book|normal|medium|semibold|"
    r"demibold|bold|extrabold|ultrabold|black|heavy|italic|oblique|condensed|\d00))+$", re.I,
)
FONT_SIZE_PX_RE =re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)px", re.I)
COPYRIGHT_RE = re.compile(r"(?:©|&copy;|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})", re.I)
CTA_RE = re.compile(r"\b(btn|button|cta)\b", re.I)
LOREM_RE = re.compile(r"lorem ipsum|dolor sit amet", re.I)


def _css_text(page: Page) -> str:
    blocks = [s.get_text() for s in page.soup.find_all("style")]
    blocks += [t["style"] for t in page.soup.find_all(style=True)]
    return "\n".join(blocks)


def _normalize_family(name: str) -> str | None:
    """'SourceSansPro-BoldItalic' -> 'SourceSansPro'; None for icon, code and placeholder fonts."""
    name = name.strip().strip("\"'").strip()
    if not name or name.lower() in GENERIC_FONTS or name[0] in "$@#" or name.startswith("var("):
        return None
    if ICON_OR_CODE_FONT_RE.search(name):
        return None
    base = WEIGHT_SUFFIX_RE.sub("", name).strip(" -_")
    return base or name


def _font_families(page: Page, css: str) -> list[str]:
    families: dict[str, str] = {}  # lowercase key -> display name
    candidates = [m.group(1).split(",")[0] for m in FONT_FAMILY_RE.finditer(css)]
    for link in page.soup.find_all("link", href=re.compile(r"fonts\.googleapis\.com")):
        candidates += [f.replace("+", " ") for f in re.findall(r"family=([^&:]+)", link["href"])]
    for candidate in candidates:
        if family := _normalize_family(candidate):
            families.setdefault(family.lower().replace(" ", ""), family)
    return list(families.values())


def collect(page: Page) -> dict[str, Any]:
    css = "\n".join([_css_text(page), *page.stylesheets])
    colors = extract_colors(css)
    headings = [
        {"level": int(h.name[1]), "text": truncate(text_of(h), 80)}
        for h in page.soup.find_all(re.compile(r"^h[1-6]$"))
    ][:40]
    return {
        "fonts": _font_families(page, css),
        "colors": colors[:24],
        "color_count": len(colors),
        "headings": headings,
        "images": len(page.soup.find_all("img")),
        "word_count": len(text_of(page.soup.body).split()) if page.soup.body else 0,
        "inline_styles": len(page.soup.find_all(style=True)),
    }


def analyze(page: Page, info: dict[str, Any]) -> CategoryResult:
    soup = page.soup
    issues: list[Issue] = []
    passed: list[str] = []

    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    viewport_content = (viewport.get("content", "") if viewport else "").replace(" ", "").lower()
    # initial-scale=1 alone also yields a device-width layout in every mobile browser.
    if "width=device-width" not in viewport_content and "initial-scale=1" not in viewport_content:
        issues.append(Issue(
            "not-responsive", "critical", "Not optimised for mobile",
            "Without a responsive viewport, phones show a tiny zoomed-out desktop page. "
            "Over half of web traffic is mobile.",
            'Add <meta name="viewport" content="width=device-width, initial-scale=1"> and responsive CSS.',
        ))
    else:
        passed.append("Mobile-friendly viewport")

    deprecated = {t: n for t in DEPRECATED_TAGS if (n := len(soup.find_all(t)))}
    if deprecated:
        issues.append(Issue(
            "deprecated-html", "moderate", "Outdated HTML tags",
            "Tags like <font> and <center> signal a dated site and render inconsistently.",
            "Replace presentational tags with CSS.",
            count=sum(deprecated.values()), examples=[f"<{t}> × {n}" for t, n in deprecated.items()],
        ))
    else:
        passed.append("Modern HTML markup")

    if LOREM_RE.search(text_of(soup)):
        issues.append(Issue(
            "placeholder-text", "serious", "Placeholder text left on the page",
            '"Lorem ipsum" filler makes the site look unfinished and erodes trust.',
            "Replace placeholder text with real content.",
        ))

    fonts = info["fonts"]
    if len(fonts) > 3:
        issues.append(Issue(
            "too-many-fonts", "moderate", f"{len(fonts)} different typefaces",
            "Many typefaces make a design feel inconsistent and slow the page with extra font files.",
            "Stick to 1–2 typefaces: one for headings and one for body text.",
            count=len(fonts), examples=fonts[:8],
        ))
    elif fonts:
        passed.append("Consistent typography")

    if info["color_count"] > 30:
        issues.append(Issue(
            "color-sprawl", "minor", f"{info['color_count']} distinct colors in the CSS",
            "A sprawling palette looks unpolished and weakens brand recognition.",
            "Define a small palette (primary, accent, neutrals) as CSS variables and reuse it.",
            count=info["color_count"], examples=["Most used: " + ", ".join(info["colors"][:10])],
        ))

    if info["inline_styles"] > 40:
        issues.append(Issue(
            "inline-styles", "minor", "Heavy use of inline styles",
            f"{info['inline_styles']} elements carry style attributes, making the design hard to keep consistent.",
            "Move repeated styling into CSS classes or a design system.",
            count=info["inline_styles"],
        ))

    # Only page-level CSS: framework stylesheets legitimately use tiny sizes for badges etc.
    tiny = [float(s) for s in FONT_SIZE_PX_RE.findall(_css_text(page)) if float(s) < 12]
    if tiny:
        issues.append(Issue(
            "small-text", "moderate", "Text smaller than 12px",
            "Very small text is hard to read on phones and for older visitors.",
            "Use at least 16px for body text and 12px for fine print.",
            count=len(tiny), examples=[f"{s:g}px" for s in sorted(set(tiny))[:5]],
        ))

    long_paragraphs = [p for p in soup.find_all("p") if len(text_of(p).split()) > 150]
    if long_paragraphs:
        issues.append(Issue(
            "wall-of-text", "minor", "Long, dense paragraphs",
            "Visitors scan rather than read; long blocks of text get skipped.",
            "Break paragraphs into 2–4 sentences and add subheadings, lists or images.",
            count=len(long_paragraphs),
            examples=[truncate(text_of(p), 80) for p in long_paragraphs[:3]],
        ))

    has_cta = soup.find("button") or soup.find("input", type="submit") or any(
        CTA_RE.search(" ".join(a.get("class", []))) for a in soup.find_all("a")
    )
    if not has_cta:
        issues.append(Issue(
            "no-cta", "moderate", "No clear call-to-action",
            "Nothing on the page stands out as the next step (buy, contact, sign up).",
            "Add a prominent button for the main action you want visitors to take.",
        ))
    else:
        passed.append("Call-to-action present")

    if info["images"] == 0 and info["word_count"] > 200:
        issues.append(Issue(
            "no-imagery", "minor", "No images on the page",
            "Text-only pages feel less engaging and are harder to scan.",
            "Add relevant photos, illustrations or diagrams.",
        ))

    favicon = page.extras.get("favicon")
    has_icon_link = soup.find("link", rel=lambda r: r and "icon" in [x.lower() for x in r])
    if not has_icon_link and not (favicon and favicon.ok):
        issues.append(Issue(
            "favicon", "minor", "No favicon",
            "Browser tabs and bookmarks show a generic icon instead of your brand.",
            "Add a favicon (and an apple-touch-icon for iOS home screens).",
        ))
    else:
        passed.append("Favicon present")

    years = [int(y) for y in COPYRIGHT_RE.findall(text_of(soup))]
    if years and max(years) < date.today().year - 1:
        issues.append(Issue(
            "stale-copyright", "minor", f"Copyright notice says {max(years)}",
            "An old copyright year makes visitors wonder if the business is still active.",
            "Update the footer year (or generate it automatically).",
        ))

    return CategoryResult(penalty_score(issues), issues, passed)
