"""Static WCAG checks modeled on the most impactful axe-core rules."""

import re
from collections import Counter

from bs4 import BeautifulSoup, Tag

from .colors import contrast_ratio, parse_color
from .page import Page
from .core import CategoryResult, Issue, penalty_score, text_of, truncate

VAGUE_LINK_TEXT = {"click here", "here", "read more", "more", "learn more", "this", "link", "click"}
LABELLABLE_INPUTS = {"text", "email", "password", "search", "tel", "url", "number", "date",
                     "datetime-local", "month", "week", "time", "file", "checkbox", "radio",
                     "range", "color", ""}


def accessible_name(tag: Tag) -> str:
    for attr in ("aria-label", "title"):
        if (value := tag.get(attr)) and value.strip():
            return value.strip()
    if tag.get("aria-labelledby"):
        return "labelledby"
    text = text_of(tag)
    if text:
        return text
    for img in tag.find_all(["img", "svg"]):
        svg_title = img.find("title")
        alt = img.get("alt") or img.get("aria-label") or (text_of(svg_title) if svg_title else "")
        if alt and alt.strip():
            return alt.strip()
    return ""


def _describe(tag: Tag) -> str:
    attrs = " ".join(f'{k}="{v if isinstance(v, str) else " ".join(v)}"'
                     for k, v in list(tag.attrs.items())[:3])
    return truncate(f"<{tag.name}{' ' + attrs if attrs else ''}>", 100)


def _has_label(field: Tag, soup: BeautifulSoup) -> bool:
    if field.get("aria-label", "").strip() or field.get("aria-labelledby") or field.get("title", "").strip():
        return True
    if field.find_parent("label"):
        return True
    field_id = field.get("id")
    return bool(field_id and soup.find("label", attrs={"for": field_id}))


def analyze(page: Page) -> CategoryResult:
    soup = page.soup
    issues: list[Issue] = []
    passed: list[str] = []

    def check(condition_failed: bool, issue: Issue, passed_text: str) -> None:
        if condition_failed:
            issues.append(issue)
        else:
            passed.append(passed_text)

    html = soup.find("html")
    check(
        not (html and html.get("lang", "").strip()),
        Issue("html-lang", "serious", "Page language not declared",
              "Screen readers can't pick the right pronunciation without a lang attribute.",
              'Add a language to the root element, e.g. <html lang="en">.'),
        "Page language is declared",
    )

    title = soup.title.get_text(strip=True) if soup.title else ""
    check(
        not title,
        Issue("document-title", "serious", "Missing page title",
              "The <title> is the first thing screen reader users hear and what browser tabs show.",
              "Add a short, descriptive <title> to every page."),
        "Page has a title",
    )

    no_alt = [img for img in soup.find_all("img") if not img.has_attr("alt")
              and img.get("role") != "presentation" and img.get("aria-hidden") != "true"]
    check(
        bool(no_alt),
        Issue("image-alt", "critical", "Images missing alt text",
              "Blind visitors get no information from these images.",
              'Describe each meaningful image in an alt attribute; use alt="" for decorative ones.',
              count=len(no_alt), examples=[truncate(i.get("src") or _describe(i)) for i in no_alt[:5]]),
        "All images have alt attributes",
    )

    fields = [
        f for f in soup.find_all(["input", "select", "textarea"])
        if f.name != "input" or f.get("type", "").lower() in LABELLABLE_INPUTS
    ]
    unlabeled = [f for f in fields if not _has_label(f, soup)]
    if fields:
        check(
            bool(unlabeled),
            Issue("form-label", "critical", "Form fields without labels",
                  "Screen reader users can't tell what to enter. Placeholder text is not a label.",
                  "Associate a <label for=…> with each field, or add aria-label.",
                  count=len(unlabeled), examples=[_describe(f) for f in unlabeled[:5]]),
            "Form fields are labelled",
        )

    unnamed_buttons = [b for b in soup.find_all("button") if not accessible_name(b)]
    unnamed_buttons += [i for i in soup.find_all("input", type=["submit", "button", "reset"])
                        if not (i.get("value") or i.get("aria-label"))]
    check(
        bool(unnamed_buttons),
        Issue("button-name", "critical", "Buttons without accessible names",
              "Icon-only buttons are announced as just \"button\", with no hint of what they do.",
              "Add visible text or an aria-label to every button.",
              count=len(unnamed_buttons), examples=[_describe(b) for b in unnamed_buttons[:5]]),
        "Buttons have accessible names",
    )

    anchors = soup.find_all("a", href=True)
    unnamed_links = [a for a in anchors if not accessible_name(a)]
    check(
        bool(unnamed_links),
        Issue("link-name", "serious", "Links without text",
              "Links with no text (often icon or image links) are announced only as their URL.",
              "Give every link discernible text, an aria-label, or an image with alt text.",
              count=len(unnamed_links), examples=[truncate(a["href"]) for a in unnamed_links[:5]]),
        "Links have discernible text",
    )

    vague = [a for a in anchors if text_of(a).lower().strip(".!»› ") in VAGUE_LINK_TEXT]
    if vague:
        issues.append(Issue(
            "vague-links", "moderate", "Non-descriptive link text",
            '"Click here" and "Read more" make no sense when screen reader users list links out of context.',
            'Describe the destination, e.g. "Read our pricing guide".',
            count=len(vague), examples=[f'"{text_of(a)}" → {truncate(a["href"], 70)}' for a in vague[:5]],
        ))

    levels = [int(h.name[1]) for h in soup.find_all(re.compile(r"^h[1-6]$"))]
    skips = [f"h{a} → h{b}" for a, b in zip(levels, levels[1:]) if b > a + 1]
    check(
        bool(skips),
        Issue("heading-order", "moderate", "Heading levels are skipped",
              "Skipping levels breaks the outline screen reader users navigate by.",
              "Use headings in order (h1, then h2, then h3) without jumping levels.",
              count=len(skips), examples=skips[:5]),
        "Heading levels are sequential",
    )

    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    content = (viewport.get("content", "") if viewport else "").lower().replace(" ", "")
    max_scale = re.search(r"maximum-scale=(\d+(?:\.\d+)?)", content)
    zoom_blocked = "user-scalable=no" in content or "user-scalable=0" in content or (
        max_scale is not None and float(max_scale.group(1)) < 2
    )
    check(
        zoom_blocked,
        Issue("zoom-disabled", "serious", "Pinch-to-zoom is disabled",
              "Low-vision visitors can't enlarge text on mobile.",
              "Remove user-scalable=no and maximum-scale from the viewport meta tag."),
        "Zooming is allowed",
    )

    check(
        not (soup.find("main") or soup.find(attrs={"role": "main"})),
        Issue("landmark-main", "moderate", "No main landmark",
              "Keyboard and screen reader users can't jump straight to the content.",
              "Wrap the primary content in a <main> element."),
        "Page has a main landmark",
    )

    positive_tab = [t for t in soup.find_all(attrs={"tabindex": True})
                    if str(t["tabindex"]).strip().lstrip("+").isdigit() and int(t["tabindex"]) > 0]
    if positive_tab:
        issues.append(Issue(
            "tabindex", "serious", "Positive tabindex values",
            "tabindex greater than 0 overrides the natural keyboard order and confuses users.",
            'Use tabindex="0" or "-1" and arrange focus order through the DOM instead.',
            count=len(positive_tab), examples=[_describe(t) for t in positive_tab[:5]],
        ))

    untitled_frames = [f for f in soup.find_all("iframe") if not f.get("title", "").strip()]
    if untitled_frames:
        issues.append(Issue(
            "frame-title", "serious", "Iframes without titles",
            "Embedded frames are announced without any description of their content.",
            'Add a title attribute to each iframe, e.g. title="Location map".',
            count=len(untitled_frames), examples=[truncate(f.get("src", "")) for f in untitled_frames[:5]],
        ))

    autoplay = [m for m in soup.find_all(["video", "audio"], autoplay=True) if not m.has_attr("muted")]
    if autoplay:
        issues.append(Issue(
            "autoplay-audio", "moderate", "Media autoplays with sound",
            "Unexpected sound interferes with screen readers and startles visitors.",
            "Mute autoplaying media or let users start playback.",
            count=len(autoplay),
        ))

    ids = Counter(t["id"] for t in soup.find_all(id=True))
    duplicates = [i for i, n in ids.items() if n > 1]
    if duplicates:
        issues.append(Issue(
            "duplicate-id", "minor", "Duplicate element IDs",
            "Duplicate IDs break label associations and ARIA references.",
            "Make every id attribute unique on the page.",
            count=len(duplicates), examples=duplicates[:5],
        ))

    low_contrast = []
    for tag in soup.find_all(style=True):
        style = tag["style"].lower()
        fg = re.search(r"(?:^|;)\s*color\s*:\s*([^;]+)", style)
        bg = re.search(r"background(?:-color)?\s*:\s*([^;]+)", style)
        if fg and bg and (c1 := parse_color(fg.group(1))) and (c2 := parse_color(bg.group(1))):
            ratio = contrast_ratio(c1, c2)
            if ratio < 4.5 and text_of(tag):
                low_contrast.append(f'{ratio:.1f}:1 — "{truncate(text_of(tag), 50)}"')
    if low_contrast:
        issues.append(Issue(
            "color-contrast", "serious", "Low color contrast",
            "Text with insufficient contrast is hard to read, especially in sunlight or for low-vision users.",
            "Ensure a contrast ratio of at least 4.5:1 for body text (3:1 for large text).",
            count=len(low_contrast), examples=low_contrast[:5],
        ))

    return CategoryResult(penalty_score(issues), issues, passed)
