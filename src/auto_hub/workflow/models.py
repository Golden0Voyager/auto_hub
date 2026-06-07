from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):  # noqa: UP042
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class StepSpec(BaseModel):
    name: str
    project: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 600
    retry_limit: int = 2
    dependencies: list[str] = Field(default_factory=list)


class StepResult(BaseModel):
    step_name: str
    status: JobStatus
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    output: str = ""
    error: str = ""
    retry_count: int = 0
    artifact_paths: dict[str, str] = Field(default_factory=dict)


class ArtifactManifest(BaseModel):
    title: str = ""
    source_url: str = ""
    source_project: str = ""
    language: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    updated_at: str = ""
    pipeline: list[str] = Field(default_factory=list)
    job_status: JobStatus = JobStatus.pending
    steps: list[StepResult] = Field(default_factory=list)


class JobSpec(BaseModel):
    pipeline: list[StepSpec]
    manifest: ArtifactManifest = Field(default_factory=ArtifactManifest)
    work_dir: str = ""


class WorkflowError(Exception):
    def __init__(self, message: str, step: str | None = None):
        self.step = step
        super().__init__(message)
