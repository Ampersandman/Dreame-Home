"""Bundled resource setup is idempotent, async and isolated from account data."""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from urllib.parse import quote

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components/dreame_home"


class FrontendRegistrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = SimpleNamespace(data={}, http=SimpleNamespace(async_register_static_paths=AsyncMock()))
        self.integration = SimpleNamespace(version="0.4.0b1")
        self.added, self.removed = [], []
        self.scope = {
            "asyncio": asyncio, "Path": Path, "quote": quote, "__file__": str(COMPONENT / "frontend.py"),
            "DOMAIN": "dreame_home", "async_get_integration": AsyncMock(return_value=self.integration),
            "StaticPathConfig": lambda url, path, cache: SimpleNamespace(url_path=url, path=path, cache_headers=cache),
            "add_extra_js_url": lambda hass, url: self.added.append(url),
            "remove_extra_js_url": lambda hass, url: self.removed.append(url),
        }
        tree = ast.parse((COMPONENT / "frontend.py").read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        exec(compile(tree, "frontend.py", "exec"), self.scope)

    async def register(self):
        await self.scope["async_register_frontend"](self.hass)

    async def test_concurrent_accounts_register_one_public_file_and_module(self):
        await asyncio.gather(self.register(), self.register())
        self.hass.http.async_register_static_paths.assert_awaited_once()
        paths = self.hass.http.async_register_static_paths.call_args.args[0]
        self.assertEqual(len(paths), 1)
        self.assertEqual(Path(paths[0].path), COMPONENT / "frontend/dreame-home-laundry-card.js")
        self.assertEqual(paths[0].url_path, "/dreame_home/dreame-home-laundry-card.js")
        self.assertEqual(self.added, ["/dreame_home/dreame-home-laundry-card.js?v=0.4.0b1"])
        self.assertFalse(self.removed)

    async def test_version_change_updates_url_without_duplicate_routes(self):
        await self.register()
        self.integration.version = "0.4.0b2"
        await self.register()
        await self.register()
        self.hass.http.async_register_static_paths.assert_awaited_once()
        self.assertEqual(len(self.added), 2)
        self.assertEqual(self.removed, ["/dreame_home/dreame-home-laundry-card.js?v=0.4.0b1"])

    async def test_ha_version_object_is_stringified_before_url_encoding(self):
        class Version:
            def __str__(self):
                return "0.4.0b1"
        self.integration.version = Version()
        await self.register()
        self.assertEqual(self.added, ["/dreame_home/dreame-home-laundry-card.js?v=0.4.0b1"])

    async def test_failed_static_registration_can_be_retried(self):
        self.hass.http.async_register_static_paths.side_effect = [OSError("mock route failure"), None]
        with self.assertRaises(OSError):
            await self.register()
        self.assertFalse(self.added)
        await self.register()
        self.assertEqual(len(self.added), 1)

    async def test_module_failure_does_not_register_static_route_twice(self):
        self.scope["add_extra_js_url"] = lambda hass, url: (_ for _ in ()).throw(RuntimeError("mock module failure"))
        with self.assertRaises(RuntimeError):
            await self.register()
        self.scope["add_extra_js_url"] = lambda hass, url: self.added.append(url)
        await self.register()
        self.hass.http.async_register_static_paths.assert_awaited_once()
        self.assertEqual(len(self.added), 1)


if __name__ == "__main__":
    unittest.main()
