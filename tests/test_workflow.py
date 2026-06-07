"""Tests for the content workflow layer."""

from __future__ import annotations

import json
import tempfile

from auto_hub.workflow import (
    ArtifactManifest,
    JobRunner,
    JobSpec,
    JobStatus,
    StepResult,
    StepSpec,
    WorkflowError,
)


class TestModels:
    def test_step_spec_defaults(self):
        s = StepSpec(name="test", project="auto_pdf", command="echo")
        assert s.args == []
        assert s.env == {}
        assert s.timeout_seconds == 600
        assert s.retry_limit == 2

    def test_artifact_manifest_defaults(self):
        m = ArtifactManifest()
        assert m.job_status == JobStatus.pending
        assert m.pipeline == []
        assert m.steps == []
        assert m.title == ""

    def test_artifact_manifest_auto_timestamps(self):
        m = ArtifactManifest()
        assert m.created_at != ""

    def test_step_result_defaults(self):
        r = StepResult(step_name="build", status=JobStatus.pending)
        assert r.exit_code is None
        assert r.output == ""
        assert r.retry_count == 0

    def test_job_spec_defaults(self):
        spec = JobSpec(pipeline=[])
        assert spec.work_dir == ""
        assert spec.manifest.job_status == JobStatus.pending

    def test_workflow_error(self):
        e = WorkflowError("oops", step="build")
        assert str(e) == "oops"
        assert e.step == "build"


class TestJobRunner:
    def test_job_id_generation(self):
        runner = JobRunner(JobSpec(pipeline=[]))
        assert runner.job_id.startswith("job-")

    def test_explicit_job_id(self):
        runner = JobRunner(JobSpec(pipeline=[]), job_id="my-custom-id")
        assert runner.job_id == "my-custom-id"

    def test_base_dir_uses_work_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            assert str(tmp) in str(runner.base_dir)
            assert runner.base_dir.name == "test-job"

    def test_base_dir_defaults_to_cwd(self):
        runner = JobRunner(JobSpec(pipeline=[]), job_id="test-job")
        assert runner.base_dir.name == "test-job"

    def test_ensure_dirs_creates_subdirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            runner.ensure_dirs()
            for sub in ("source", "intermediate", "output", "assets", "logs"):
                assert (runner.base_dir / sub).is_dir()

    def test_save_and_load_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            manifest = ArtifactManifest(title="My Test", pipeline=["step1"])
            runner.save_manifest(manifest)
            assert (runner.base_dir / "manifest.json").exists()

            loaded = runner.load_manifest()
            assert loaded.title == "My Test"
            assert loaded.pipeline == ["step1"]

    def test_execute_step_success(self):
        step = StepSpec(name="hello", project="test", command="echo", args=["hello world"])
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[step], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            result = runner._execute_step(step)
            assert result.status == JobStatus.completed
            assert result.exit_code == 0
            assert "hello world" in result.output

    def test_execute_step_failure(self):
        step = StepSpec(name="fail", project="test", command="bash", args=["-c", "exit 1"])
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[step], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            result = runner._execute_step(step)
            assert result.status == JobStatus.failed
            assert result.exit_code == 1

    def test_execute_step_command_not_found(self):
        step = StepSpec(name="nope", project="test", command="nonexistent_cmd_xyz")
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[step], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            result = runner._execute_step(step)
            assert result.status == JobStatus.failed
            assert result.exit_code == -2

    def test_execute_step_creates_log_file(self):
        step = StepSpec(name="loggy", project="test", command="echo", args=["hi"])
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[step], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            runner._execute_step(step)
            log_file = runner.base_dir / "logs" / "loggy.log"
            assert log_file.exists()
            assert log_file.read_text().strip() == "hi"

    def test_run_completes_all_steps(self):
        steps = [
            StepSpec(name="a", project="test", command="echo", args=["alpha"]),
            StepSpec(name="b", project="test", command="echo", args=["beta"]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=steps, work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            manifest = runner.run()
            assert manifest.job_status == JobStatus.completed
            assert len(manifest.steps) == 2
            for s in manifest.steps:
                assert s.status == JobStatus.completed

    def test_run_stops_on_failure(self):
        steps = [
            StepSpec(name="good", project="test", command="echo", args=["ok"]),
            StepSpec(name="bad", project="test", command="bash", args=["-c", "exit 1"]),
            StepSpec(name="never", project="test", command="echo", args=["should not run"]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=steps, work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            manifest = runner.run()
            assert manifest.job_status == JobStatus.failed
            assert len(manifest.steps) == 2
            assert manifest.steps[0].status == JobStatus.completed
            assert manifest.steps[1].status == JobStatus.failed

    def test_run_retries_on_failure(self):
        step = StepSpec(
            name="retry", project="test", command="bash",
            args=["-c", "exit 1"],
            retry_limit=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[step], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            result = runner._execute_step(step)
            assert result.status == JobStatus.failed
            assert result.retry_count == 1

    def test_run_step_individually(self):
        step = StepSpec(name="solo", project="test", command="echo", args=["solo run"])
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[step], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            result = runner.run_step("solo")
            assert result.status == JobStatus.completed
            manifest = runner.load_manifest()
            assert len(manifest.steps) == 1

    def test_skip_completed_steps(self):
        steps = [
            StepSpec(name="a", project="test", command="echo", args=["alpha"]),
            StepSpec(name="b", project="test", command="bash", args=["-c", "exit 1"]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=steps, work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")

            manifest = runner.run()
            assert manifest.job_status == JobStatus.failed
            assert manifest.steps[0].status == JobStatus.completed
            assert manifest.steps[1].status == JobStatus.failed

            runner2 = JobRunner(spec, job_id=runner.job_id)
            runner2._base_dir = runner.base_dir
            manifest2 = runner2.run()
            assert len(manifest2.steps) == 2

    def test_manifest_persists_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(
                pipeline=[
                    StepSpec(name="a", project="test", command="echo", args=["first"]),
                ],
                work_dir=tmp,
            )
            runner = JobRunner(spec, job_id="persist-test")
            runner.run()
            manifest_path = runner.base_dir / "manifest.json"
            assert manifest_path.exists()
            data = json.loads(manifest_path.read_text())
            assert len(data["steps"]) == 1
            assert data["steps"][0]["step_name"] == "a"
            assert data["steps"][0]["status"] == "completed"

    def test_run_with_env_override(self):
        step = StepSpec(
            name="env-test", project="test", command="bash",
            args=["-c", "echo $MY_VAR"],
            env={"MY_VAR": "hello-env"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            spec = JobSpec(pipeline=[step], work_dir=tmp)
            runner = JobRunner(spec, job_id="test-job")
            result = runner._execute_step(step)
            assert result.output.strip() == "hello-env"
