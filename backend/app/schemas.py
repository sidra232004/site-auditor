from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _assume_utc(value: datetime | None) -> datetime | None:
    # SQLite drops tzinfo; every timestamp is stored in UTC, so restore it before serializing.
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


UTCDateTime = Annotated[datetime, AfterValidator(_assume_utc)]


class AuditCreate(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048, examples=["https://example.com"])


class AuditSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    final_url: str | None
    status: str
    progress: str | None
    error: str | None
    overall_score: float | None
    scores: dict[str, Any] | None
    created_at: UTCDateTime
    completed_at: UTCDateTime | None


class AuditDetail(AuditSummary):
    report: dict[str, Any] | None


class CompareRow(BaseModel):
    id: int
    url: str
    created_at: UTCDateTime
    scores: dict[str, Any]
    metrics: dict[str, Any]
    issue_counts: dict[str, int]
