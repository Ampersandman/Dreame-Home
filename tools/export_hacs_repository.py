"""Export an allowlisted standalone HACS repository without research/private data.

The destination must stay under the workspace. Re-exporting updates known files;
optional housekeeping removes only explicitly retired publication paths. Git
metadata and ignored test/build artifacts remain untouched, and unexpected
destination content fails before mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "pyproject.toml",
    "requirements-tested.txt", "hacs.json", ".gitignore",
)
OPTIONAL_ROOT_FILES = (".gitattributes",)
TOOLS = ("build_component.py", "build_brand.py", "export_hacs_repository.py")
PUBLIC_DOCS = {"installation.md", "entities.md", "dashboard-card.md", "automations.md", "troubleshooting.md"}
PUBLIC_TEST_FIXTURES = {"fixtures/signing_reference.json", "fixtures/vacuum_reference.json"}
# Keep public source aligned with the component builder's runtime selection.
RUNTIME_CATALOGS = {"api", "models", "properties", "l9_washer", "l9_dryer"}
RESEARCH_MODULES = {"__main__.py", "cli.py", "discovery.py", "miot.py"}
REFERENCE_CATALOGS = {
    "actions", "availability", "constants", "device_info", "entities", "entity_defaults",
    "enums", "implementations", "property_groups", "protocol_strings", "provenance",
    "translations_en", "washer_candidates",
}
RESEARCH_TESTS = {"test_account_scan.py", "test_cli_schema.py", "test_device_capture.py",
                  "test_dryer_extraction.py", "test_plugins.py"}
RETIRED_DOCS = {
    "appliance-controls.md", "cycle-progress.md", "dreamehome-api.md", "ha-diagnostics-review-2026-10-06.md",
    "ha-diagnostics-review.md", "ha-os-installation.md", "hacs-design.md", "hacs-publishing.md",
    "home-assistant-roadmap.md", "l9-investigation.md", "l9-schema-research.md", "live-coverage.md",
    "live-verification.json", "mqtt-trust-research.md", "vacuum-model-review.md", "verification.md",
}
RETIRED_TOOLS = {
    "check_ha_dependencies.py", "extract_upstream.py", "extract_miot.py", "extract_l9_dryer.py",
    "extract_l9_washer.py", "fetch_miot_reference.py", "capture_device_api.py", "capture_device_api.ps1",
    "fetch_device_plugins.py", "fetch_device_plugins.ps1", "scan_cloud_account.py", "scan_cloud_account.ps1",
    "summarize_live_verification.py",
}
RETIRED_BACKEND_FILES = RESEARCH_MODULES | {f"data/{name}.json" for name in REFERENCE_CATALOGS}
RETIRED_PATHS = (
    {f"docs/{name}" for name in RETIRED_DOCS}
    | {f"tools/{name}" for name in RETIRED_TOOLS}
    | {f"tests/{name}" for name in RESEARCH_TESTS}
    | {f"src/dreamehome/{name}" for name in RETIRED_BACKEND_FILES}
    | {f"custom_components/dreame_home/api/{name}" for name in RETIRED_BACKEND_FILES}
)
RESERVED_OUTPUT_ROOTS = {
    "custom_components", "src", "tools", "tests", "docs", "licenses", ".github",
    ".git", ".venv", "private", "captures", "ha-diag", "references", "upstream", "build", "dist",
}
IGNORED_DESTINATION_DIRS = {
    ".git", ".venv", "build", "dist", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
SOURCE_EXCLUDED_DIRS = {
    ".git", ".venv", "private", "captures", "ha-diag", "references", "upstream", "build", "dist",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "hacs-repository",
    ".aws", ".codex", ".agents",
}


def linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def checked_path(path: Path, boundary: Path) -> Path:
    """Reject redirects and require both lexical and resolved containment."""
    boundary = boundary.resolve()
    absolute = Path(os.path.abspath(path))
    absolute.relative_to(boundary)
    absolute.resolve().relative_to(boundary)
    current = absolute
    while current != boundary:
        if linked(current):
            raise ValueError(f"Export paths must not be links: {current}")
        current = current.parent
    return absolute


def files_under(directory: Path, boundary: Path):
    if not directory.exists():
        return
    checked_path(directory, boundary)
    for entry in sorted(directory.iterdir(), key=lambda path: path.name):
        checked_path(entry, boundary)
        if entry.is_dir():
            if entry.name in SOURCE_EXCLUDED_DIRS or entry.name.endswith(".egg-info"):
                continue
            yield from files_under(entry, boundary)
        elif entry.is_file():
            yield entry


def planned_files(root: Path) -> dict[str, bytes]:
    """Read only explicitly approved namespaces and file formats."""
    root = root.resolve()
    plan: dict[str, bytes] = {}

    def include(path: Path):
        checked = checked_path(path, root)
        plan[checked.relative_to(root).as_posix()] = checked.read_bytes()

    for name in ROOT_FILES:
        path = root / name
        if not path.is_file():
            raise ValueError(f"Missing repository metadata: {name}")
        include(path)
    for name in OPTIONAL_ROOT_FILES:
        if (root / name).exists():
            include(root / name)

    for base in (root / "custom_components/dreame_home", root / "src/dreamehome"):
        if not base.is_dir():
            raise ValueError(f"Missing runtime package: {base.relative_to(root)}")
        for path in files_under(base, root):
            relative = path.relative_to(base)
            runtime = path.suffix in {".py", ".json", ".md"} or path.name in {"LICENSE", "py.typed"}
            if base.name == "dreamehome":
                if relative.as_posix() in RESEARCH_MODULES:
                    continue
                if path.suffix == ".json" and path.stem not in RUNTIME_CATALOGS:
                    continue
            elif len(relative.parts) > 1 and relative.parts[0] == "api":
                backend_path = Path(*relative.parts[1:])
                if backend_path.as_posix() in RESEARCH_MODULES:
                    continue
                if (backend_path.parts[0] == "data" and path.suffix == ".json"
                        and path.stem not in RUNTIME_CATALOGS):
                    continue
            license_file = "licenses" in relative.parts and path.suffix == ".txt"
            brand = base.name == "dreame_home" and relative.parts[0] == "brand" and path.suffix in {".png", ".svg"}
            frontend = base.name == "dreame_home" and relative.parts[0] == "frontend" and path.suffix in {".js", ".css", ".svg"}
            if runtime or license_file or brand or frontend:
                include(path)
    for base, suffixes in ((root / "licenses", {".txt", ".md"}),
                           (root / "tests", {".py"}),
                           (root / ".github/workflows", {".yml", ".yaml"})):
        for path in files_under(base, root):
            if path.name in RESEARCH_TESTS:
                continue
            frontend_test = base.name == "tests" and path.relative_to(base).parts[0] == "frontend" and path.suffix in {".js", ".mjs"}
            reference_fixture = base.name == "tests" and path.relative_to(base).as_posix() in PUBLIC_TEST_FIXTURES
            if path.suffix in suffixes or frontend_test or reference_fixture:
                include(path)
    for path in files_under(root / "docs", root):
        relative = path.relative_to(root / "docs").as_posix()
        if relative in PUBLIC_DOCS or relative == "assets/laundry-card.png":
            include(path)
    for name in TOOLS:
        if (root / "tools" / name).exists():
            include(root / "tools" / name)
    return dict(sorted(plan.items()))


def destination_path(root: Path, destination: Path) -> Path:
    root = root.resolve()
    destination = destination if destination.is_absolute() else root / destination
    destination = checked_path(destination, root)
    relative = destination.relative_to(root)
    if not relative.parts or relative.parts[0] in RESERVED_OUTPUT_ROOTS:
        raise ValueError("Repository output must be an isolated directory under the workspace")
    return destination


def ignored_directory(name: str) -> bool:
    return name in IGNORED_DESTINATION_DIRS or name.endswith(".egg-info")


def ignored_file(name: str) -> bool:
    return name == ".git" or name == ".coverage" or name.startswith(".coverage.") or name.endswith((".pyc", ".pyo"))


def validate_destination(destination: Path, plan: dict[str, bytes], *, retired=()) -> None:
    """Fail before mutation if anything outside the declared export is present."""
    if not destination.exists():
        return
    if not destination.is_dir():
        raise ValueError("Repository output is not a directory")
    directories = {str(Path(name).parent.as_posix()) for name in plan}
    for name in plan:
        directories.update(parent.as_posix() for parent in Path(name).parents if parent.as_posix() != ".")
    unexpected = []

    def inspect(directory: Path):
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            relative = path.relative_to(destination).as_posix()
            # Existing Git and ignored verification artifacts are preserved,
            # never read, written or included in source repository archives.
            if ((path.is_dir() and ignored_directory(path.name))
                    or (path.is_file() and ignored_file(path.name))):
                continue
            checked_path(path, destination)
            if path.is_dir():
                if relative not in directories:
                    unexpected.append(relative + "/")
                else:
                    inspect(path)
            elif not path.is_file() or relative not in plan and relative not in retired:
                unexpected.append(relative)

    inspect(destination)
    if unexpected:
        preview = ", ".join(unexpected[:10])
        raise ValueError(f"Unexpected repository output requires review ({len(unexpected)}): {preview}")


@dataclass(frozen=True)
class ExportResult:
    destination: Path
    file_count: int
    changed: tuple[str, ...]
    retired: tuple[str, ...] = ()


def export_repository(root: Path, destination: Path, *, check: bool = False, dry_run: bool = False,
                      prune: bool = False) -> ExportResult:
    root = root.resolve()
    output = destination_path(root, destination)
    plan = planned_files(root)
    retired = tuple(sorted(name for name in RETIRED_PATHS if name not in plan and (output / name).exists())) if prune else ()
    validate_destination(output, plan, retired=retired)
    changed = tuple(name for name, data in plan.items()
                    if not (output / name).is_file() or (output / name).read_bytes() != data)
    if not check and not dry_run:
        # Only explicitly retired publication files can be removed. Their local
        # source/research copies remain outside the clean Git checkout.
        for name in retired:
            target = checked_path(output / name, output)
            if not target.is_file():
                raise ValueError("Retired publication paths must be ordinary files")
            target.unlink()
        for name in changed:
            target = checked_path(output / name, root)
            target.parent.mkdir(parents=True, exist_ok=True)
            checked_path(target, output)
            target.write_bytes(plan[name])
    return ExportResult(output, len(plan), changed, retired)


def archive_repository(root: Path, destination: Path, archive: Path) -> tuple[Path, str]:
    """Create a reproducible source ZIP from the verified allowlist only."""
    root = root.resolve()
    output = destination_path(root, destination)
    plan = planned_files(root)
    validate_destination(output, plan)
    if any(not (output / name).is_file() or (output / name).read_bytes() != data for name, data in plan.items()):
        raise ValueError("Export must match current source before archiving")
    archive = archive if archive.is_absolute() else root / archive
    archive = checked_path(archive, root)
    if archive.relative_to(root).parts[0] != "dist" or archive.suffix != ".zip":
        raise ValueError("Repository archive must be a ZIP under workspace/dist")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, data in plan.items():
            info = zipfile.ZipInfo(f"dreame-home-repository/{name}", date_time=(2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, data)
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("hacs-repository"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prune", action="store_true", help="Remove only the explicit retired publication files")
    parser.add_argument("--archive", type=Path, nargs="?", const=Path("dist/dreame-home-repository.zip"))
    args = parser.parse_args()
    if args.archive and (args.check or args.dry_run):
        parser.error("--archive cannot be combined with --check or --dry-run")
    try:
        result = export_repository(ROOT, args.output, check=args.check, dry_run=args.dry_run, prune=args.prune)
        verb = "Checked" if args.check else "Planned" if args.dry_run else "Exported"
        print(f"{verb} {result.file_count} repository files; {len(result.changed)} differ: {result.destination}")
        if result.retired:
            print(f"Retired publication files: {len(result.retired)}")
        if args.check and (result.changed or result.retired):
            return 1
        if args.archive:
            output, digest = archive_repository(ROOT, args.output, args.archive)
            print(f"Built {output}; SHA256 {digest}")
        return 0
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
