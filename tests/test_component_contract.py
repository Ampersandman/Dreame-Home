"""Exercise isolated beta boundaries, without pretending to run Home Assistant."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from dreamehome.exceptions import AuthenticationError, TransportError
from dreamehome.laundry import laundry_read_pairs, laundry_schema
from dreamehome.observations import ObservationStore, VACUUM_INITIAL_READ_PAIRS, property_coordinate

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "dreame_home"


def isolated(filename, name, namespace=None, owner=None):
    module = ast.parse((COMPONENT / filename).read_text(encoding="utf-8"))
    body = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == owner).body if owner else module.body
    node = next(node for node in body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    scope = {"__builtins__": __builtins__, **(namespace or {})}
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec"), scope)
    return scope[name]


def state(model):
    return SimpleNamespace(device=SimpleNamespace(model=model), store=ObservationStore(model),
                           timestamps={}, read_error=None, initial_read_done=False)


class ReadPlanTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = SimpleNamespace(read_properties=AsyncMock(return_value=[]))
        self.read = isolated("coordinator.py", "_read", {
            "monotonic": lambda: 733, "VACUUM_INITIAL_READ_PAIRS": VACUUM_INITIAL_READ_PAIRS,
            "AuthenticationError": AuthenticationError, "RateLimitError": type("Rate", (Exception,), {}),
            "DreameError": TransportError,
            "laundry_read_pairs": laundry_read_pairs, "laundry_schema": laundry_schema,
            "property_coordinate": property_coordinate,
        }, owner="DreameCoordinator")
        freshness = isolated("coordinator.py", "_freshness", {"monotonic": lambda: 733}, owner="DreameCoordinator")
        self.coordinator = SimpleNamespace(api=self.api, _freshness=lambda state, touched: freshness(None, state, touched))

    async def test_unverified_laundry_requires_own_successful_observation(self):
        item = state("dreame.washer.unverified")
        await self.read(self.coordinator, item)
        self.api.read_properties.assert_not_called()
        item.store.merge_properties([
            {"siid": 20, "piid": 7, "value": 4, "code": 0},
            {"siid": 20, "piid": 8, "value": 5, "code": -4001},
        ])
        await self.read(self.coordinator, item)
        self.assertEqual(self.api.read_properties.call_args.args[1], [(20, 7)])

    async def test_vacuum_seed_is_preserved_when_observed_values_exceed_budget(self):
        item = state("dreame.vacuum.r5023a")
        item.store.merge_properties([{"siid": 100, "piid": index, "value": index} for index in range(1, 301)])
        await self.read(self.coordinator, item)
        pairs = self.api.read_properties.call_args.args[1]
        self.assertEqual(len(pairs), 240)
        self.assertTrue(set(VACUUM_INITIAL_READ_PAIRS).issubset(pairs))

    async def test_device_transport_failure_is_local_but_authentication_propagates(self):
        item = state("dreame.dryer.l9nacn")
        item.store.merge_properties([{"siid": 6, "piid": 1, "value": True}])
        self.api.read_properties.side_effect = TransportError("offline")
        await self.read(self.coordinator, item)
        self.assertEqual(item.read_error, "TransportError")
        self.api.read_properties.side_effect = AuthenticationError("expired")
        with self.assertRaises(AuthenticationError):
            await self.read(self.coordinator, item)


class DistributionBoundaryTests(unittest.TestCase):
    def test_diagnostics_omit_unknown_strings_containing_secrets(self):
        project = isolated("diagnostics.py", "diagnostic_value")
        project.__globals__["diagnostic_value"] = project
        secret = "undocumented-refresh-token"
        value = project({"value": [secret, {"unrecognized": secret, "count": 3}], "enabled": True})
        self.assertNotIn(secret, json.dumps(value))
        self.assertEqual(value["value"][1]["count"], 3)

    def test_packaging_has_matching_translations_and_only_readonly_platforms(self):
        strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        translated = json.loads((COMPONENT / "translations" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(strings, translated)
        manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], "dreame_home")
        for control in ("switch", "select", "number", "button", "services"):
            self.assertFalse((COMPONENT / f"{control}.py").exists())


if __name__ == "__main__":
    unittest.main()
