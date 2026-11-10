"""Engine regressions and adapter lifecycle tests (AstrBot transport is a double)."""
import asyncio
import ast
from dataclasses import replace
import importlib
import json
import logging
from pathlib import Path
import random
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
PKG = ROOT.name
Settings = importlib.import_module(f"{PKG}.settings").Settings
race_group = importlib.import_module(f"{PKG}.race_group").race_group
event_main = importlib.import_module(f"{PKG}.events_main").event_main
deal = importlib.import_module(f"{PKG}.start").deal
load_events = importlib.import_module(f"{PKG}.event_loader").load_events

# Explicit doubles: no claim that these tests launch the AstrBot runtime.
api = types.ModuleType("astrbot.api")
api.AstrBotConfig = dict
api.logger = logging.getLogger("test.astrbot")
event_api = types.ModuleType("astrbot.api.event")
event_api.AstrMessageEvent = object
sys.modules["astrbot"] = types.ModuleType("astrbot")
sys.modules["astrbot.api"] = api
sys.modules["astrbot.api.event"] = event_api
RaceService = importlib.import_module(f"{PKG}.service").RaceService


class Event:
    def __init__(self, user="1", group="g", platform="p", text="", admin=False):
        self.user, self.group, self.platform = user, group, platform
        self.message_str, self.admin = text, admin
        self.messages = []
        self.fail = False

    def get_sender_id(self): return self.user
    def get_sender_name(self): return f"user-{self.user}"
    def get_group_id(self): return self.group
    def get_platform_id(self): return self.platform
    def is_admin(self): return self.admin
    def plain_result(self, text): return text
    def image_result(self, url): return "image:" + url

    async def send(self, result):
        if self.fail:
            raise RuntimeError("transport offline")
        self.messages.append(result)


async def consume(generator):
    return [item async for item in generator]


def make_race(settings=None):
    r = race_group(settings)
    r.add_player("a", "1", "alice")
    r.add_player("b", "2", "bob")
    return r


class EngineTests(unittest.TestCase):
    def test_all_bundled_packs_and_reload(self):
        a, logs = load_events(ROOT / "events", Path("missing-custom-folder"))
        b, _ = load_events(ROOT / "events", Path("missing-custom-folder"))
        self.assertEqual(len(a), 103)
        self.assertEqual(a, b)
        self.assertEqual(len(logs), 9)
        self.assertFalse(any("失败" in line for line in logs))

    def test_bad_pack_does_not_remove_valid_pack(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            (p / "bad.json").write_text('{bad', encoding="utf-8")
            (p / "good.json").write_text('[{"target":0,"move":2}]', encoding="utf-8")
            events, logs = load_events(Path("missing"), p)
            self.assertEqual(len(events), 1)
            self.assertTrue(any("失败" in s for s in logs))

    def test_normalize_does_not_mutate_source(self):
        raw = {"target": 0, "random_event_once": [[5, {"target": 0, "move": 1}]]}
        before = json.dumps(raw)
        deal(raw)
        self.assertEqual(before, json.dumps(raw))

    def test_delayed_event(self):
        r = make_race(Settings(event_rate=0))
        event_main(r, 0, deal({"target": 0, "delay_event": [2, {"target": 0, "move": 5, "describe": "delayed"}]}))
        self.assertEqual(len(r.player[0].delay_events), 1)
        r.round_add()
        self.assertNotIn("delayed", r.event_start([]))
        r.round_add()
        self.assertIn("delayed", r.event_start([]))
        self.assertEqual(r.player[0].location_add_move, 5)
        self.assertEqual(r.player[0].delay_events, [])

    def test_replace_keeps_location_and_round(self):
        r = make_race()
        r.round_add()
        r.player[0].location = 8
        text = event_main(r, 0, deal({"target": 0, "replace_horse": {"horsename": "new"}}))
        self.assertNotIn("故障", text)
        self.assertEqual((r.player[0].horse, r.player[0].location, r.player[0].round), ("new", 8, 1))

    def test_zero_probability_and_empty_event_list(self):
        for s in (Settings(), Settings(event_rate=0)):
            r = make_race(s)
            self.assertEqual(r.event_start([]), "")

    def test_rules_are_isolated_between_races(self):
        a = make_race(Settings(base_move_min=1, base_move_max=1, setting_track_length=20))
        b = make_race(Settings(base_move_min=5, base_move_max=5, setting_track_length=40))
        a.move()
        b.move()
        self.assertEqual(a.player[0].location, 1)
        self.assertEqual(b.player[0].location, 5)

    def test_dead_or_away_horse_cannot_win(self):
        r = make_race()
        for i, tag in enumerate(("die", "away")):
            r.player[i].location = 20
            r.player[i].add_buff(tag, 0, 99, [tag])
        self.assertEqual(r.is_win_all(), "")
        self.assertTrue(r.is_die_all())

    def test_tied_winners(self):
        r = make_race()
        for h in r.player:
            h.location = 20
        self.assertIn("alice", r.is_win_all())
        self.assertIn("bob", r.is_win_all())

    def test_delete_named_buff(self):
        h = make_race().player[0]
        h.add_buff("fast", 0, 5, [], 1, 1)
        h.del_buff("fast")
        h.del_buff_overtime(1)
        self.assertEqual(h.buff, [])

    def test_string_buff_removal_and_delayed_replacement(self):
        r = make_race(Settings(event_rate=0))
        r.player[0].add_buff("dead", 0, 10, ["die"])
        event_main(r, 0, deal({"target": 0, "del_buff": "die"}), 1)
        r.round_add()
        r.del_buff_overtime()
        self.assertFalse(r.player[0].is_die())
        event_main(r, 0, deal({"target": 0, "delay_event": [2, {"target": 0, "replace_horse": {"horsename": "new"}}]}))
        r.round_add()
        r.round_add()
        r.event_start([])
        self.assertEqual(r.player[0].horse, "new")

    def test_thin_entrypoint_registers_groups_and_admin_gates(self):
        module = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        plugin = next(n for n in module.body if isinstance(n, ast.ClassDef))
        methods = {n.name: n for n in plugin.body if isinstance(n, ast.AsyncFunctionDef)}
        commands = {k: v for k, v in methods.items() if v.decorator_list}
        self.assertEqual(len(commands), 9)
        for name in ("pause", "clear", "reload_events"):
            self.assertTrue(any("PermissionType.ADMIN" in ast.unparse(d) for d in commands[name].decorator_list))
        for name in ("create", "join", "start", "status", "reset", "pause", "clear"):
            self.assertTrue(any("GROUP_MESSAGE" in ast.unparse(d) for d in commands[name].decorator_list))
        for command in commands.values():
            self.assertEqual(len(command.body), 2)  # docstring + delegation only

    def test_once_random_draws_once_per_target(self):
        r = make_race()
        e = deal({"target": 0, "random_event_once": [[0, {"target": 0, "move": 1}], [10, {"target": 0, "move": 5}]]})
        with patch(f"{PKG}.events_main.random.randint", return_value=9) as rng:
            event_main(r, 0, e)
        self.assertEqual(rng.call_count, 1)
        self.assertEqual(r.player[0].location_add_move, 5)

    def test_spawn_limit(self):
        r = make_race()
        for _ in range(100):
            r.add_player()
        self.assertEqual(len(r.player), 32)

    def test_settings_reject_invalid_values(self):
        for invalid in ({"event_rate": -1}, {"round_interval": float("nan")}, {"min_player": 9}, {"base_move_min": 9}, {"event_rate": "450"}, {"image_mode": "false"}):
            with self.subTest(config=invalid), self.assertRaises(ValueError):
                Settings.from_config(invalid)

    def test_each_bundled_event_executes_without_fault(self):
        events, _ = load_events(ROOT / "events", Path("missing"))
        for seed in range(5):
            random.seed(seed)
            for e in events:
                r = make_race()
                r.add_player("c", "3", "carol")
                r.round_add()
                result = event_main(r, 1, e)
                self.assertNotIn("执行故障", result, e["event_name"])

    def test_200_seeded_full_races(self):
        events, _ = load_events(ROOT / "events", Path("missing"))
        for seed in range(200):
            random.seed(seed)
            r = make_race()
            for _ in range(100):
                r.round_add()
                r.del_buff_overtime()
                r.fullname()
                self.assertNotIn("执行故障", r.event_start(events), f"seed={seed}")
                r.move()
                for h in r.player:
                    self.assertTrue(0 <= h.location <= 20)
                if r.is_die_all() or r.is_win_all():
                    break


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        async def render(text): return "https://example.test/image.png"
        self.service = RaceService({"event_rate": 0, "max_rounds": 1}, Path(self.temp.name), render)
        await self.service.initialize()
        self.owner = Event(text="赛马加入 白 色 闪电")

    async def asyncTearDown(self):
        await self.service.terminate()
        self.temp.cleanup()

    async def ready(self):
        await consume(self.service.create(self.owner))
        await consume(self.service.join(self.owner))
        await consume(self.service.join(Event(user="2", text="赛马加入 赤兔")))
        return self.service._room(self.owner)

    async def test_duplicate_join_and_full_name(self):
        room = await self.ready()
        self.assertEqual(room.race.player[0].horse, "白 色 闪电")
        result = await consume(self.service.join(self.owner))
        self.assertIn("已经报名", result[0])
        self.assertEqual(len(room.race.player), 2)

    async def test_group_and_platform_isolation(self):
        await self.ready()
        await consume(self.service.create(Event(group="g2")))
        await consume(self.service.create(Event(platform="p2")))
        self.assertEqual(len(self.service.rooms), 3)
        self.assertIs(self.service._room(Event(user="2")), self.service._room(self.owner))

    async def test_only_creator_starts(self):
        room = await self.ready()
        result = await consume(self.service.start(Event(user="2")))
        self.assertIn("只有", result[0])
        self.assertIsNone(room.task)

    async def test_duplicate_start_creates_one_task(self):
        room = await self.ready()
        await consume(self.service.start(self.owner))
        task = room.task
        await consume(self.service.start(self.owner))
        self.assertIs(task, room.task)
        await task
        self.assertFalse(self.service.rooms)

    async def test_pause_resume_and_clear(self):
        room = await self.ready()
        room.race.settings = replace(room.race.settings, max_rounds=100)
        await consume(self.service.start(self.owner))
        await asyncio.sleep(0)
        await consume(self.service.pause(Event(admin=True)))
        turn = room.race.round
        self.assertEqual(room.race.start, 2)
        self.assertIsNone(room.task)
        await consume(self.service.start(self.owner))
        await asyncio.sleep(0)
        self.assertGreater(room.race.round, turn)
        await consume(self.service.clear(Event(admin=True)))
        self.assertFalse(self.service.rooms)

    async def test_reset_needs_timeout(self):
        room = await self.ready()
        self.assertIn("尚未超时", (await consume(self.service.reset(self.owner)))[0])
        room.race.time = time.time() - 1000
        await consume(self.service.reset(Event(user="2")))
        self.assertFalse(self.service.rooms)

    async def test_reload_does_not_duplicate(self):
        await self.service._load()
        self.assertEqual(len(self.service.events), 103)

    async def test_reload_failure_keeps_old_events(self):
        self.service.builtin_dir = Path(self.temp.name) / "missing"
        old = self.service.events
        with self.assertRaises(ValueError):
            await self.service._load()
        self.assertIs(self.service.events, old)

    async def test_renderer_failure_falls_back(self):
        async def fail(text): raise RuntimeError("render offline")
        self.service.render = fail
        await self.service._send_board(self.owner, "board", True)
        self.assertEqual(self.owner.messages, ["board"])

    async def test_send_failure_releases_room(self):
        room = await self.ready()
        await consume(self.service.start(self.owner))
        self.owner.fail = True
        with self.assertLogs("test.astrbot", level="ERROR"):
            await room.task
        self.assertFalse(self.service.rooms)

    async def test_unload_cancels_active_tasks(self):
        room = await self.ready()
        await consume(self.service.start(self.owner))
        task = room.task
        await self.service.terminate()
        self.assertTrue(task.done())
        self.assertFalse(self.service.rooms)

    async def test_start_acknowledgement_failure_can_retry(self):
        room = await self.ready()
        self.owner.fail = True
        with self.assertRaises(RuntimeError):
            await consume(self.service.start(self.owner))
        self.assertEqual(room.race.start, 0)
        self.assertIsNone(room.task)
        self.assertIsNotNone(room.idle_task)

    async def test_reset_cancels_running_task(self):
        room = await self.ready()
        await consume(self.service.start(self.owner))
        task = room.task
        room.race.time = time.time() - 1000
        await consume(self.service.reset(self.owner))
        self.assertTrue(task.done())
        self.assertFalse(self.service.rooms)

    async def test_clear_old_task_does_not_delete_new_room(self):
        old = await self.ready()
        old.race.start = 1
        key = self.service._key(self.owner)
        self.service.rooms.pop(key)
        await consume(self.service.create(self.owner))
        new = self.service.rooms[key]
        await self.service._run(self.owner, key, old, self.service.events)
        self.assertIs(self.service.rooms[key], new)

    async def test_empty_lobby_expires_after_sixty_seconds(self):
        await consume(self.service.create(self.owner))
        room = self.service._room(self.owner)
        room.last_join_at -= 61
        await asyncio.wait_for(room.idle_task, timeout=1)
        self.assertFalse(self.service.rooms)
        self.assertIn("自动清空", self.owner.messages[-1])

    async def test_successful_join_refreshes_deadline(self):
        await consume(self.service.create(self.owner))
        room = self.service._room(self.owner)
        timer = room.idle_task
        room.last_join_at -= 59
        await consume(self.service.join(self.owner))
        self.assertLess(time.monotonic() - room.last_join_at, 1)
        self.assertIs(room.idle_task, timer)
        last_join = room.last_join_at
        await consume(self.service.join(self.owner))  # duplicate
        await consume(self.service.join(Event(user="2", text="赛马加入")))
        await consume(self.service.status(self.owner))
        self.assertEqual(room.last_join_at, last_join)
        room.last_join_at -= 61
        await asyncio.wait_for(timer, timeout=1)
        self.assertFalse(self.service.rooms)

    async def test_sleeping_timer_rechecks_extended_deadline(self):
        await consume(self.service.create(self.owner))
        room = self.service._room(self.owner)
        await self.service._cancel_idle(room)
        room.last_join_at = 0

        async def simulate_join(delay):
            if delay == 60:
                room.last_join_at = 50

        with patch(f"{PKG}.service.time") as clock, patch(
            f"{PKG}.service.asyncio.sleep", new=AsyncMock(side_effect=simulate_join)
        ) as sleep:
            clock.monotonic.side_effect = [0, 61, 111]
            await self.service._watch_idle(self.owner, self.service._key(self.owner), room)
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [60, 49])
        self.assertFalse(self.service.rooms)

    async def test_started_and_paused_race_ignore_lobby_timeout(self):
        room = await self.ready()
        room.race.settings = replace(room.race.settings, max_rounds=100)
        timer = room.idle_task
        await consume(self.service.start(self.owner))
        self.assertTrue(timer.done())
        self.assertIsNone(room.idle_task)
        room.last_join_at -= 61
        await self.service._watch_idle(self.owner, self.service._key(self.owner), room)
        self.assertIs(self.service._room(self.owner), room)
        await consume(self.service.pause(Event(admin=True)))
        await self.service._watch_idle(self.owner, self.service._key(self.owner), room)
        self.assertIs(self.service._room(self.owner), room)

    async def test_clear_reset_and_unload_cancel_lobby_timer(self):
        for action in (self.service.clear, self.service.reset, None):
            await consume(self.service.create(self.owner))
            room = self.service._room(self.owner)
            timer = room.idle_task
            room.race.time -= 1000
            if action:
                await consume(action(self.owner))
            else:
                await self.service.terminate()
            self.assertTrue(timer.done())
            self.assertFalse(self.service.rooms)
        self.assertFalse(self.owner.messages)

    async def test_old_lobby_timer_cannot_remove_new_room(self):
        await consume(self.service.create(self.owner))
        old = self.service._room(self.owner)
        await self.service._cancel_idle(old)
        self.service.rooms.pop(self.service._key(self.owner))
        await consume(self.service.create(self.owner))
        new = self.service._room(self.owner)
        old.last_join_at -= 61
        await self.service._watch_idle(self.owner, self.service._key(self.owner), old)
        self.assertIs(self.service._room(self.owner), new)
        self.assertFalse(self.owner.messages)

    async def test_timeout_notification_failure_still_releases_room(self):
        await consume(self.service.create(self.owner))
        room = self.service._room(self.owner)
        room.last_join_at -= 61
        self.owner.fail = True
        with self.assertLogs("test.astrbot", level="ERROR"):
            await asyncio.wait_for(room.idle_task, timeout=1)
        self.assertFalse(self.service.rooms)

    async def test_unload_cancels_notification_after_room_removed(self):
        await consume(self.service.create(self.owner))
        room = self.service._room(self.owner)
        room.last_join_at -= 61
        sending = asyncio.Event()
        async def blocked_send(result):
            sending.set()
            await asyncio.Future()
        self.owner.send = blocked_send
        timer = room.idle_task
        await asyncio.wait_for(sending.wait(), timeout=1)
        self.assertFalse(self.service.rooms)
        await self.service.terminate()
        self.assertTrue(timer.done())
        self.assertFalse(self.service.idle_tasks)


if __name__ == "__main__":
    unittest.main()
