import os
from dataclasses import dataclass
from pathlib import Path


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{Path(__file__).resolve().parent.parent / 'audits.db'}"
    )
    cors_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    )
    # Allow auditing localhost / private networks. Off by default: the server fetches
    # arbitrary user-supplied URLs, so private targets would be an SSRF hole.
    allow_private_targets: bool = _flag("ALLOW_PRIVATE_TARGETS")
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "15"))
    max_page_bytes: int = int(os.getenv("MAX_PAGE_BYTES", str(5 * 1024 * 1024)))
    max_resources: int = int(os.getenv("MAX_RESOURCES", "60"))
    max_links: int = int(os.getenv("MAX_LINKS", "80"))
    probe_concurrency: int = int(os.getenv("PROBE_CONCURRENCY", "10"))
    max_concurrent_audits: int = int(os.getenv("MAX_CONCURRENT_AUDITS", "3"))
    # Upper bound on audits waiting or running, so the server can't be flooded with work.
    max_pending_audits: int = int(os.getenv("MAX_PENDING_AUDITS", "20"))
    # Hard deadline for a whole audit; per-request timeouts alone can't stop a slow-drip server.
    audit_timeout: float = float(os.getenv("AUDIT_TIMEOUT", "120"))
    # Optional Google PageSpeed Insights (real Lighthouse lab data + Core Web Vitals).
    pagespeed_api_key: str | None = os.getenv("PAGESPEED_API_KEY") or None
    # Built frontend (frontend/dist) to serve alongside the API; unset in development.
    static_dir: str | None = os.getenv("STATIC_DIR") or None
    user_agent: str = os.getenv(
        "AUDIT_USER_AGENT",
        "Mozilla/5.0 (compatible; SiteAuditor/1.0; +https://github.com/site-auditor)",
    )


settings = Settings()
