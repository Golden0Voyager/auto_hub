"""Tests for the registry loader and manifest validation."""

from pathlib import Path

import pytest
import yaml

from auto_hub.registry.loader import RegistryLoader
from auto_hub.registry.models import RegistryManifest


@pytest.fixture
def loader() -> RegistryLoader:
    return RegistryLoader()


def test_manifest_loads_all_projects(loader: RegistryLoader):
    registry = loader.load()
    assert len(registry.projects) == 13
    names = {p.name for p in registry.projects}
    expected = {
        "auto_animation", "auto_audiobook", "auto_curation", "auto_f1",
        "auto_form", "auto_github", "auto_html", "auto_lingo",
        "auto_motion", "auto_nutrition", "auto_pdf", "auto_resume",
        "auto_scrape",
    }
    assert names == expected


def test_every_project_has_capabilities(loader: RegistryLoader):
    for p in loader.load().projects:
        if p.type in ("static-assets",):
            continue
        assert len(p.capabilities) >= 1, f"{p.name} has no capabilities"


def test_every_project_has_type(loader: RegistryLoader):
    for p in loader.load().projects:
        assert p.type, f"{p.name} missing type"


def test_get_project_found(loader: RegistryLoader):
    p = loader.get_project("auto_pdf")
    assert p is not None
    assert p.name == "auto_pdf"


def test_get_project_not_found(loader: RegistryLoader):
    p = loader.get_project("nonexistent")
    assert p is None


def test_missing_projects_detected(loader: RegistryLoader):
    missing = loader.get_missing_projects()
    for m in missing:
        resolved = loader.resolve_path(m)
        assert not resolved.exists(), f"{m.name} should exist at {resolved}"


def test_duplicate_capability_ids(loader: RegistryLoader):
    all_caps = []
    for p in loader.load().projects:
        all_caps.extend(p.capabilities)
    duplicates = {c for c in all_caps if all_caps.count(c) > 1}
    assert len(duplicates) == 0, f"Duplicate capability IDs: {duplicates}"


def test_manifest_conforms_to_schema(loader: RegistryLoader):
    manifest_path = Path(__file__).resolve().parent.parent / "manifests" / "projects.yaml"
    with open(manifest_path) as f:
        data = yaml.safe_load(f)
    registry = RegistryManifest(**data)
    assert isinstance(registry, RegistryManifest)


def test_python_packages_have_entrypoints(loader: RegistryLoader):
    for p in loader.load().projects:
        if p.type in ("python-package", "mcp-server"):
            assert p.entrypoints and p.entrypoints.cli, f"{p.name} missing CLI entrypoint"


def test_mcp_projects_have_mcp_entrypoints(loader: RegistryLoader):
    mcp_projects = [p for p in loader.load().projects if p.type == "mcp-server"]
    assert len(mcp_projects) >= 2
    for p in mcp_projects:
        assert p.entrypoints and p.entrypoints.mcp, f"{p.name} missing MCP entrypoint"
        assert p.ai_clients and p.ai_clients.mcp, f"{p.name} missing ai_clients.mcp"


def test_names_are_snake_case(loader: RegistryLoader):
    for p in loader.load().projects:
        assert "_" in p.name, f"{p.name} is not snake_case"
