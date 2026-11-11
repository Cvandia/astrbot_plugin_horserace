"""Load original JSON event packs, with isolated failures and atomic replacement."""
import json
from pathlib import Path
from .start import deal_events


def validate_event(event: dict, depth: int = 0) -> None:
    if depth > 20 or not isinstance(event, dict):
        raise ValueError("事件必须是对象，嵌套不能超过 20 层")
    if type(event.get("target")) is not int or not 0 <= event["target"] <= 7:
        raise ValueError("target 必须是 0~7 的整数")
    for key in ("negative_immunity", "immediate"):
        if key in event and (type(event[key]) is not int or event[key] not in (0, 1)):
            raise ValueError(f"{key} 必须是 0 或 1")
    for key in ("describe", "event_name", "name", "die_name", "away_name", "target_is_buff", "target_no_buff"):
        if key in event and not isinstance(event[key], str):
            raise ValueError(f"{key} 必须是字符串")
    for key in ("move", "rounds", "move_min", "move_max", "track_to_location", "buff_time_add", "live", "die", "away", "locate_lock", "vertigo", "hiding", "track_random_location", "track_exchange_location"):
        if key in event and type(event[key]) is not int:
            raise ValueError(f"{key} 必须是整数")
    for key in ("other_buff", "del_buff"):
        if key in event and not isinstance(event[key], (str, list)):
            raise ValueError(f"{key} 必须是标签列表或字符串")
    for key in ("add_horse", "replace_horse"):
        if key in event and not isinstance(event[key], dict):
            raise ValueError(f"{key} 必须是对象")
    for key in ("another_event", "another_event_self"):
        if event.get(key):
            validate_event(event[key], depth + 1)
    for key in ("delay_event", "delay_event_self"):
        pair = event.get(key, [])
        if pair:
            if not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not int or pair[0] < 2:
                raise ValueError(f"{key} 必须是 [至少2回合, 事件]")
            validate_event(pair[1], depth + 1)
    for key in ("random_event", "random_event_once"):
        items = event.get(key, [])
        if not isinstance(items, list):
            raise ValueError(f"{key} 必须是列表")
        last = -1
        for pair in items:
            if not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not int or pair[0] <= last:
                raise ValueError(f"{key} 的概率阈值必须是严格递增的非负整数")
            last = pair[0]
            validate_event(pair[1], depth + 1)


def load_events(builtin: Path, custom: Path) -> tuple[list[dict], list[str]]:
    events, logs = [], []
    for folder in (builtin, custom):
        for path in sorted(folder.glob("*.json")):
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("单个事件包不能超过 2MB")
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(raw, list):
                    raise ValueError("事件包顶层必须是数组")
                for event in raw:
                    validate_event(event)
                normalized = deal_events(raw)
                events.extend(normalized)
                logs.append(f"{path.name}: 成功 ({len(normalized)} 条)")
            except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
                logs.append(f"{path.name}: 失败 ({exc})")
    return events, logs
