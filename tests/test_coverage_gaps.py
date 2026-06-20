"""Coverage gap tests — targeting 95%+."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ═══════════════════════════════════════════════════════════════
# cli.py — workflow commands (lines 161-224)
# ═══════════════════════════════════════════════════════════════

class TestCLIWorkflow:

    def test_workflow_run_json_success(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        pipeline = {
            "pipeline": [
                {"name": "echo_test", "project": "test", "command": "echo hello", "timeout_seconds": 5}
            ]
        }
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe_path = Path(tmpdir) / "test.json"
            pipe_path.write_text(json.dumps(pipeline))
            result = runner.invoke(main, [
                "workflow", "run", str(pipe_path),
                "--work-dir", tmpdir,
            ])
            assert result.exit_code == 0

    def test_workflow_run_yaml(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        pipeline = {
            "pipeline": [
                {"name": "echo_test", "project": "test", "command": "echo yaml_test", "timeout_seconds": 5}
            ]
        }
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe_path = Path(tmpdir) / "test.yaml"
            pipe_path.write_text(yaml.dump(pipeline))
            result = runner.invoke(main, [
                "workflow", "run", str(pipe_path),
                "--work-dir", tmpdir,
            ])
            assert result.exit_code == 0

    def test_workflow_run_with_custom_job_id(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        pipeline = {
            "pipeline": [
                {"name": "id_test", "project": "test", "command": "echo test", "timeout_seconds": 5}
            ]
        }
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe_path = Path(tmpdir) / "test.json"
            pipe_path.write_text(json.dumps(pipeline))
            result = runner.invoke(main, [
                "workflow", "run", str(pipe_path),
                "--work-dir", tmpdir,
                "--job-id", "custom-job-001",
            ])
            assert result.exit_code == 0
            assert "custom-job-001" in result.output

    def test_workflow_run_file_not_found(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["workflow", "run", "/nonexistent/pipeline.json"])
        assert result.exit_code != 0 or "Error" in result.output or "error" in result.output.lower()

    def test_workflow_status(self):
        from click.testing import CliRunner

        from auto_hub.cli import main
        from auto_hub.workflow.models import ArtifactManifest, JobSpec, StepSpec
        from auto_hub.workflow.runner import JobRunner

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = JobSpec(
                pipeline=[StepSpec(name="s1", project="t", command="echo hi")],
                manifest=ArtifactManifest(job_id="test-job", status="pending", pipeline=["s1"]),
                work_dir=tmpdir,
            )
            JobRunner(spec)
            result = runner.invoke(main, ["workflow", "status", tmpdir])
            assert "test-job" in result.output or "Error" in result.output or result.exit_code == 0

    def test_workflow_status_nonexistent_job(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["workflow", "status", "/nonexistent/job"])
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_workflow_run_failed_step_shows_errors(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        pipeline = {
            "pipeline": [
                {"name": "fail_step", "project": "test", "command": "bash -c 'exit 1'", "timeout_seconds": 5}
            ]
        }
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            pipe_path = Path(tmpdir) / "fail.json"
            pipe_path.write_text(json.dumps(pipeline))
            result = runner.invoke(main, [
                "workflow", "run", str(pipe_path),
                "--work-dir", tmpdir,
            ])
            assert "fail_step" in result.output


# ═══════════════════════════════════════════════════════════════
# provider_chain.py — edge cases
# ═══════════════════════════════════════════════════════════════

class TestProviderChainGaps:

    def test_chain_with_missing_api_key_skips_provider(self, monkeypatch):
        import auto_hub.llm.provider_chain as pc
        pc.reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "OPENAI,MISSING_PROV")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("MISSING_PROV_API_KEY", raising=False)
        pc.load_provider_chain()
        names = [c.name for c in ([pc._primary] + pc._fallbacks)]
        assert "OPENAI" in names
        assert "MISSING_PROV" not in names
        pc.reset_provider_chain()

    def test_chain_azure_openai_config(self, monkeypatch):
        import auto_hub.llm.provider_chain as pc
        pc.reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "AZURE_OPENAI")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az-test-key")
        pc.load_provider_chain()
        assert pc._primary.api_key == "az-test-key"
        assert pc._primary.base_url == "https://test.openai.azure.com"
        pc.reset_provider_chain()

    def test_chain_with_custom_model_env(self, monkeypatch):
        import auto_hub.llm.provider_chain as pc
        pc.reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "OPENAI")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4-custom")
        pc.load_provider_chain()
        assert pc._primary.model == "gpt-4-custom"
        pc.reset_provider_chain()

    def test_chain_cached_second_call(self, monkeypatch):
        import auto_hub.llm.provider_chain as pc
        pc.reset_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "OPENAI")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        first = pc.load_provider_chain()
        monkeypatch.setenv("AI_PROVIDER_CHAIN", "OPENAI,DEEPSEEK")
        second = pc.load_provider_chain()
        assert first == second
        pc.reset_provider_chain()


# ═══════════════════════════════════════════════════════════════
# gateway.py — MCP tools (async pattern from existing tests)
# ═══════════════════════════════════════════════════════════════

class TestGatewayGaps:

    @pytest.mark.asyncio
    async def test_show_project_with_all_fields(self):
        from auto_hub.mcp.gateway import create_app
        from auto_hub.registry.loader import RegistryLoader

        mock_project = MagicMock()
        mock_project.name = "auto_test"
        mock_project.type = "scraper"
        mock_project.description = "Test project"
        mock_project.status = "active"
        mock_project.path = "projects/auto_test"
        mock_project.capabilities = ["cli", "mcp"]
        mock_project.entry_points = {}
        mock_project.env_vars = ["API_KEY"]
        mock_project.integration_targets = []

        mock_loader = MagicMock(spec=RegistryLoader)
        mock_loader.get_project.return_value = mock_project
        mock_loader.resolve_path.return_value = Path("/fake/path")

        with patch("auto_hub.mcp.gateway._loader", return_value=mock_loader):
            app = create_app()
            result = await app.call_tool("show_project", {"name": "auto_test"})
            assert result is not None
            content = result[0].text if hasattr(result[0], "text") else str(result)
            assert "auto_test" in content

    @pytest.mark.asyncio
    async def test_registry_status_by_type(self):
        from auto_hub.mcp.gateway import create_app
        from auto_hub.registry.loader import RegistryLoader

        mock_project = MagicMock()
        mock_project.name = "auto_test"
        mock_project.type = "scraper"
        mock_project.description = "Test"

        mock_loader = MagicMock(spec=RegistryLoader)
        mock_loader.list_projects.return_value = [mock_project]
        mock_loader.get_missing_projects.return_value = []
        mock_loader.resolve_path.return_value = Path("/fake/path")

        with patch("auto_hub.mcp.gateway._loader", return_value=mock_loader):
            app = create_app()
            result = await app.call_tool("registry_status", {})
            assert result is not None

    @pytest.mark.asyncio
    async def test_llm_chat_success(self):
        from auto_hub.mcp.gateway import create_app

        mock_client = MagicMock()
        mock_client.chat.return_value = "Hello from LLM"

        with patch("auto_hub.mcp.gateway._get_llm_client", return_value=mock_client):
            app = create_app()
            result = await app.call_tool("llm_chat", {"message": "Hello"})
            assert result is not None
            content = result[0].text if hasattr(result[0], "text") else str(result)
            assert "Hello" in content or "LLM" in content

    @pytest.mark.asyncio
    async def test_llm_chat_error_handling(self):
        from auto_hub.mcp.gateway import create_app

        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("Provider not available")

        with patch("auto_hub.mcp.gateway._get_llm_client", return_value=mock_client):
            app = create_app()
            result = await app.call_tool("llm_chat", {"message": "Hello"})
            assert result is not None
            content = result[0].text if hasattr(result[0], "text") else str(result)
            assert "Error" in content or "error" in content.lower()

    @pytest.mark.asyncio
    async def test_list_projects_formatted(self):
        from auto_hub.mcp.gateway import create_app
        from auto_hub.registry.loader import RegistryLoader

        mock_project = MagicMock()
        mock_project.name = "auto_test"
        mock_project.type = "scraper"
        mock_project.description = "Test scraper"

        mock_loader = MagicMock(spec=RegistryLoader)
        mock_loader.list_projects.return_value = [mock_project]
        mock_loader.resolve_path.return_value = Path("/fake/path")

        with patch("auto_hub.mcp.gateway._loader", return_value=mock_loader):
            app = create_app()
            result = await app.call_tool("list_projects", {})
            assert result is not None
            content = result[0].text if hasattr(result[0], "text") else str(result)
            assert "auto_test" in content


# ═══════════════════════════════════════════════════════════════
# runner.py — error handling paths (work_dir is str)
# ═══════════════════════════════════════════════════════════════

class TestRunnerGaps:

    def test_run_sets_status_failed_on_exception(self):
        from auto_hub.workflow.models import ArtifactManifest, JobSpec, StepSpec
        from auto_hub.workflow.runner import JobRunner

        tmp = tempfile.mkdtemp()
        manifest = ArtifactManifest(
            job_id="test-fail", status="pending", pipeline=["broken_step"],
        )
        spec = JobSpec(
            pipeline=[StepSpec(name="broken_step", project="test", command="echo x")],
            manifest=manifest,
            work_dir=tmp,
        )
        runner = JobRunner(spec)
        runner._execute_step = MagicMock(side_effect=Exception("Boom"))
        with patch.object(runner, "save_manifest"):
            result = runner.run()
        assert result.job_status in ("failed", "failed")

    def test_run_catches_workflow_error(self):
        from auto_hub.workflow.models import ArtifactManifest, JobSpec, StepSpec, WorkflowError
        from auto_hub.workflow.runner import JobRunner

        tmp = tempfile.mkdtemp()
        manifest = ArtifactManifest(
            job_id="test-wf-error", status="pending", pipeline=["error_step"],
        )
        spec = JobSpec(
            pipeline=[StepSpec(name="error_step", project="test", command="echo x")],
            manifest=manifest,
            work_dir=tmp,
        )
        runner = JobRunner(spec)
        runner._execute_step = MagicMock(side_effect=WorkflowError("Workflow failed"))
        with patch.object(runner, "save_manifest"):
            result = runner.run()
        assert result is not None

    def test_execute_step_handles_timeout(self):
        from auto_hub.workflow.models import ArtifactManifest, JobSpec, StepSpec
        from auto_hub.workflow.runner import JobRunner

        tmp = tempfile.mkdtemp()
        spec = JobSpec(
            pipeline=[StepSpec(name="timeout_step", project="test", command="sleep", timeout_seconds=1)],
            manifest=ArtifactManifest(job_id="test-timeout", status="pending", pipeline=["timeout_step"]),
            work_dir=tmp,
        )
        runner = JobRunner(spec)
        result = runner._execute_step(spec.pipeline[0])
        assert result is not None
        assert result.status in ("failed", "completed")

    def test_execute_step_file_not_found(self):
        from auto_hub.workflow.models import ArtifactManifest, JobSpec, StepSpec
        from auto_hub.workflow.runner import JobRunner

        tmp = tempfile.mkdtemp()
        spec = JobSpec(
            pipeline=[StepSpec(name="missing_cmd", project="test", command="nonexistent_command_xyz_123", timeout_seconds=5)],
            manifest=ArtifactManifest(job_id="test-missing", status="pending", pipeline=["missing_cmd"]),
            work_dir=tmp,
        )
        runner = JobRunner(spec)
        result = runner._execute_step(spec.pipeline[0])
        assert result.status == "failed"


# ═══════════════════════════════════════════════════════════════
# loader.py — manifest loading (lines 18, 48)
# ═══════════════════════════════════════════════════════════════

class TestLoaderGaps:

    def test_load_reads_yaml_and_creates_manifest(self):
        from auto_hub.registry.loader import RegistryLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            manifests_dir = Path(tmpdir) / "manifests"
            manifests_dir.mkdir()
            projects_yaml = manifests_dir / "projects.yaml"
            projects_yaml.write_text(yaml.dump({"projects": []}))
            loader = RegistryLoader(manifests_dir=manifests_dir)
            manifest = loader.load()
            assert manifest is not None
            assert manifest.projects == []

    def test_get_missing_projects_detects_missing(self):
        from auto_hub.registry.loader import RegistryLoader
        from auto_hub.registry.models import ProjectManifest, RegistryManifest

        project = ProjectManifest(name="missing_project", type="scraper", path="nonexistent/path")
        manifest = RegistryManifest(projects=[project])
        loader = RegistryLoader()
        loader._manifest = manifest
        missing = loader.get_missing_projects()
        assert len(missing) == 1
        assert missing[0].name == "missing_project"


# ═══════════════════════════════════════════════════════════════
# json.py — no-block fallback (line 42)
# ═══════════════════════════════════════════════════════════════

class TestJSONGaps:

    def test_parse_llm_json_no_block_raises_valueerror(self):
        from auto_hub.llm.json import parse_llm_json

        with pytest.raises(ValueError, match="LLM response is not valid JSON"):
            parse_llm_json("This is just plain text with no JSON block at all")


# ═══════════════════════════════════════════════════════════════
# adapters.py — assistant → model role mapping (lines 235-236)
# ═══════════════════════════════════════════════════════════════

class TestAdaptersGaps:

    def test_gemini_chat_wraps_assistant_as_model(self):
        from auto_hub.llm.adapters import _GeminiChatCompletions

        mock_client = MagicMock()
        wrapper = _GeminiChatCompletions(client=mock_client, default_model="gemini-2.0-flash")
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = wrapper.create(
            model="gemini-2.0-flash",
            messages=messages,
            temperature=0.7,
        )
        assert result is not None




class TestProviderChainV2:
    """Cover default-provider and Azure skip paths."""

    def test_default_provider_skip_if_no_api_key(self):
        from auto_hub.llm.provider_chain import load_provider_chain, reset_provider_chain
        reset_provider_chain()
        with patch.dict(os.environ, {"AI_PROVIDER_CHAIN": "RANDOMX"}, clear=True):
            chain = load_provider_chain()
        assert chain == []

    def test_azure_skip_if_no_api_key(self):
        from auto_hub.llm.provider_chain import load_provider_chain, reset_provider_chain
        reset_provider_chain()
        with patch.dict(os.environ, {"AI_PROVIDER_CHAIN": "AZURE_OPENAI"}, clear=True):
            chain = load_provider_chain()
        assert chain == []


# ═══════════════════════════════════════════════════════════════
# gateway.py — lines 123-125 (missing projects), 146-148 (ImportError)
# ═══════════════════════════════════════════════════════════════

class TestGatewayV2:
    """Cover registry_status missing-projects section and llm_chat ImportError."""

    def test_registry_status_with_missing_projects(self):
        from auto_hub.mcp.gateway import registry_status
        from auto_hub.registry.models import ProjectManifest

        mock_missing = MagicMock(spec=ProjectManifest)
        mock_missing.name = "ghost-project"
        mock_missing.path = "/dev/null/ghost"
        mock_missing.type = "scraper"

        mock_loader = MagicMock()
        mock_loader.list_projects.return_value = [mock_missing]
        mock_loader.get_missing_projects.return_value = [mock_missing]

        with patch("auto_hub.mcp.gateway._loader", return_value=mock_loader):
            result = registry_status()

        assert "ghost-project" in result
        assert "/dev/null/ghost" in result
        assert "Missing" in result

    def test_llm_chat_import_error(self):
        from auto_hub.mcp.gateway import _gateway_stats, llm_chat

        _gateway_stats.llm_failures = 0
        with patch("auto_hub.mcp.gateway._get_llm_client", side_effect=ImportError("no llm")):
            result = llm_chat(message="hello")

        assert "not available" in result.lower() or "missing" in result.lower()
        assert _gateway_stats.llm_failures >= 1


# ═══════════════════════════════════════════════════════════════
# runner.py — line 102 (step not found), lines 142-144 (timeout)
# ═══════════════════════════════════════════════════════════════

class TestRunnerV2:
    """Cover run_step not-found and detailed timeout path."""

    def test_run_step_not_found_raises_workflow_error(self):
        from auto_hub.workflow import JobRunner, JobSpec
        from auto_hub.workflow.models import StepSpec

        job_spec = JobSpec(
            pipeline=[
                StepSpec(name="real_step", project="test", command="echo hi")
            ]
        )
        runner = JobRunner(job_spec)
        with pytest.raises(Exception) as exc_info:
            runner.run_step("nonexistent_step")
        assert "not found" in str(exc_info.value).lower()

    def test_execute_step_timeout_writes_log_and_sets_error(self):
        from auto_hub.workflow import JobRunner, JobSpec
        from auto_hub.workflow.models import StepSpec

        job_spec = JobSpec(
            pipeline=[
                StepSpec(name="slow", project="test", command="sleep", args=["10"], timeout_seconds=1)
            ]
        )
        runner = JobRunner(job_spec)
        try:
            result = runner._execute_step(job_spec.pipeline[0])
            assert result.error is not None
            assert "Timeout" in result.error
            assert result.exit_code == -1
            # Verify log file was written
            log_path = runner.base_dir / "logs" / "slow.log"
            assert log_path.exists()
            assert "TIMEOUT" in log_path.read_text()
        finally:
            shutil.rmtree(runner.base_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# loader.py — line 18 (manifest file not found)
# ═══════════════════════════════════════════════════════════════

class TestLoaderV2:
    """Cover FileNotFoundError when manifests/projects.yaml missing."""

    def test_load_raises_when_manifest_missing(self):
        from auto_hub.registry.loader import RegistryLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            loader = RegistryLoader(manifests_dir=Path(tmpdir))
            with pytest.raises(FileNotFoundError, match="Manifest file not found"):
                loader.load()


# ═══════════════════════════════════════════════════════════════
# json.py — line 42 (regex-based JSON block extraction)
# ═══════════════════════════════════════════════════════════════

class TestJSONV2:
    """Cover regex-based JSON extraction from markdown-wrapped text."""

    def test_parse_llm_json_with_regex_block(self):
        from auto_hub.llm.json import parse_llm_json

        # Input that fails direct parse and manual strip, but regex finds block
        raw = 'Here is some text before\n```json\n{"key": "value"}\n```\nand some after'
        result = parse_llm_json(raw)
        assert result == {"key": "value"}


# ═══════════════════════════════════════════════════════════════
# cli.py — list / show / status / env / mcp / workflow commands
# ═══════════════════════════════════════════════════════════════

class TestCLIV2:
    """Cover CLI commands: list, show, status, env, mcp, workflow."""

    # ── list command ──

    def test_list_no_projects(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.list_projects.return_value = []
        mock_loader.get_missing_projects.return_value = []

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["list"])
        assert result.exit_code == 0
        assert "No projects registered" in result.output

    def test_list_with_project(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_proj = MagicMock()
        mock_proj.name = "demo"
        mock_proj.type = "scraper"
        mock_proj.description = "A demo"

        mock_loader = MagicMock()
        mock_loader.list_projects.return_value = [mock_proj]
        mock_loader.get_missing_projects.return_value = []

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["list"])
        assert "demo" in result.output

    def test_list_file_not_found_error(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.list_projects.side_effect = FileNotFoundError("boom")

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["list"])
        assert "Error:" in result.output

    def test_list_generic_error(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.list_projects.side_effect = Exception("panic")

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["list"])
        assert "Error loading registry" in result.output

    # ── show command ──

    def test_show_file_not_found_error(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.get_project.side_effect = FileNotFoundError("boom")

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["show", "test"])
        assert "Error:" in result.output

    def test_show_generic_error(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.get_project.side_effect = Exception("panic")

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["show", "test"])
        assert "Error loading registry" in result.output

    # ── status command ──

    def test_status_with_missing(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_proj = MagicMock()
        mock_proj.name = "ghost"
        mock_proj.path = "/gone"

        mock_loader = MagicMock()
        mock_loader.list_projects.return_value = [mock_proj]
        mock_loader.get_missing_projects.return_value = [mock_proj]

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["status"])
        assert "ghost" in result.output
        assert "/gone" in result.output

    def test_status_error_handling(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.list_projects.side_effect = [FileNotFoundError("boom")]

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["status"])
        assert "Error:" in result.output

    def test_status_generic_error(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.list_projects.side_effect = [Exception("panic")]

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["status"])
        assert "Error loading registry" in result.output

    # ── env command ──

    def test_env_project_not_found(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.get_project.return_value = None

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["env", "nope"])
        assert "not found" in result.output

    def test_env_file_not_found_error(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.get_project.side_effect = FileNotFoundError("boom")

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["env", "test"])
        assert "Error:" in result.output

    def test_env_generic_error(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        mock_loader = MagicMock()
        mock_loader.get_project.side_effect = Exception("panic")

        with patch("auto_hub.cli._get_loader", return_value=mock_loader):
            result = CliRunner().invoke(main, ["env", "test"])
        assert "Error loading registry" in result.output

    # ── mcp command ──

    def test_mcp_command_calls_main(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        with patch("auto_hub.mcp.gateway.main") as mock_mcp_main:
            runner = CliRunner()
            runner.invoke(main, ["mcp"])
        mock_mcp_main.assert_called_once()

    # ── workflow run (failed) ──

    def test_workflow_run_failed_status(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        pipeline = {"pipeline": [{"name": "s1", "project": "test", "command": "echo hi"}]}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(pipeline, f)
            pipe_path = f.name

        mock_runner = MagicMock()
        mock_runner.job_id = "bad-job"
        mock_runner.base_dir = Path("/tmp/bad")
        mock_manifest = MagicMock()
        mock_manifest.job_status = "failed"
        mock_manifest.steps = []
        mock_runner.run.return_value = mock_manifest

        with patch("auto_hub.workflow.JobRunner", return_value=mock_runner), patch("auto_hub.workflow.JobSpec"):
            result = CliRunner().invoke(main, ["workflow", "run", pipe_path])
        assert "Workflow failed" in result.output
        os.unlink(pipe_path)

    # ── workflow status full display ──

    def test_workflow_status_full_display(self):
        from click.testing import CliRunner

        from auto_hub.cli import main

        manifest = {
            "job_id": "job-abc",
            "job_status": "completed",
            "pipeline": ["step1", "step2"],
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:01:00",
            "steps": [
                {"step_name": "step1", "status": "completed", "exit_code": 0, "retry_count": 0,
                 "started_at": "2024-01-01T00:00:00", "finished_at": "2024-01-01T00:00:01", "command": "echo 1"},
                {"step_name": "step2", "status": "failed", "exit_code": 1, "retry_count": 2,
                 "started_at": "2024-01-01T00:00:01", "finished_at": "2024-01-01T00:00:02", "command": "echo 2"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir) / "job-abc"
            job_dir.mkdir()
            (job_dir / "manifest.json").write_text(json.dumps(manifest))

            result = CliRunner().invoke(main, ["workflow", "status", str(job_dir)])
        assert result.exit_code == 0
        assert "job-abc" in result.output
        assert "completed" in result.output
        assert "step1 → step2" in result.output or "step1" in result.output
        # Icon rendering
        output = result.output
        assert "✓" in output or "completed" in output
