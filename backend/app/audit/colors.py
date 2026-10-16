import re

RGB = tuple[int, int, int]

NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "green": (0, 128, 0),
    "blue": (0, 0, 255), "yellow": (255, 255, 0), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "silver": (192, 192, 192), "orange": (255, 165, 0), "navy": (0, 0, 128), "purple": (128, 0, 128),
}
HEX_RE = re.compile(r"#([0-9a-f]{3}|[0-9a-f]{6})\b", re.I)
RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})", re.I)


def parse_color(value: str) -> RGB | None:
    value = value.strip().lower().replace("!important", "").strip()
    if match := HEX_RE.fullmatch(value):
        digits = match.group(1)
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    if match := RGB_RE.match(value):
        return tuple(min(255, int(g)) for g in match.groups())  # type: ignore[return-value]
    return NAMED.get(value)


def _luminance(rgb: RGB) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def to_hex(rgb: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def extract_colors(css: str) -> list[str]:
    """Distinct colors mentioned in a CSS string, normalised to #rrggbb, most frequent first."""
    counts: dict[str, int] = {}
    for match in HEX_RE.finditer(css):
        if rgb := parse_color(match.group(0)):
            counts[to_hex(rgb)] = counts.get(to_hex(rgb), 0) + 1
    for match in RGB_RE.finditer(css):
        rgb = tuple(min(255, int(g)) for g in match.groups())
        counts[to_hex(rgb)] = counts.get(to_hex(rgb), 0) + 1  # type: ignore[arg-type]
    return sorted(counts, key=counts.__getitem__, reverse=True)
