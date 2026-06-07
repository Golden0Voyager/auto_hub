import click


@click.group()
def main():
    """auto_hub: central coordination layer for auto_* projects."""


@main.command()
def list():
    """List all registered auto_* projects."""
    click.echo("No projects registered yet. Run Phase 1 to set up the registry.")


@main.command()
@click.argument("project_name")
def show(project_name: str):
    """Show metadata for a single project."""
    click.echo(f"Project '{project_name}' not found. Run Phase 1 to set up the registry.")


if __name__ == "__main__":
    main()
