"""CLI schema inspection stays offline and does not broaden capture reads."""

import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dreamehome import cli
from dreamehome.catalog import load_catalog
from dreamehome.exceptions import SchemaRequiredError


class SchemaCommandTests(unittest.IsolatedAsyncioTestCase):
    async def inspect(self, *arguments):
        output = io.StringIO()
        args = cli.parser().parse_args(["schema", *arguments])
        with patch.object(cli, "create_client", side_effect=AssertionError("Schema command must not create an API client")), contextlib.redirect_stdout(output):
            self.assertEqual(await cli.run(args), 0)
        return json.loads(output.getvalue())

    async def test_exact_l9_catalogs_include_full_offline_definitions(self):
        for model, catalog in (("dreame.washer.l9nacn", "l9_washer"),
                               ("dreame.dryer.l9nacn", "l9_dryer")):
            with self.subTest(model=model):
                definition = await self.inspect("--model", model)
                self.assertEqual(definition, load_catalog(catalog))
                self.assertTrue(definition["properties"])
                self.assertTrue(definition["programs"])
                self.assertTrue(definition["source"]["bundle_sha256"])

    async def test_existing_debug_candidate_requires_explicit_opt_in(self):
        with self.assertRaises(SchemaRequiredError):
            await self.inspect("--model", "dreame.washer.r1111")
        candidate = await self.inspect("--model", "dreame.washer.r1111", "--allow-debug-schema")
        self.assertEqual(candidate["model"], "dreame.washer.r1111")
        self.assertFalse(candidate["live_verified"])

    async def test_similar_marketing_models_do_not_inherit_l9_definitions(self):
        with self.assertRaises(SchemaRequiredError):
            await self.inspect("--model", "dreame.dryer.l9other", "--allow-debug-schema")

    async def test_inspection_does_not_enable_implicit_laundry_capture_polling(self):
        for model in ("dreame.washer.l9nacn", "dreame.dryer.l9nacn"):
            args = cli.parser().parse_args(["capture", "--model", model, "--read-schema", "--output", "not-created.json"])
            with patch.object(cli, "create_client", side_effect=AssertionError("Capture must reject missing MIoT schema before login")):
                with self.assertRaises(SchemaRequiredError):
                    await cli.run(args)


if __name__ == "__main__":
    unittest.main()
