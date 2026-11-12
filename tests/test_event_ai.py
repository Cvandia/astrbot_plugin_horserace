"""Native AstrBot model selection and untrusted event-data validation."""
import asyncio
import importlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from test_horserace import PKG

module = importlib.import_module(f"{PKG}.event_ai")
EventAI = module.EventAI
PACK = [{"event_name": "AI测试", "describe": "<0>前进", "target": 0, "move": 3}]


def response(pack=PACK, **extra):
    return SimpleNamespace(completion_text=json.dumps({"reply": "已生成", "filename": "AI测试.json", "pack": pack, **extra}, ensure_ascii=False))


def context():
    provider = SimpleNamespace(meta=lambda: SimpleNamespace(id="native-default"))
    return SimpleNamespace(llm_generate=AsyncMock(return_value=response()),
                           get_using_provider_async=AsyncMock(return_value=provider))


class EventAITests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_ai_never_calls_model(self):
        ctx = context()
        with self.assertRaisesRegex(ValueError, "未开启"):
            await EventAI(ctx, {}).chat({"prompt": "生成事件"})
        ctx.llm_generate.assert_not_awaited()

    async def test_configured_model_has_priority_and_uses_native_api_without_tools(self):
        ctx = context()
        ai = EventAI(ctx, {"enable_ai_event_generator": True, "ai_event_provider_id": " configured-model "})
        result = await ai.chat({"prompt": "生成事件", "provider_id": "client-cannot-override"})
        ctx.get_using_provider_async.assert_not_awaited()
        args = ctx.llm_generate.await_args.kwargs
        self.assertEqual(args["chat_provider_id"], "configured-model")
        self.assertIsNone(args["tools"])
        self.assertIn("下一回合离场", args["system_prompt"])
        self.assertEqual(result["pack"], PACK)

    async def test_unset_model_uses_native_default_provider(self):
        ctx = context()
        await EventAI(ctx, {"enable_ai_event_generator": True}).chat({"prompt": "生成事件"})
        ctx.get_using_provider_async.assert_awaited_once_with()
        self.assertEqual(ctx.llm_generate.await_args.kwargs["chat_provider_id"], "native-default")

    async def test_older_native_provider_getter_is_supported(self):
        ctx = SimpleNamespace(llm_generate=AsyncMock(return_value=response()),
                              get_using_provider=Mock(return_value=SimpleNamespace(meta=lambda: SimpleNamespace(id="legacy-default"))))
        await EventAI(ctx, {"enable_ai_event_generator": True}).chat({"prompt": "生成事件"})
        self.assertEqual(ctx.llm_generate.await_args.kwargs["chat_provider_id"], "legacy-default")

    async def test_selected_model_failure_does_not_fall_back(self):
        ctx = context()
        ctx.llm_generate.side_effect = RuntimeError("provider failed")
        with self.assertRaisesRegex(ValueError, "所选模型调用失败"):
            await EventAI(ctx, {"enable_ai_event_generator": True, "ai_event_provider_id": "chosen"}).chat({"prompt": "生成事件"})
        ctx.get_using_provider_async.assert_not_awaited()
        ctx.llm_generate.assert_awaited_once()

    async def test_history_and_previous_candidate_are_passed_as_bounded_data(self):
        ctx = context()
        history = [{"role": "user", "content": "先生成一个"}, {"role": "assistant", "content": "已生成"}]
        await EventAI(ctx, {"enable_ai_event_generator": True}).chat({"prompt": "改成前进5格", "history": history, "candidate": PACK})
        sent = json.loads(ctx.llm_generate.await_args.kwargs["prompt"])
        self.assertEqual(sent["对话记录"], history)
        self.assertEqual(sent["上一版事件包"], PACK)
        self.assertEqual(sent["本次需求"], "改成前进5格")

    async def test_invalid_input_is_rejected_before_model_call(self):
        ctx = context()
        ai = EventAI(ctx, {"enable_ai_event_generator": True})
        for body in ({"prompt": ""}, {"prompt": "x" * 2001}, {"prompt": "生成", "history": [{"role": "system", "content": "bad"}]}, {"prompt": "生成", "candidate": [{"target": 99}]}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                await ai.chat(body)
        ctx.llm_generate.assert_not_awaited()

    async def test_busy_generation_is_not_queued_and_timeout_is_reported(self):
        ctx = context(); ai = EventAI(ctx, {"enable_ai_event_generator": True})
        async with ai.lock:
            with self.assertRaisesRegex(ValueError, "正在生成"):
                await ai.chat({"prompt": "生成"})
        ctx.llm_generate.side_effect = asyncio.TimeoutError()
        with self.assertRaisesRegex(ValueError, "超时"):
            await ai.chat({"prompt": "生成"})

    async def test_missing_default_model_is_reported_without_generation(self):
        ctx = context(); ctx.get_using_provider_async.return_value = None
        with self.assertRaisesRegex(ValueError, "默认聊天模型"):
            await EventAI(ctx, {"enable_ai_event_generator": True}).chat({"prompt": "生成"})
        ctx.llm_generate.assert_not_awaited()


class EventAIParsingTests(unittest.TestCase):
    def test_add_horse_data_is_supported_in_nested_ai_events(self):
        for horse in ({"horsename": "援军", "owner": "玩家"}, {"horsename": "援军", "owner": "玩家", "uid": 42, "location": 3}, {"horsename": "援军", "owner": "玩家", "uid": "12345678901234567890"}):
            event = {"target": 0, "another_event_self": {"target": 0, "add_horse": horse}}
            self.assertEqual(module.parse_ai_response(response(pack=[event]).completion_text)["pack"], [event])
        self.assertIn("add_horse", module.SYSTEM_PROMPT)

    def test_add_horse_invalid_fields_and_types_are_rejected(self):
        for horse in ({}, {"horsename": "新马"}, {"horsename": " ", "owner": "玩家"}, {"horsename": "新马", "owner": "玩家", "uid": True}, {"horsename": "新马", "owner": "玩家", "uid": 2**53}, {"horsename": "新马", "owner": "玩家", "uid": ""}, {"horsename": "新马", "owner": "玩家", "location": 1.5}, {"horsename": "新马", "owner": "玩家", "location": 1000001}, {"horsename": "新马", "owner": "玩家", "code": "run"}):
            with self.subTest(horse=horse), self.assertRaises(ValueError):
                module.parse_ai_response(response(pack=[{"target": 0, "add_horse": horse}]).completion_text)

    def test_json_fences_and_raw_event_array_are_supported(self):
        raw = response().completion_text
        self.assertEqual(module.parse_ai_response("```json\n" + raw + "\n```")["pack"], PACK)
        self.assertEqual(module.parse_ai_response(json.dumps(PACK))["pack"], PACK)

    def test_clarification_and_safe_filename_fallback(self):
        result = module.parse_ai_response(response(pack=None, filename="../outside.json").completion_text)
        self.assertIsNone(result["pack"])
        self.assertEqual(result["filename"], "AI生成事件.json")

    def test_invalid_data_and_wrong_effect_semantics_are_rejected(self):
        for event in ({"target": 0, "code": "execute"}, {"target": 0, "rounds": 0, "locate_lock": 1}, {"target": 0, "track_exchange_location": 1}, {"target": 0, "away": 1, "immediate": 1}, {"target": 0, "rounds": 1, "other_buff": [123]}, {"target": 0, "move": 1000001}):
            with self.subTest(event=event), self.assertRaises(ValueError):
                module.parse_ai_response(response(pack=[event]).completion_text)
        for raw in ("not json", "{} trailing", "[]", "null"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                module.parse_ai_response(raw)
