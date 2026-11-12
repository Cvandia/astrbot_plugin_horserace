"""Generate event data through AstrBot's configured chat provider, without tools."""
import asyncio
import json
import re

from astrbot.api import logger

from .dashboard_core import MAX_BODY, validate_pack


SYSTEM_PROMPT = """你是赛马事件包编辑助手。根据本工作台对话生成或修改完整的自定义事件包。
仅返回 JSON 对象：{"reply":"中文说明或追问","filename":"自定义事件.json","pack":[事件对象]}。
需要追问时 pack 为 null；修改上一版时返回完整事件包，不返回差异。默认生成 1~8 条，最多128条。
名称、消息、buff 显示名可自由编写。消息 <0> 代表发起马，<1> 代表目标。不要输出程序代码。
每个事件 target 必填：0自己，1随机另一匹，2全场，3其他全部，4全场随机一匹，5自己和另一匹，6相邻一匹，7两侧。
基础字段 event_name/describe 为字符串；move 为额外位移整数；track_to_location 为传送位置整数。
track_random_location=1随机传送；track_exchange_location=1交换位置，只能搭配target=1或6；live=1复活。
die=1死亡，immediate=1仅让死亡当回合生效；away=1永远下一回合离场，不能立即离场。
negative_immunity=1授予本场负面免疫，保留正面效果。它不需要 rounds，也不能被普通移除。
持续 buff：rounds为正整数，name为显示名，move_min/move_max为移动加成；locate_lock=1停滞，vertigo=1眩晕，hiding=1隐藏。
持续buff从下一回合生效，因此停留一回合用 rounds=1,locate_lock=1。other_buff 是自定义buff标识字符串数组。
target_is_buff/target_no_buff 为必须有/不能有的一个buff标识；del_buff为移除的buff标识或显示名数组；buff_time_add为时长增减整数。
内置buff标识：die、away、locate_lock、vertigo、hiding、negative_immunity（仅条件判断）。
随机分支 random_event_once=[[累计阈值,子事件],...]，阈值从0起严格递增、抽取区间含端点。
例如胜负各50%用阈值49、99。random_event格式相同，但需配合rounds，在持续buff期间每回合触发。
delay_event=[至少2回合,子事件]由目标发起；delay_event_self由原发起者发起。
another_event/another_event_self 为立即执行的子事件对象，分别由目标/原发起者发起。
race_only为本场唯一字符串标识。可选字段省略，不填无意义的0或空数组。
只使用以上字段；各类开关值为0或1。每个子事件也必须有target。禁止请求工具或执行外部操作。
文件名仅中英文、数字、下划线、短横线，以.json结尾。生成结果会经过严格校验，不能直接执行或写入文件。
"""

FLAGS = {"die", "immediate", "away", "live", "negative_immunity", "locate_lock", "vertigo", "hiding", "track_exchange_location", "track_random_location"}
FIELDS = FLAGS | {"target", "event_name", "describe", "move", "track_to_location", "buff_time_add", "del_buff", "die_name", "away_name", "rounds", "name", "move_min", "move_max", "other_buff", "race_only", "target_is_buff", "target_no_buff", "random_event_once", "random_event", "delay_event", "delay_event_self", "another_event", "another_event_self"}


def validate_ai_pack(pack):
    pack = validate_pack(pack)
    budget = 1000

    def visit(event):
        nonlocal budget
        budget -= 1
        if budget < 0:
            raise ValueError("AI 事件嵌套过多，请减少事件数量")
        unknown = set(event) - FIELDS
        if unknown:
            raise ValueError("AI 生成了不支持的字段：" + ", ".join(sorted(unknown)))
        for key in FLAGS:
            if key in event and event[key] not in (0, 1):
                raise ValueError(f"{key} 必须为 0 或 1")
        if "race_only" in event and not isinstance(event["race_only"], str):
            raise ValueError("race_only 必须是字符串")
        for key in ("del_buff", "other_buff"):
            if key in event:
                if key == "other_buff" and not isinstance(event[key], list):
                    raise ValueError("other_buff 必须为字符串数组")
                values = event[key] if isinstance(event[key], list) else [event[key]]
                if not all(isinstance(value, str) for value in values):
                    raise ValueError(f"{key} 必须为 buff 字符串或字符串数组")
        for key, value in event.items():
            if type(value) is int and abs(value) > 1000000:
                raise ValueError(f"{key} 数值过大，请使用合理的游戏数值")
        if event.get("track_exchange_location") == 1 and event["target"] not in (1, 6):
            raise ValueError("交换位置的 target 必须为 1 或 6")
        if event.get("immediate") == 1 and event.get("die") != 1:
            raise ValueError("immediate 仅可用于死亡，离场仍在下一回合生效")
        if any(event.get(key) for key in ("locate_lock", "vertigo", "hiding", "move_min", "move_max", "random_event", "other_buff")) and event.get("rounds", 0) <= 0:
            raise ValueError("持续 buff 需要大于 0 的 rounds")
        for key in ("another_event", "another_event_self"):
            if event.get(key):
                visit(event[key])
        for key in ("delay_event", "delay_event_self"):
            if event.get(key):
                visit(event[key][1])
        for key in ("random_event_once", "random_event"):
            for pair in event.get(key, []):
                if pair[0] > 1000000:
                    raise ValueError("随机分支权重过大")
                visit(pair[1])

    for event in pack:
        visit(event)
    return pack


def parse_ai_response(text):
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > MAX_BODY + 8192:
        raise ValueError("模型返回为空或过大，请重新描述需求")
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced:
        text = fenced[1]
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise ValueError("模型未返回有效事件 JSON，请让 AI 重新生成") from exc
    if isinstance(data, list):
        data = {"pack": data, "reply": "已生成事件包，请检查后导入或保存。"}
    if not isinstance(data, dict):
        raise ValueError("模型返回格式无效")
    reply = data.get("reply", "")
    if not isinstance(reply, str):
        raise ValueError("模型说明必须是文字")
    pack = validate_ai_pack(data["pack"]) if data.get("pack") is not None else None
    filename = data.get("filename", "AI生成事件.json")
    if not isinstance(filename, str) or not re.fullmatch(r"[\w\-\u4e00-\u9fff]{1,64}\.json", filename):
        filename = "AI生成事件.json"
    return {"reply": reply[:4000] or ("已生成事件包，请检查后导入或保存。" if pack else "请补充想生成的事件内容。"), "filename": filename, "pack": pack}


class EventAI:
    def __init__(self, context, config):
        self.context = context
        self.config = config
        self.lock = asyncio.Lock()

    def capabilities(self):
        provider = self.config.get("ai_event_provider_id", "")
        return {"ai_enabled": self.config.get("enable_ai_event_generator", False) is True,
                "ai_provider_id": provider.strip() if isinstance(provider, str) else ""}

    async def chat(self, body):
        if not self.capabilities()["ai_enabled"]:
            raise ValueError("未开启 AI 事件生成，请先在插件配置中启用")
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
            raise ValueError("请填写 1~2000 字的事件需求")
        history = body.get("history", [])
        if not isinstance(history, list) or len(history) > 8:
            raise ValueError("对话历史最多 8 条")
        messages = []
        for item in history:
            if not isinstance(item, dict) or item.get("role") not in ("user", "assistant") or not isinstance(item.get("content"), str) or len(item["content"]) > 2000:
                raise ValueError("对话历史格式无效")
            messages.append({"role": item["role"], "content": item["content"]})
        candidate = body.get("candidate")
        if candidate is not None:
            candidate = validate_ai_pack(candidate)
        if self.lock.locked():
            raise ValueError("AI 正在生成，请稍后再试")
        async with self.lock:
            # Honour an explicit provider selection. Never silently switch models
            # after an explicit selection fails.
            provider_id = self.capabilities()["ai_provider_id"]
            if not provider_id:
                if hasattr(self.context, "get_using_provider_async"):
                    provider = await self.context.get_using_provider_async()
                else:
                    provider = self.context.get_using_provider()
                if not provider:
                    raise ValueError("未找到 AstrBot 默认聊天模型，请在插件配置中选择模型")
                provider_id = provider.meta().id
            request = json.dumps({"对话记录": messages, "上一版事件包": candidate, "本次需求": prompt.strip()}, ensure_ascii=False)
            try:
                response = await asyncio.wait_for(self.context.llm_generate(
                    chat_provider_id=provider_id, prompt=request,
                    system_prompt=SYSTEM_PROMPT, tools=None,
                ), timeout=90)
            except asyncio.TimeoutError as exc:
                raise ValueError("AI 生成超时，请稍后再试或选择其他模型") from exc
            except Exception as exc:
                logger.exception("[horserace] AstrBot 原生 AI 事件生成失败")
                raise ValueError("所选模型调用失败，请检查 AstrBot 模型配置和日志") from exc
            if not self.capabilities()["ai_enabled"]:
                raise ValueError("AI 事件生成已关闭")
            return parse_ai_response(response.completion_text)
