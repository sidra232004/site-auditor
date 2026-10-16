from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from bs4 import CData, NavigableString, Tag, TemplateString

Severity = Literal["critical", "serious", "moderate", "minor"]

# Points deducted from a category's score for each issue of a given severity.
PENALTY: dict[str, int] = {"critical": 25, "serious": 12, "moderate": 6, "minor": 2}


@dataclass
class Issue:
    id: str
    severity: Severity
    title: str
    description: str
    recommendation: str
    count: int = 1
    examples: list[str] = field(default_factory=list)


@dataclass
class CategoryResult:
    score: int
    issues: list[Issue] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        order = list(PENALTY)
        issues = sorted(self.issues, key=lambda i: order.index(i.severity))
        return {
            "score": self.score,
            "issues": [asdict(i) for i in issues],
            "passed": self.passed,
        }


def penalty_score(issues: list[Issue]) -> int:
    return max(0, 100 - sum(PENALTY[i.severity] for i in issues))


def linear_score(value: float, good: float, poor: float) -> float:
    """100 at or below `good`, 0 at or above `poor`, linear in between."""
    if value <= good:
        return 100.0
    if value >= poor:
        return 0.0
    return 100.0 * (poor - value) / (poor - good)


def truncate(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# Visible text includes <template> content: sites using declarative shadow DOM (e.g. Lit SSR)
# put real button/link labels there, and BeautifulSoup skips TemplateString by default.
# Exact-type matching still excludes <script>/<style> contents and comments.
TEXT_TYPES = (NavigableString, CData, TemplateString)


def text_of(tag: Tag, separator: str = " ") -> str:
    return tag.get_text(separator, strip=True, types=TEXT_TYPES)
