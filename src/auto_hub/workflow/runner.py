from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from auto_hub.workflow.models import (
    ArtifactManifest,
    JobSpec,
    JobStatus,
    StepResult,
    StepSpec,
    WorkflowError,
)

logger = logging.getLogger("auto_hub.workflow")


class JobRunner:
    """Execute a multi-step workflow with resumable artifacts.

    Directory layout per job::

        <work_dir>/<job_id>/
            manifest.json       # ArtifactManifest — job state
            source/             # original inputs
            intermediate/       # per-step outputs
            output/             # final outputs
            assets/             # supporting files
            logs/               # per-step stdout/stderr
    """

    def __init__(self, job_spec: JobSpec, job_id: str | None = None):
        self.job_spec = job_spec
        self.job_id = job_id or _generate_job_id()
        self._base_dir: Path | None = None

    @property
    def base_dir(self) -> Path:
        if self._base_dir is None:
            root = Path(self.job_spec.work_dir) if self.job_spec.work_dir else Path.cwd()
            self._base_dir = root / self.job_id
        return self._base_dir

    def ensure_dirs(self) -> None:
        for sub in ("source", "intermediate", "output", "assets", "logs"):
            (self.base_dir / sub).mkdir(parents=True, exist_ok=True)

    def load_manifest(self) -> ArtifactManifest:
        path = self.base_dir / "manifest.json"
        if path.exists():
            return ArtifactManifest(**json.loads(path.read_text()))
        return self.job_spec.manifest

    def save_manifest(self, manifest: ArtifactManifest) -> None:
        self.ensure_dirs()
        manifest.updated_at = datetime.now(UTC).isoformat()
        path = self.base_dir / "manifest.json"
        path.write_text(manifest.model_dump_json(indent=2, by_alias=True))

    def run(self) -> ArtifactManifest:
        manifest = self.load_manifest()
        manifest.job_status = JobStatus.running
        self.save_manifest(manifest)

        try:
            for step in self.job_spec.pipeline:
                existing = self._find_step_result(manifest, step.name)
                if existing and existing.status == JobStatus.completed:
                    logger.info("Step '%s' already completed, skipping", step.name)
                    continue

                result = self._execute_step(step)
                self._upsert_step_result(manifest, result)
                self.save_manifest(manifest)

                if result.status == JobStatus.failed:
                    manifest.job_status = JobStatus.failed
                    self.save_manifest(manifest)
                    raise WorkflowError(
                        f"Step '{step.name}' failed (exit={result.exit_code})",
                        step=step.name,
                    )

            manifest.job_status = JobStatus.completed
        except WorkflowError:
            pass
        except Exception as e:
            manifest.job_status = JobStatus.failed
            logger.exception("Workflow failed unexpectedly: %s", e)

        self.save_manifest(manifest)
        return manifest

    def run_step(self, step_name: str) -> StepResult:
        step = next((s for s in self.job_spec.pipeline if s.name == step_name), None)
        if step is None:
            raise WorkflowError(f"Step '{step_name}' not found in pipeline")
        result = self._execute_step(step)
        manifest = self.load_manifest()
        self._upsert_step_result(manifest, result)
        self.save_manifest(manifest)
        return result

    def _execute_step(self, step: StepSpec) -> StepResult:
        logger.info("Running step '%s' (%s %s)", step.name, step.command, " ".join(step.args))
        result = StepResult(step_name=step.name, status=JobStatus.running)
        result.started_at = datetime.now(UTC).isoformat()

        self.ensure_dirs()
        log_path = self.base_dir / "logs" / f"{step.name}.log"

        for attempt in range(step.retry_limit + 1):
            if attempt > 0:
                logger.warning("Retrying step '%s' (attempt %d/%d)", step.name, attempt, step.retry_limit)
                time.sleep(1)

            try:
                proc = subprocess.run(
                    [step.command, *step.args],
                    capture_output=True,
                    text=True,
                    timeout=step.timeout_seconds,
                    env={**os.environ, **step.env},
                )
                log_path.write_text(proc.stdout + proc.stderr)
                result.output = proc.stdout
                result.error = proc.stderr
                result.retry_count = attempt
                result.exit_code = proc.returncode

                if proc.returncode == 0:
                    result.status = JobStatus.completed
                    result.finished_at = datetime.now(UTC).isoformat()
                    return result

            except subprocess.TimeoutExpired:
                log_path.write_text(f"TIMEOUT after {step.timeout_seconds}s\n")
                result.error = f"Timeout after {step.timeout_seconds}s"
                result.exit_code = -1

            except FileNotFoundError:
                result.error = f"Command not found: {step.command}"
                result.exit_code = -2
                result.status = JobStatus.failed
                result.finished_at = datetime.now(UTC).isoformat()
                return result

        result.status = JobStatus.failed
        result.finished_at = datetime.now(UTC).isoformat()
        return result

    @staticmethod
    def _find_step_result(manifest: ArtifactManifest, step_name: str) -> StepResult | None:
        for s in manifest.steps:
            if s.step_name == step_name:
                return s
        return None

    @staticmethod
    def _upsert_step_result(manifest: ArtifactManifest, result: StepResult) -> None:
        for i, s in enumerate(manifest.steps):
            if s.step_name == result.step_name:
                manifest.steps[i] = result
                return
        manifest.steps.append(result)


def _generate_job_id() -> str:
    return f"job-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
