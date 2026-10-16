"""Security headers and web-standards hygiene."""

import re

from .core import CategoryResult, Issue, penalty_score, truncate
from .page import Page

JQUERY_VERSION = re.compile(r"jquery[.-]?(\d+)\.(\d+)(?:\.(\d+))?", re.I)
VERSIONED_SERVER = re.compile(r"/\d")


def analyze(page: Page) -> CategoryResult:
    soup = page.soup
    headers = page.headers
    issues: list[Issue] = []
    passed: list[str] = []

    if not page.is_https:
        issues.append(Issue(
            "https", "critical", "Site is not served over HTTPS",
            "Browsers mark the site \"Not secure\" and visitor data travels unencrypted.",
            "Install a free TLS certificate (e.g. Let's Encrypt) and redirect all HTTP traffic to HTTPS.",
        ))
    else:
        passed.append("Served over HTTPS")
        if "strict-transport-security" not in headers:
            issues.append(Issue(
                "hsts", "moderate", "HSTS header missing",
                "Without HSTS, the first visit can be downgraded to insecure HTTP.",
                "Send `Strict-Transport-Security: max-age=31536000; includeSubDomains`.",
            ))
        else:
            passed.append("HSTS enabled")

        insecure = [
            tag.get("src") or tag.get("href")
            for tag in soup.find_all(["script", "img", "iframe", "link", "source", "video", "audio"])
            if (tag.get("src") or tag.get("href") or "").startswith("http://")
            and not (tag.name == "link" and "stylesheet" not in tag.get("rel", []))
        ]
        if insecure:
            issues.append(Issue(
                "mixed-content", "serious", "Mixed content",
                "This HTTPS page loads files over insecure HTTP; browsers block or warn about them.",
                "Change these URLs to https:// (or protocol-relative).",
                count=len(insecure), examples=[truncate(u) for u in insecure[:5]],
            ))
        else:
            passed.append("No mixed content")

    csp = headers.get("content-security-policy", "")
    if not csp:
        issues.append(Issue(
            "csp", "moderate", "No Content-Security-Policy",
            "A CSP is the strongest defence against cross-site scripting (XSS).",
            "Add a Content-Security-Policy header, starting in report-only mode.",
        ))
    else:
        passed.append("Content-Security-Policy set")

    if "x-frame-options" not in headers and "frame-ancestors" not in csp:
        issues.append(Issue(
            "clickjacking", "moderate", "No clickjacking protection",
            "Other sites can embed this page in a frame and trick users into clicking.",
            "Send `X-Frame-Options: SAMEORIGIN` or a CSP `frame-ancestors` directive.",
        ))
    else:
        passed.append("Clickjacking protection")

    if headers.get("x-content-type-options", "").lower() != "nosniff":
        issues.append(Issue(
            "nosniff", "minor", "X-Content-Type-Options missing",
            "Browsers may guess file types, which can turn uploads into executable scripts.",
            "Send `X-Content-Type-Options: nosniff`.",
        ))
    else:
        passed.append("MIME sniffing disabled")

    if "referrer-policy" not in headers:
        issues.append(Issue(
            "referrer-policy", "minor", "No Referrer-Policy",
            "Full URLs (which can include private data) leak to every external site you link to.",
            "Send `Referrer-Policy: strict-origin-when-cross-origin`.",
        ))

    leaks = [f"{h}: {headers[h]}" for h in ("server", "x-powered-by", "x-aspnet-version")
             if h in headers and (h != "server" or VERSIONED_SERVER.search(headers[h]))]
    if leaks:
        issues.append(Issue(
            "version-disclosure", "minor", "Server software version exposed",
            "Advertising exact software versions helps attackers find known vulnerabilities.",
            "Hide version numbers in Server / X-Powered-By headers.",
            count=len(leaks), examples=leaks,
        ))

    if not page.html.lstrip()[:15].lower().startswith("<!doctype html"):
        issues.append(Issue(
            "doctype", "moderate", "Missing HTML5 doctype",
            "Without <!DOCTYPE html> browsers render in quirks mode, causing layout inconsistencies.",
            "Add <!DOCTYPE html> as the very first line.",
        ))
    else:
        passed.append("HTML5 doctype")

    has_charset = soup.find("meta", charset=True) or "charset=" in headers.get("content-type", "")
    if not has_charset:
        issues.append(Issue(
            "charset", "minor", "Character encoding not declared",
            "Special characters may display as garbage.",
            'Add <meta charset="utf-8"> at the top of <head>.',
        ))
    else:
        passed.append("Character encoding declared")

    unsafe_blank = [a["href"] for a in soup.find_all("a", href=True, target="_blank")
                    if not {"noopener", "noreferrer"} & set(a.get("rel", []))
                    and not page.is_internal(a["href"]) and a["href"].startswith("http")]
    if unsafe_blank:
        issues.append(Issue(
            "noopener", "minor", 'External links open without rel="noopener"',
            "Older browsers let the opened page control yours (reverse tabnabbing).",
            'Add rel="noopener" to links with target="_blank".',
            count=len(unsafe_blank), examples=[truncate(u, 90) for u in unsafe_blank[:5]],
        ))

    old_jquery = []
    for res in page.resources:
        if res.kind == "script" and (m := JQUERY_VERSION.search(res.url)):
            major, minor = int(m.group(1)), int(m.group(2))
            if (major, minor) < (3, 5):
                old_jquery.append(f"{m.group(0)} — {truncate(res.url, 80)}")
    if old_jquery:
        issues.append(Issue(
            "vulnerable-library", "serious", "Outdated jQuery with known vulnerabilities",
            "jQuery versions before 3.5 have published XSS vulnerabilities (CVE-2020-11022/11023).",
            "Upgrade to the latest jQuery 3.x, or remove it if no longer needed.",
            count=len(old_jquery), examples=old_jquery,
        ))

    return CategoryResult(penalty_score(issues), issues, passed)
