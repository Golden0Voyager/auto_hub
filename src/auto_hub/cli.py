
import click

from auto_hub.registry.loader import RegistryLoader


def _get_loader() -> RegistryLoader:
    return RegistryLoader()


@click.group()
def main():
    """auto_hub: central coordination layer for auto_* projects."""


@main.command(name="list")
def list_projects():
    """List all registered auto_* projects."""
    try:
        loader = _get_loader()
        projects = loader.list_projects()
        missing = loader.get_missing_projects()
        if not projects:
            click.echo("No projects registered.")
            return

        click.echo(f"Registered projects ({len(projects)}):")
        for p in projects:
            label = f"  {p.name}"
            label += f"  ({p.type})"
            label += f"  — {p.description}"
            if p in missing:
                label += "  [MISSING]"
            click.echo(label)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
    except Exception as e:
        click.echo(f"Error loading registry: {e}")


@main.command()
@click.argument("project_name")
def show(project_name: str):
    """Show metadata for a single project."""
    try:
        loader = _get_loader()
        project = loader.get_project(project_name)

        if project is None:
            click.echo(f"Project '{project_name}' not found.")
            return

        click.echo(f"Name:        {project.name}")
        click.echo(f"Type:        {project.type}")
        click.echo(f"Status:      {project.status}")
        click.echo(f"Description: {project.description}")
        click.echo(f"Path:        {project.path}")
        resolved = loader.resolve_path(project)
        exists = resolved.exists()
        click.echo(f"Resolved:    {resolved} {'[EXISTS]' if exists else '[MISSING]'}")

        if project.capabilities:
            click.echo(f"Capabilities ({len(project.capabilities)}):")
            for cap in project.capabilities:
                click.echo(f"  - {cap}")

        if project.entrypoints:
            click.echo("Entry points:")
            if project.entrypoints.cli:
                click.echo(f"  CLI:   {project.entrypoints.cli.command}")
            if project.entrypoints.web:
                click.echo(f"  Web:   {project.entrypoints.web.command}")
            if project.entrypoints.mcp:
                click.echo(f"  MCP:   {project.entrypoints.mcp.command}")

        if project.environment.required or project.environment.optional:
            click.echo("Environment:")
            for var in project.environment.required:
                click.echo(f"  [REQUIRED] {var}")
            for var in project.environment.optional:
                click.echo(f"  [optional] {var}")

        integration = project.integration
        if integration and (integration.shared_llm or integration.mcp or integration.workflow_node):
            click.echo("Integration targets:")
            if integration.shared_llm:
                click.echo(f"  shared_llm:    {integration.shared_llm}")
            if integration.mcp:
                click.echo(f"  mcp:           {integration.mcp}")
            if integration.workflow_node:
                click.echo(f"  workflow_node: {integration.workflow_node}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
    except Exception as e:
        click.echo(f"Error loading registry: {e}")


@main.command()
def status():
    """Show overall project health: missing dirs, etc."""
    try:
        loader = _get_loader()
        projects = loader.list_projects()
        missing = loader.get_missing_projects()
        total = len(projects)
        present = total - len(missing)

        click.echo(f"Registered: {total}")
        click.echo(f"Present:    {present}")
        if missing:
            click.echo(f"Missing:    {len(missing)}")
            for m in missing:
                click.echo(f"  - {m.name} ({m.path})")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
    except Exception as e:
        click.echo(f"Error loading registry: {e}")


@main.command()
@click.argument("project_name")
def env(project_name: str):
    """Show required/optional env vars for a project."""
    try:
        loader = _get_loader()
        project = loader.get_project(project_name)

        if project is None:
            click.echo(f"Project '{project_name}' not found.")
            return

        for var in project.environment.required:
            click.echo(f"{var} — required")
        for var in project.environment.optional:
            click.echo(f"{var} — optional")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
    except Exception as e:
        click.echo(f"Error loading registry: {e}")


@main.command()
def mcp():
    """Start the MCP aggregation gateway (stdio)."""
    from auto_hub.mcp.gateway import main as mcp_main
    mcp_main()


@main.group()
def workflow():
    """Manage content workflows."""


@workflow.command(name="run")
@click.option("--work-dir", default="", help="Working directory for job artifacts.")
@click.option("--job-id", default=None, help="Explicit job ID (auto-generated if omitted).")
@click.argument("pipeline_file", type=click.Path(exists=True))
def run_workflow(work_dir: str, job_id: str | None, pipeline_file: str):
    """Run a workflow from a JSON or YAML pipeline file."""
    import json
    from pathlib import Path

    try:
        import yaml
    except ImportError:
        yaml = None

    path = Path(pipeline_file)
    raw = path.read_text()

    data = yaml.safe_load(raw) if path.suffix in (".yaml", ".yml") and yaml else json.loads(raw)

    from auto_hub.workflow import JobRunner, JobSpec

    job_spec = JobSpec(**data)
    if work_dir:
        job_spec.work_dir = work_dir

    runner = JobRunner(job_spec, job_id=job_id)
    click.echo(f"Starting workflow: {runner.job_id}")
    click.echo(f"  Work dir: {runner.base_dir}")

    manifest = runner.run()

    if manifest.job_status == "completed":
        click.echo("Workflow completed successfully.")
    else:
        click.echo(f"Workflow failed: {manifest.job_status}")
        for step in manifest.steps:
            if step.status == "failed":
                click.echo(f"  Step '{step.step_name}' failed: {step.error[:200]}")


@workflow.command(name="status")
@click.argument("job_dir", type=click.Path(exists=True))
def workflow_status(job_dir: str):
    """Show status of a running/completed workflow job."""
    import json
    from pathlib import Path

    manifest_path = Path(job_dir) / "manifest.json"
    if not manifest_path.exists():
        click.echo(f"No manifest.json found in {job_dir}")
        return

    data = json.loads(manifest_path.read_text())

    from auto_hub.workflow import ArtifactManifest

    manifest = ArtifactManifest(**data)
    click.echo(f"Job ID:       {Path(job_dir).name}")
    click.echo(f"Status:       {manifest.job_status.value}")
    click.echo(f"Pipeline:     {' → '.join(manifest.pipeline)}")
    click.echo(f"Created:      {manifest.created_at}")
    click.echo(f"Updated:      {manifest.updated_at}")
    click.echo("---")
    for step in manifest.steps:
        icon = {"completed": "✓", "failed": "✗", "running": "▶", "pending": "○"}.get(
            step.status.value, "?"
        )
        click.echo(f"  {icon} {step.step_name} ({step.status.value})")
        if step.exit_code is not None:
            click.echo(f"       exit={step.exit_code}  retries={step.retry_count}")


if __name__ == "__main__":
    main()
