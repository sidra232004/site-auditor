"""Renders a finished audit report as a downloadable PDF."""

from datetime import datetime
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

INK = colors.HexColor("#0b0b0b")
INK_2 = colors.HexColor("#52514e")
MUTED = colors.HexColor("#898781")
HAIRLINE = colors.HexColor("#e1e0d9")
ACCENT = colors.HexColor("#2a78d6")
SEVERITY = {
    "critical": colors.HexColor("#d03b3b"),
    "serious": colors.HexColor("#ec835a"),
    "moderate": colors.HexColor("#c98500"),
    "minor": colors.HexColor("#898781"),
}
LABELS = {
    "performance": "Performance",
    "accessibility": "Accessibility",
    "seo": "SEO",
    "best_practices": "Best practices",
    "design": "Design & UX",
    "links": "Links",
}


FONT_CANDIDATES = [  # Unicode TTFs so page titles and arrows render; Helvetica is the fallback
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def _register_fonts() -> tuple[str, str]:
    for regular, bold in FONT_CANDIDATES:
        try:
            pdfmetrics.registerFont(TTFont("Body", regular))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold))
            pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold")
            return "Body", "Body-Bold"
        except Exception:  # noqa: BLE001 - font missing or unreadable, try the next one
            continue
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _register_fonts()


def score_color(score: float) -> colors.Color:
    if score >= 90:
        return colors.HexColor("#0ca30c")
    if score >= 50:
        return colors.HexColor("#c98500")
    return colors.HexColor("#d03b3b")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    for style in base.byName.values():
        if isinstance(style, ParagraphStyle):
            style.fontName = FONT_BOLD if "Bold" in style.fontName else FONT
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=22, textColor=INK, alignment=0, spaceAfter=2),
        "url": ParagraphStyle("u", parent=base["Normal"], fontSize=10, textColor=ACCENT),
        "meta": ParagraphStyle("m", parent=base["Normal"], fontSize=9, textColor=MUTED),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=14, textColor=INK, spaceBefore=14, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading4"], fontSize=10.5, textColor=INK, spaceAfter=2, spaceBefore=0),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9, leading=12.5, textColor=INK_2),
        "fix": ParagraphStyle("f", parent=base["Normal"], fontSize=9, leading=12.5, textColor=INK),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=7.5, leading=10, textColor=MUTED),
        "big": ParagraphStyle("big", parent=base["Normal"], fontSize=40, leading=44, alignment=1),
        "center": ParagraphStyle("c", parent=base["Normal"], fontSize=9, alignment=1, textColor=INK_2),
    }


def _score_chart(scores: dict[str, Any]) -> Drawing:
    names = list(LABELS)
    drawing = Drawing(300, 150)
    chart = HorizontalBarChart()
    chart.x, chart.y, chart.width, chart.height = 85, 10, 195, 132
    chart.data = [[scores.get(n, 0) for n in reversed(names)]]
    chart.categoryAxis.categoryNames = [LABELS[n] for n in reversed(names)]
    chart.categoryAxis.labels.fontName = FONT
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fillColor = INK_2
    chart.categoryAxis.strokeColor = HAIRLINE
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 25
    chart.valueAxis.labels.fontName = FONT
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = HAIRLINE
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.gridStrokeColor = HAIRLINE
    chart.barWidth = 9
    chart.bars.strokeColor = None
    for i, n in enumerate(reversed(names)):
        chart.bars[(0, i)].fillColor = score_color(scores.get(n, 0))
    drawing.add(chart)
    for i, n in enumerate(reversed(names)):
        value = scores.get(n, 0)
        y = chart.y + (i + 0.5) * chart.height / len(names) - 3
        drawing.add(String(chart.x + chart.width * value / 100 + 4, y, str(value), fontName=FONT, fontSize=7.5, fillColor=INK))
    return drawing


def render_pdf(audit_id: int, report: dict[str, Any]) -> bytes:
    s = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Website audit — {report['final_url']}", author="Site Auditor",
    )
    scores = report["scores"]
    metrics = report["metrics"]
    fetched = datetime.fromisoformat(report["fetched_at"]).strftime("%d %B %Y, %H:%M UTC")
    story: list[Any] = [
        Paragraph("Website Audit Report", s["title"]),
        Paragraph(escape(report["final_url"]), s["url"]),
        Paragraph(f"Audit #{audit_id} · {fetched}", s["meta"]),
        Paragraph("Scores are calculated by Site Auditor from automated checks of the page's HTML, "
                  "headers and links. They are not Google Lighthouse scores unless labelled as such.", s["meta"]),
        Spacer(1, 8 * mm),
    ]

    overall = scores["overall"]
    counts = report["issue_counts"]
    hero = Table(
        [[
            [Paragraph(f'<font color="{score_color(overall).hexval().replace("0x", "#")}">{overall}</font>', s["big"]),
             Paragraph("Overall score / 100", s["center"]),
             Spacer(1, 4 * mm),
             Paragraph(f"{counts['critical']} critical · {counts['serious']} serious<br/>"
                       f"{counts['moderate']} moderate · {counts['minor']} minor", s["center"])],
            _score_chart(scores),
        ]],
        colWidths=[55 * mm, None],
    )
    hero.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(hero)

    story.append(Paragraph("Key metrics", s["h2"]))
    links = report["links"]
    rows = [
        ["Server response (TTFB)", f"{metrics['ttfb_ms']:,} ms", "Requests", f"{metrics['request_count']}"],
        ["HTML download", f"{metrics['load_ms']:,} ms", "DOM elements", f"{metrics['dom_elements']:,}"],
        ["Page weight", f"{metrics['page_weight_kb']:,.0f} KB", "Links checked", f"{links['checked']}"],
        ["Redirects", f"{metrics['redirects']}", "Broken links", f"{links['broken']}"],
    ]
    table = Table(rows, colWidths=[45 * mm, 32 * mm, 45 * mm, None])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK_2),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("TEXTCOLOR", (3, 0), (3, -1), INK),
        ("FONTNAME", (1, 0), (1, -1), FONT_BOLD),
        ("FONTNAME", (3, 0), (3, -1), FONT_BOLD),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, HAIRLINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)

    if (psi := report.get("pagespeed")) and psi.get("error"):
        story.append(Paragraph("Google Lighthouse (mobile)", s["h2"]))
        story.append(Paragraph(f"Unavailable for this audit: {escape(psi['error'])}", s["body"]))
    elif psi:
        story.append(Paragraph("Google Lighthouse (mobile)", s["h2"]))
        parts = [f"{LABELS.get(k.replace('-', '_'), k)}: <b>{v}</b>" for k, v in psi["categories"].items()]
        parts += [f"{m['label']}: <b>{escape(str(m['value']))}</b>" for m in psi["metrics"]]
        story.append(Paragraph(" · ".join(parts), s["body"]))

    for name, label in LABELS.items():
        category = report["categories"][name]
        story.append(Paragraph(
            f'{label} — <font color="{score_color(category["score"]).hexval().replace("0x", "#")}">'
            f'{category["score"]}</font>/100', s["h2"],
        ))
        if not category["issues"]:
            story.append(Paragraph("No issues found.", s["body"]))
        for issue in category["issues"]:
            color = SEVERITY[issue["severity"]].hexval().replace("0x", "#")
            count = f" ({issue['count']})" if issue["count"] > 1 else ""
            block = [
                Paragraph(f'<font color="{color}"><b>{issue["severity"].upper()}</b></font>  '
                          f'{escape(issue["title"])}{count}', s["h3"]),
                Paragraph(escape(issue["description"]), s["body"]),
                Paragraph(f"<b>Fix:</b> {escape(issue['recommendation'])}", s["fix"]),
            ]
            if issue["examples"]:
                block.append(Paragraph("<br/>".join(escape(e) for e in issue["examples"][:4]), s["small"]))
            block.append(Spacer(1, 3.5 * mm))
            story.append(KeepTogether(block))
        if category["passed"]:
            story.append(Paragraph("Passed: " + escape(", ".join(category["passed"])), s["small"]))

    def footer(canvas, document) -> None:  # noqa: ANN001
        canvas.saveState()
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 9 * mm, f"Site Auditor · {report['final_url'][:90]}")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
