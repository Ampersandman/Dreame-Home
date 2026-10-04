"""Portable allowlist, containment and preservation checks for repository export."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("hacs_repository_export", ROOT / "tools/export_hacs_repository.py")
EXPORT = importlib.util.module_from_spec(SPEC)
# Dataclasses resolve the defining module from sys.modules during decoration.
import sys
sys.modules[SPEC.name] = EXPORT
SPEC.loader.exec_module(EXPORT)


def write(root, relative, value=b"fixture\n"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


def workspace(root):
    for name in EXPORT.ROOT_FILES:
        write(root, name)
    write(root, ".gitattributes", b"* text=auto eol=lf\n")
    write(root, "custom_components/dreame_home/__init__.py")
    write(root, "custom_components/dreame_home/manifest.json", b'{"domain":"dreame_home"}\n')
    write(root, "custom_components/dreame_home/api/data/l9_washer.json", b"{}\n")
    write(root, "custom_components/dreame_home/api/LICENSE")
    write(root, "custom_components/dreame_home/api/licenses/ioBroker.dreame.txt")
    write(root, "custom_components/dreame_home/brand/icon.png", b"generated-brand-png")
    write(root, "custom_components/dreame_home/brand/icon.svg", b"<svg>original-brand</svg>")
    write(root, "src/dreamehome/__init__.py")
    write(root, "src/dreamehome/data/l9_washer.json", b"{}\n")
    write(root, "src/dreamehome/py.typed", b"")
    write(root, "licenses/ioBroker.dreame.txt")
    write(root, "docs/live-coverage.md")
    write(root, "docs/live-verification.json", b"{}\n")
    write(root, "tests/test_portable.py")
    write(root, "tools/build_component.py")
    write(root, "tools/build_brand.py")
    write(root, "tools/export_hacs_repository.py")
    write(root, "tools/scan_cloud_account.py")
    write(root, ".github/workflows/validate.yml")


class RepositoryExportTests(unittest.TestCase):
    def test_allowlist_excludes_private_research_vendor_code_and_bytecode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root)
            excluded = [
                "private/account.json", "captures/live.json", "ha-diag/diagnostic.json", "references/public.apk",
                "references/miot/provenance.json", "upstream/protocol.py", ".venv/secret.py",
                "dist/old.zip", "custom_components/dreame_home/__pycache__/client.pyc",
                "custom_components/dreame_home/private/account.json",
                "custom_components/dreame_home/ha-diag/diagnostic.json",
                "custom_components/dreame_home/vendor.js",
                "custom_components/dreame_home/brand/vendor.js",
                "custom_components/dreame_home/raw.pem", "src/dreamehome/plugin.hbc",
                "docs/raw-capture.json", "tools/l9_research_mirror.py", ".github/workflows/local.apk",
            ]
            for name in excluded:
                write(root, name, b"never-export-this")
            plan = EXPORT.planned_files(root)
            self.assertFalse(set(excluded) & set(plan))
            for name in (".gitattributes", "tools/build_brand.py", "docs/live-verification.json",
                         "custom_components/dreame_home/brand/icon.png",
                         "custom_components/dreame_home/brand/icon.svg", "tests/test_portable.py"):
                self.assertIn(name, plan)
            self.assertFalse(any(data == b"never-export-this" for data in plan.values()))

    def test_export_preserves_existing_git_metadata_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root)
            output = root / "hacs-repository"
            git = write(output, ".git/config", b"existing-authorized-remote\n")
            result = EXPORT.export_repository(root, output)
            self.assertGreater(len(result.changed), 0)
            self.assertEqual(git.read_bytes(), b"existing-authorized-remote\n")
            stamp = (output / "README.md").stat().st_mtime_ns
            second = EXPORT.export_repository(root, output)
            self.assertEqual(second.changed, ())
            self.assertEqual((output / "README.md").stat().st_mtime_ns, stamp)
            write(root, "README.md", b"updated-public-readme\n")
            updated = EXPORT.export_repository(root, output)
            self.assertEqual(updated.changed, ("README.md",))
            self.assertEqual(git.read_bytes(), b"existing-authorized-remote\n")

    def test_unexpected_content_is_refused_before_overwriting_known_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root)
            output = root / "hacs-repository"
            EXPORT.export_repository(root, output)
            write(output, "private/account.json", b"must-remain-untouched")
            write(root, "README.md", b"new-readme\n")
            original = (output / "README.md").read_bytes()
            with self.assertRaisesRegex(ValueError, "Unexpected repository output"):
                EXPORT.export_repository(root, output)
            self.assertEqual((output / "README.md").read_bytes(), original)
            self.assertEqual((output / "private/account.json").read_bytes(), b"must-remain-untouched")

    def test_check_and_dry_run_do_not_write_and_report_changed_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root)
            output = root / "hacs-repository"
            for kwargs in ({"check": True}, {"dry_run": True}):
                result = EXPORT.export_repository(root, output, **kwargs)
                self.assertFalse(output.exists())
                self.assertGreater(len(result.changed), 0)
            EXPORT.export_repository(root, output)
            self.assertEqual(EXPORT.export_repository(root, output, check=True).changed, ())

    def test_output_boundaries_reject_workspace_root_reserved_paths_and_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            workspace(root)
            for output in (root, root.parent / "outside", Path("../outside"),
                           root / "src/output", root / "private/output", root / "dist/output"):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    EXPORT.export_repository(root, output)
            self.assertFalse((root.parent / "outside").exists())

    def test_archive_is_reproducible_and_excludes_git_and_verification_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root)
            output = root / "hacs-repository"
            write(output, ".git/config", b"local-git-metadata")
            EXPORT.export_repository(root, output)
            for name in (".venv/install.py", "build/temp.bin", "dist/package.zip",
                         "src/package.egg-info/PKG-INFO", "tests/__pycache__/test.pyc"):
                write(output, name, b"verification-artifact")
            self.assertEqual(EXPORT.export_repository(root, output, check=True).changed, ())
            archive, first_hash = EXPORT.archive_repository(root, output, Path("dist/source.zip"))
            _, second_hash = EXPORT.archive_repository(root, output, Path("dist/source.zip"))
            self.assertEqual(first_hash, second_hash)
            with zipfile.ZipFile(archive) as bundle:
                self.assertIn("dreame-home-repository/README.md", bundle.namelist())
                self.assertEqual(len(bundle.namelist()), len(EXPORT.planned_files(root)))
                self.assertFalse(any(".git/" in name or "/dist/" in name or "/.venv/" in name for name in bundle.namelist()))
                self.assertFalse(any(bundle.read(name) == b"verification-artifact" for name in bundle.namelist()))
            with self.assertRaises(ValueError):
                EXPORT.archive_repository(root, output, root.parent / "outside.zip")

    def test_source_and_destination_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace(root)
            target = write(root, "private/secret.py", b"never-follow")
            link = root / "src/dreamehome/linked.py"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("Local platform does not permit symlink creation")
            with self.assertRaisesRegex(ValueError, "links"):
                EXPORT.planned_files(root)
            link.unlink()
            output = root / "hacs-repository"
            EXPORT.export_repository(root, output)
            output_link = output / "README.md"
            output_link.unlink()
            output_link.symlink_to(target)
            with self.assertRaises(ValueError):
                EXPORT.export_repository(root, output)
            self.assertEqual(target.read_bytes(), b"never-follow")


if __name__ == "__main__":
    unittest.main()
