"""Exercise the actual release version guard without GitHub or account access."""

import ast
from pathlib import Path
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        guard = workflow.split("# BEGIN RELEASE VERSION GUARD\n", 1)[1].split(
            "# END RELEASE VERSION GUARD", 1)[0]
        tree = ast.parse(textwrap.dedent(guard))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
        scope = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<release-version-guard>", "exec"), scope)
        cls.verify = staticmethod(scope["verify_release_version"])

    def test_exact_stable_and_beta_tags_are_accepted(self):
        for version in ("0.2.0b3", "1.0.0", "1.2.0rc1"):
            for tag in (version, "v" + version):
                with self.subTest(version=version, tag=tag):
                    self.verify(version, tag)

    def test_mismatched_and_nonexact_tags_are_rejected(self):
        for tag in ("v0.2.0b2", "0.2.0", "main", "vv0.2.0b3", "v0.2.0b3\n", "$(echo bad)"):
            with self.subTest(tag=tag), self.assertRaises(SystemExit):
                self.verify("0.2.0b3", tag)

    def test_missing_or_malformed_manifest_version_is_rejected(self):
        for version in (None, "", " 1.0.0", "1.0.0\n", 1, ["1.0.0"]):
            with self.subTest(version=version), self.assertRaises(SystemExit):
                self.verify(version, "v1.0.0")


if __name__ == "__main__":
    unittest.main()
