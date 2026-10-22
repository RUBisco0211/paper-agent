"""Keep router packages uniform and HTTP wiring out of execution code."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
ROUTER_FILES = {
    "__init__.py",
    "api.py",
    "schemas.py",
    "depends.py",
    "service.py",
    "domain.py",
    "repo.py",
    "ports.py",
}

LITERATURE_PACKAGES = {"library", "imports", "processing", "retrieval"}

#: Packages that carry their own HTTP boundary and must therefore be uniform.
#: Supporting packages (``web``, ``service_credentials``) live beside them with
#: the file names that match what they contain.
ROUTER_PACKAGES = {
    "auth",
    "imports",
    "library",
    "processing",
    "projects",
    "retrieval",
    "schedules",
    "sessions",
}


def test_literature_workflows_have_four_business_packages():
    for name in LITERATURE_PACKAGES:
        package = APP / name
        assert {path.name for path in package.glob("*.py")} == ROUTER_FILES
    for old_name in {"ingestion", "embedding", "evidence", "scholar"}:
        assert not (APP / old_name).exists()


def _imports(path: Path) -> list[str]:
    """Resolve imports without bootstrapping application infrastructure."""
    package = ["app", *path.relative_to(APP).parts[:-1]]
    modules = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join(prefix + ([node.module] if node.module else []))
            modules.append(module)
            modules.extend(f"{module}.{alias.name}" for alias in node.names)
    return modules


def test_router_packages_have_only_the_standard_modules():
    packages = [APP / name for name in sorted(ROUTER_PACKAGES)]
    assert all((package / "api.py").exists() for package in packages)
    for package in packages:
        assert {path.name for path in package.glob("*.py")} == ROUTER_FILES
        assert not [
            path
            for path in package.iterdir()
            if path.is_dir() and (path / "__init__.py").exists()
        ], f"Move supporting packages out of {package.name}"


def test_execution_code_does_not_import_http_wiring():
    for path in APP.rglob("*.py"):
        if path.parent == APP or path.relative_to(APP).parts[0] == "platform":
            continue
        if path.name in {"__init__.py", "api.py", "schemas.py", "depends.py"}:
            continue
        for module in _imports(path):
            assert module.split(".")[0] != "fastapi", (path, module)
            if module.startswith("app."):
                assert not {"api", "schemas", "depends"}.intersection(
                    module.split(".")
                ), (path, module)


def test_routers_do_not_access_repositories_directly():
    for path in APP.glob("*/api.py"):
        for module in _imports(path):
            assert "repo" not in module.split("."), (path, module)
            assert module != "sqlalchemy" and not module.startswith("sqlalchemy."), (
                path,
                module,
            )
