"""Pydantic request/response models and internal data types."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl, field_validator, model_validator


# --- API request/response schemas ---


class UserOut(BaseModel):
    id: int
    username: str


class TargetCreate(BaseModel):
    url: HttpUrl
    name: str  # user-provided display name


class TargetOut(BaseModel):
    id: int
    url: str
    name: str
    created_at: datetime
    last_job_status: Optional[str]  # latest job status for dashboard display
    last_scraped_at: Optional[datetime]
    has_schedule: bool = False
    schedule_status: Optional[str] = None
    next_run_at: Optional[datetime] = None


class ScrapeJobOut(BaseModel):
    id: int
    target_id: int
    status: str  # "pending", "running", "complete", "failed"
    trigger: str = "manual"
    pages_found: int
    pages_scraped: int
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]


class SnapshotOut(BaseModel):
    id: int
    job_id: int
    storage_path: str
    file_count: int
    total_size_bytes: int
    created_at: datetime


_VALID_INTERVAL_TYPES = {"6h", "12h", "daily", "weekly", "cron"}
_CRON_FIELD_RE = re.compile(
    r"^(\*(/[0-9]+)?|[0-9]+(-[0-9]+)?(/[0-9]+)?(,[0-9]+(-[0-9]+)?(/[0-9]+)?)*)$"
)


class ScheduleCreate(BaseModel):
    interval_type: str
    cron_expression: Optional[str] = None

    @field_validator("interval_type")
    @classmethod
    def validate_interval_type(cls, v: str) -> str:
        if v not in _VALID_INTERVAL_TYPES:
            raise ValueError(
                f"interval_type must be one of {sorted(_VALID_INTERVAL_TYPES)}"
            )
        return v

    @model_validator(mode="after")
    def validate_cron(self) -> ScheduleCreate:
        if self.interval_type == "cron":
            if not self.cron_expression:
                raise ValueError(
                    "cron_expression is required when interval_type is 'cron'"
                )
            fields = self.cron_expression.strip().split()
            if len(fields) != 5:
                raise ValueError(
                    "cron_expression must be a valid 5-field cron string"
                )
            for field in fields:
                if not _CRON_FIELD_RE.match(field):
                    raise ValueError(
                        f"Invalid cron field: {field}"
                    )
        return self


class ScheduleToggle(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("active", "paused"):
            raise ValueError("status must be 'active' or 'paused'")
        return v


class ScheduleOut(BaseModel):
    id: int
    target_id: int
    interval_type: str
    cron_expression: Optional[str]
    status: str
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    last_run_status: Optional[str]
    created_at: datetime
    updated_at: datetime


# --- Internal types ---


class ScrapeResult(BaseModel):
    """Internal result returned by orchestrator."""

    job_id: int
    status: str
    pages_found: int
    pages_scraped: int
    pages_failed: int
    snapshot_path: Optional[str]
    error_message: Optional[str]


class FetchResult(BaseModel):
    """Per-page fetch outcome."""

    url: str
    html: Optional[str]
    status_code: Optional[int]
    error: Optional[str]
    success: bool


class PageContent(BaseModel):
    """Converted page ready for indexing."""

    url: str
    url_path: str  # path portion of URL, used for structured file layout
    markdown: str
