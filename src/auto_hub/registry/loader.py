from pathlib import Path

import yaml

from auto_hub.registry.models import ProjectManifest, RegistryManifest


class RegistryLoader:
    """Load and validate project manifests from YAML files."""

    def __init__(self, manifests_dir: Path | None = None):
        self._manifests_dir = manifests_dir or Path(__file__).resolve().parent.parent.parent.parent / "manifests"
        self._manifest: RegistryManifest | None = None

    def load(self) -> RegistryManifest:
        main_file = self._manifests_dir / "projects.yaml"
        if not main_file.exists():
            raise FileNotFoundError(f"Manifest file not found: {main_file}")
        with open(main_file) as f:
            data = yaml.safe_load(f)
        self._manifest = RegistryManifest(**data)
        return self._manifest

    @property
    def manifest(self) -> RegistryManifest:
        if self._manifest is None:
            return self.load()
        return self._manifest

    def list_projects(self) -> list[ProjectManifest]:
        return self.manifest.projects

    def get_project(self, name: str) -> ProjectManifest | None:
        for p in self.manifest.projects:
            if p.name == name:
                return p
        return None

    def resolve_path(self, project: ProjectManifest) -> Path:
        hub_root = self._manifests_dir.resolve().parent
        return (hub_root / project.path).resolve()

    def get_missing_projects(self) -> list[ProjectManifest]:
        missing: list[ProjectManifest] = []
        for p in self.manifest.projects:
            resolved = self.resolve_path(p)
            if not resolved.exists():
                missing.append(p)
        return missing
