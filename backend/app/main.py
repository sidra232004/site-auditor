import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from .audit.engine import AuditError, run_audit
from .config import settings
from .db import Base, SessionLocal, describe_database, engine, get_session
from .models import Audit
from .netguard import UnsafeURLError, assert_public_url, normalize_url
from .pdf import render_pdf
from .schemas import AuditCreate, AuditDetail, AuditSummary, CompareRow

log = logging.getLogger("site_auditor")
audit_slots = asyncio.Semaphore(settings.max_concurrent_audits)
DbSession = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        Base.metadata.create_all(engine)
    except OperationalError as exc:
        raise RuntimeError(
            f"Could not connect to the database at {describe_database()}. "
            "Check DATABASE_URL and that the database server is running."
        ) from exc
    log.info("Using database %s", describe_database())
    with SessionLocal() as session:  # audits interrupted by a restart will never finish
        session.execute(
            update(Audit)
            .where(Audit.status.in_(["queued", "running"]))
            .values(status="failed", error="Interrupted by a server restart. Please run it again.")
        )
        session.commit()
    yield


app = FastAPI(title="Site Auditor API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _set(audit_id: int, **values) -> None:
    with SessionLocal() as session:
        session.execute(update(Audit).where(Audit.id == audit_id).values(**values))
        session.commit()


async def execute_audit(audit_id: int, url: str) -> None:
    async def progress(message: str) -> None:
        _set(audit_id, progress=message)

    async with audit_slots:
        _set(audit_id, status="running", progress="Starting")
        try:
            async with asyncio.timeout(settings.audit_timeout):
                report = await run_audit(url, progress)
        except TimeoutError:
            _set(audit_id, status="failed", progress=None,
                 error=f"The audit took longer than {settings.audit_timeout:.0f} seconds and was stopped. "
                       "The site may be very slow or unresponsive.")
            return
        except (AuditError, UnsafeURLError) as exc:
            _set(audit_id, status="failed", error=str(exc), progress=None)
            return
        except Exception:
            log.exception("Audit %s crashed", audit_id)
            _set(audit_id, status="failed", error="Unexpected error while auditing this site.", progress=None)
            return
        _set(
            audit_id,
            status="done",
            progress=None,
            final_url=report["final_url"],
            overall_score=report["scores"]["overall"],
            scores=report["scores"],
            report=report,
            completed_at=datetime.now(timezone.utc),
        )


def _get_or_404(session: Session, audit_id: int) -> Audit:
    audit = session.get(Audit, audit_id)
    if audit is None:
        raise HTTPException(404, "Audit not found")
    return audit


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "pagespeed": bool(settings.pagespeed_api_key)}


@app.post("/api/audits", response_model=AuditSummary, status_code=202)
async def create_audit(body: AuditCreate, background: BackgroundTasks, session: DbSession) -> Audit:
    try:
        url = normalize_url(body.url)
        await assert_public_url(url)
    except UnsafeURLError as exc:
        raise HTTPException(422, str(exc)) from exc
    pending = session.scalar(
        select(func.count()).select_from(Audit).where(Audit.status.in_(["queued", "running"]))
    )
    if pending >= settings.max_pending_audits:
        raise HTTPException(429, "Too many audits are running right now. Please try again in a minute.")
    audit = Audit(url=url, status="queued", progress="Queued")
    session.add(audit)
    session.commit()
    background.add_task(execute_audit, audit.id, url)
    return audit


@app.get("/api/audits", response_model=list[AuditSummary])
def list_audits(
    session: DbSession,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Audit]:
    stmt = select(Audit).order_by(Audit.created_at.desc()).limit(limit)
    if q:
        stmt = stmt.where(Audit.url.contains(q))
    return list(session.scalars(stmt))


@app.get("/api/audits/{audit_id}", response_model=AuditDetail)
def get_audit(audit_id: int, session: DbSession) -> Audit:
    return _get_or_404(session, audit_id)


@app.delete("/api/audits/{audit_id}", status_code=204)
def delete_audit(audit_id: int, session: DbSession) -> Response:
    session.delete(_get_or_404(session, audit_id))
    session.commit()
    return Response(status_code=204)


@app.get("/api/audits/{audit_id}/pdf")
def download_pdf(audit_id: int, session: DbSession, inline: bool = False) -> Response:
    audit = _get_or_404(session, audit_id)
    if audit.status == "failed":
        raise HTTPException(409, "This audit failed, so there is no report to export.")
    if audit.status != "done" or not audit.report:
        raise HTTPException(409, "This audit hasn't finished yet.")
    host = (audit.final_url or audit.url).split("//", 1)[-1].split("/", 1)[0]
    return Response(
        render_pdf(audit.id, audit.report),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="audit-{host}-{audit.id}.pdf"'
        },
    )


@app.get("/api/compare", response_model=list[CompareRow])
def compare(session: DbSession, ids: Annotated[str, Query(description="Comma-separated audit ids")]) -> list[CompareRow]:
    try:
        wanted = [int(i) for i in ids.split(",") if i.strip()][:6]
    except ValueError as exc:
        raise HTTPException(422, "ids must be comma-separated integers") from exc
    audits = {a.id: a for a in session.scalars(select(Audit).where(Audit.id.in_(wanted)))}
    rows = []
    for audit_id in wanted:
        audit = audits.get(audit_id)
        if audit and audit.status == "done" and audit.report:
            m = audit.report["metrics"]
            rows.append(CompareRow(
                id=audit.id,
                url=audit.final_url or audit.url,
                created_at=audit.created_at,
                scores=audit.report["scores"],
                metrics={k: m[k] for k in ("ttfb_ms", "load_ms", "page_weight_kb", "request_count", "dom_elements")}
                | {"broken_links": audit.report["links"]["broken"]},
                issue_counts=audit.report["issue_counts"],
            ))
    return rows


# In production the built frontend is served from the same origin, so /api needs no CORS or proxy.
if settings.static_dir and (static := Path(settings.static_dir)).is_dir():
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (static / path).resolve()
        if path and file.is_file() and file.is_relative_to(static.resolve()):
            return FileResponse(file)
        return FileResponse(static / "index.html")  # client-side routes like /report/3
