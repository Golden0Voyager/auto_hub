
from pydantic import BaseModel, Field


class EnvironmentManifest(BaseModel):
    required: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)


class IntegrationManifest(BaseModel):
    shared_llm: str | None = None
    mcp: str | None = None
    workflow_node: str | None = None


class AiClientsMCPManifest(BaseModel):
    status: str | None = None
    preferred_transport: str | None = None


class AiClientsManifest(BaseModel):
    mcp: AiClientsMCPManifest | None = None


class GitManifest(BaseModel):
    independent_repo: bool = True
    default_branch: str = "main"


class PackageManifest(BaseModel):
    manager: str = "uv"
    python: str | None = None


class DocsManifest(BaseModel):
    readme: str | None = None
    local_instructions: str | None = None


class EntryPointManifest(BaseModel):
    command: str


class EntryPointsManifest(BaseModel):
    cli: EntryPointManifest | None = None
    web: EntryPointManifest | None = None
    mcp: EntryPointManifest | None = None


class ProjectManifest(BaseModel):
    name: str
    path: str
    type: str
    status: str = "active"
    description: str = ""
    entrypoints: EntryPointsManifest | None = None
    capabilities: list[str] = Field(default_factory=list)
    environment: EnvironmentManifest = Field(default_factory=EnvironmentManifest)
    integration: IntegrationManifest | None = None
    ai_clients: AiClientsManifest | None = None
    git: GitManifest = Field(default_factory=GitManifest)
    package: PackageManifest = Field(default_factory=PackageManifest)
    docs: DocsManifest = Field(default_factory=DocsManifest)
    tests: EntryPointManifest | None = None


class RegistryManifest(BaseModel):
    projects: list[ProjectManifest]
