"""Page mirror, isolated simulation, validation and custom-pack save contracts."""
import asyncio
import importlib
import json
from pathlib import Path
import random
import tempfile
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, Mock, patch

from test_horserace import PKG, ROOT, RaceService

core = importlib.import_module(f"{PKG}.dashboard_core")
DashboardAPI = importlib.import_module(f"{PKG}.dashboard_api").DashboardAPI


def payload(**kwargs):
    return {"pack": [{"event_name": "测试", "target": 0, "move": 3}],
            "players": [{"name": "a", "location": 0}, {"name": "b", "location": 0}],
            "seed": 42, "rounds": 4, **kwargs}


class DashboardCoreTests(unittest.TestCase):
    def test_mirror_and_metadata_declaration(self):
        source = ROOT / "page/dashboard"
        for path in source.rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (ROOT / "pages/dashboard" / path.relative_to(source)).read_bytes())
        metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
        self.assertIn("pages:\n  - name: dashboard\n    title: 赛马游戏", metadata)
        # Current AstrBot uses this locale key for the sidebar and page title,
        # regardless of metadata.pages.title or a literal _page.json title.
        locale = json.loads((ROOT / ".astrbot-plugin/i18n/zh-CN.json").read_text(encoding="utf-8"))
        self.assertEqual(locale["pages"]["dashboard"]["title"], "赛马游戏")
        entry = json.loads((ROOT / "page/dashboard/_page.json").read_text(encoding="utf-8"))
        self.assertEqual(entry["title"]["i18n_key"], "pages.dashboard.title")

    def test_simulation_is_reproducible_without_global_random_changes(self):
        before = random.getstate()
        first = core.simulate(payload(mode="race"))
        self.assertEqual(first, core.simulate(payload(mode="race")))
        self.assertEqual(random.getstate(), before)

    def test_selected_event_and_delayed_effects_use_real_engine(self):
        p = payload(pack=[{"target": 0, "move": 3, "delay_event_self": [2, {"target": 0, "move": 5}]}])
        result = core.simulate(p)
        self.assertGreaterEqual(result["frames"][1]["horses"][0]["position"], 4)
        self.assertGreaterEqual(result["frames"][3]["horses"][0]["delta"], 6)

    def test_add_horse_is_visible_in_simulation_and_spawns_once_for_all_targets(self):
        for extra in ({}, {"uid": "npc-1", "location": 5}):
            result = core.simulate(payload(pack=[{"target": 2, "add_horse": {"horsename": "援军", "owner": "事件玩家", **extra}}], rounds=2))
            self.assertEqual(len(result["frames"][0]["horses"]), 2)
            horses = result["frames"][1]["horses"]
            self.assertEqual(len(horses), 3)
            spawned = horses[-1]
            self.assertEqual(spawned["name"], "援军")
            self.assertEqual(spawned["owner"], "事件玩家")
            self.assertGreaterEqual(spawned["position"], extra.get("location", 0))
            self.assertEqual(len(result["frames"][2]["horses"]), 3)

    def test_totem_and_next_round_leaving_preserved(self):
        for protected in (False, True):
            result = core.simulate(payload(pack=[{"target": 0, "away": 1, "immediate": 1}], players=[{"name": "a", "protected": protected}, {"name": "b"}]))
            self.assertFalse(result["frames"][1]["horses"][0]["away"])
            self.assertEqual(result["frames"][2]["horses"][0]["away"], not protected)

    def test_invalid_inputs_are_rejected(self):
        for p in (payload(rounds=101), payload(players=[]), payload(mode="bad"), payload(seed=-1), payload(pack=[{"target": 99}]), payload(pack=[]), payload(pack=[{"target": 0, "describe": "x" * 150000}])):
            with self.subTest(payload=p), self.assertRaises(ValueError):
                core.simulate(p)

    def test_swap_death_and_stop_have_engine_timing(self):
        base = core.simulate(payload(pack=[{"target": 0}], rounds=3))
        stopped = core.simulate(payload(pack=[{"target": 0, "rounds": 1, "locate_lock": 1}], rounds=3))
        self.assertEqual(stopped["frames"][1]["horses"][0]["position"], base["frames"][1]["horses"][0]["position"])
        self.assertEqual(stopped["frames"][2]["horses"][0]["delta"], 0)
        death = core.simulate(payload(pack=[{"target": 0, "die": 1, "immediate": 1}]))
        self.assertTrue(death["frames"][1]["horses"][0]["dead"])
        self.assertEqual(death["frames"][1]["horses"][0]["position"], 0)
        swapped = core.simulate(payload(pack=[{"target": 1, "track_exchange_location": 1}], players=[{"name": "a", "location": 0}, {"name": "b", "location": 10}], rounds=1))
        self.assertGreaterEqual(swapped["frames"][1]["horses"][0]["position"], 11)
        self.assertLessEqual(swapped["frames"][1]["horses"][1]["position"], 3)

    def test_fanout_is_stopped_by_simulation_budget(self):
        event = {"target": 2}
        for _ in range(5):
            event = {"target": 2, "random_event_once": [[0, event]]}
        with self.assertRaisesRegex(ValueError, "5000"):
            core.simulate(payload(pack=[event], players=[{"name": str(i)} for i in range(8)], rounds=1))

    def test_all_bundled_packs_validate_and_simulate(self):
        for path in (ROOT / "events").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            with self.subTest(path=path.name):
                core.validate_pack(data)
                self.assertTrue(core.simulate(payload(pack=data, mode="race"))["frames"])


class DashboardAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = RaceService({}, Path(self.temp.name), AsyncMock())
        await self.service.initialize()
        self.context = Mock()
        self.api = DashboardAPI(self.context, self.service)

    async def asyncTearDown(self):
        await self.service.terminate()
        self.temp.cleanup()

    async def test_routes_are_namespaced(self):
        routes = [call.args[0] for call in self.context.register_web_api.call_args_list]
        self.assertEqual(len(routes), 7)
        self.assertTrue(all(r.startswith("/astrbot_plugin_horserace/dashboard/") for r in routes))

    async def test_library_validate_and_simulate(self):
        library = await self.api.handle("packs")
        self.assertEqual(len(library["packs"]), 10)
        self.assertEqual((await self.api.handle("validate", payload()))["count"], 1)
        self.assertTrue((await self.api.handle("simulate", payload()))["frames"])

    async def test_save_is_custom_only_and_requires_explicit_overwrite(self):
        body = {"filename": "自定义-测试.json", "pack": payload()["pack"]}
        result = await self.api.handle("save", body)
        self.assertEqual(result["count"], 1)
        path = self.service.custom_dir / body["filename"]
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), body["pack"])
        conflict = await self.api.handle("save", body)
        self.assertTrue(conflict["conflict"])
        body["pack"] = [{"target": 0, "move": 5}]
        await self.api.handle("save", {**body, "overwrite": True})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))[0]["move"], 5)

    async def test_path_traversal_rejected(self):
        for name in ("../x.json", "/tmp/x.json", "a/b.json", "a\\b.json", "a.json/../../x", "x.txt", "..json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                await self.api.handle("save", {"filename": name, "pack": payload()["pack"]})

    async def test_failed_reload_restores_previous_file(self):
        body = {"filename": "rollback.json", "pack": payload()["pack"]}
        await self.api.handle("save", body)
        path = self.service.custom_dir / body["filename"]
        original = path.read_bytes()
        self.service._load = AsyncMock(side_effect=ValueError("reload failed"))
        with self.assertRaises(ValueError):
            await self.api.handle("save", {**body, "overwrite": True, "pack": [{"target": 0}]})
        self.assertEqual(path.read_bytes(), original)

    async def test_failed_reload_removes_new_file(self):
        self.service._load = AsyncMock(side_effect=ValueError("reload failed"))
        with self.assertRaises(ValueError):
            await self.api.handle("save", {"filename": "new.json", "pack": payload()["pack"]})
        self.assertFalse((self.service.custom_dir / "new.json").exists())

    async def test_http_adapter_returns_structured_errors_and_data(self):
        web = ModuleType("astrbot.api.web")
        web.request = Mock()
        web.request.body = AsyncMock(return_value=json.dumps(payload()).encode())
        web.json_response = lambda data, status_code: (data, status_code)
        with patch.dict(sys.modules, {"astrbot.api.web": web}):
            result, status = await self.api.validate()
            self.assertEqual(status, 200)
            self.assertEqual(result["data"]["count"], 1)
            for raw in (b"{bad", b"[]", b"x" * 150000):
                web.request.body.return_value = raw
                result, status = await self.api.validate()
                self.assertEqual(status, 400)
                self.assertEqual(result["status"], "error")

    async def test_closed_api_rejects_requests(self):
        self.api.closed = True
        with self.assertRaises(ValueError):
            await self.api.handle("packs")

    async def test_delete_custom_keeps_builtin_and_running_event_snapshot(self):
        name = "基础事件.json"
        builtin = (self.service.builtin_dir / name).read_bytes()
        pack = [{"target": 0, "event_name": "仅自定义包存在的事件", "move": 2}]
        await self.api.handle("save", {"filename": name, "pack": pack})
        snapshot = self.service.events
        raw = (self.service.custom_dir / name).read_bytes()
        result = await self.api.handle("delete", {"id": "custom/" + name, "confirm": True})
        self.assertFalse((self.service.custom_dir / name).exists())
        backup = self.service.custom_dir.parent / "deleted_events" / result["backup_filename"]
        self.assertEqual(backup.read_bytes(), raw)
        self.assertEqual((self.service.builtin_dir / name).read_bytes(), builtin)
        self.assertTrue(any(e["event_name"] == pack[0]["event_name"] for e in snapshot))
        self.assertFalse(any(e["event_name"] == pack[0]["event_name"] for e in self.service.events))
        with self.assertRaises(ValueError):
            await self.api.handle("delete", {"id": "custom/" + name, "confirm": True})

    async def test_delete_requires_confirmation_and_rejects_builtin_or_traversal(self):
        name = "confirmation.json"
        await self.api.handle("save", {"filename": name, "pack": payload()["pack"]})
        with self.assertRaises(ValueError):
            await self.api.handle("delete", {"id": "custom/" + name})
        self.assertTrue((self.service.custom_dir / name).exists())
        builtin = (self.service.builtin_dir / "基础事件.json").read_bytes()
        for pack_id in ("builtin/基础事件.json", "custom/../基础事件.json", "custom/a/b.json", "custom/a\\b.json", "custom/C:x.json", "custom/file.json:stream.json", "custom/"):
            with self.subTest(pack_id=pack_id), self.assertRaises(ValueError):
                await self.api.handle("delete", {"id": pack_id, "confirm": True})
        self.assertEqual((self.service.builtin_dir / "基础事件.json").read_bytes(), builtin)

    async def test_failed_delete_reload_restores_file_and_memory(self):
        await self.api.handle("save", {"filename": "rollback.json", "pack": payload()["pack"]})
        path = self.service.custom_dir / "rollback.json"
        original, events = path.read_bytes(), self.service.events
        async def broken_reload():
            self.service.events = []
            raise RuntimeError("reload failed")
        self.service._load = broken_reload
        with self.assertRaises(RuntimeError):
            await self.api.handle("delete", {"id": "custom/rollback.json", "confirm": True})
        self.assertEqual(path.read_bytes(), original)
        self.assertIs(self.service.events, events)
        self.assertEqual(list((self.service.custom_dir.parent / "deleted_events").glob("*.json")), [])

    async def test_delete_cancelled_reload_restores_file(self):
        await self.api.handle("save", {"filename": "cancel.json", "pack": payload()["pack"]})
        self.service._load = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await self.api.handle("delete", {"id": "custom/cancel.json", "confirm": True})
        self.assertTrue((self.service.custom_dir / "cancel.json").exists())

    async def test_unreadable_custom_pack_remains_listed_and_deletable(self):
        path = self.service.custom_dir / "坏 JSON.json"
        path.write_bytes(b"not-json")
        listing = await self.api.handle("packs")
        item = next(item for item in listing["packs"] if item["id"] == "custom/坏 JSON.json")
        self.assertIsNone(item["pack"])
        self.assertTrue(item["error"])
        await self.api.handle("delete", {"id": item["id"], "confirm": True})
        self.assertFalse(path.exists())

    async def test_delete_rejects_symlink_to_builtin(self):
        path = self.service.custom_dir / "linked.json"
        try:
            path.symlink_to(self.service.builtin_dir / "基础事件.json")
        except OSError:
            self.skipTest("Creating symlinks requires OS permission")
        with self.assertRaises(ValueError):
            await self.api.handle("delete", {"id": "custom/linked.json", "confirm": True})
        self.assertTrue(path.is_symlink())

    async def test_capabilities_and_disabled_ai_are_enforced_server_side(self):
        caps = await self.api.handle("capabilities")
        self.assertFalse(caps["ai_enabled"])
        self.assertTrue(caps["can_delete_custom"])
        with self.assertRaisesRegex(ValueError, "未开启"):
            await self.api.handle("ai_chat", {"prompt": "生成一个事件"})


if __name__ == "__main__":
    unittest.main()
