"""Bounded, isolated event validation and simulation for the developer page."""
from copy import deepcopy
import json
from random import Random

from .event_loader import validate_event
from .events_main import event_main
from .race_group import race_group
from .settings import Settings
from .start import deal_events

MAX_BODY = 128 * 1024


def validate_pack(pack: object) -> list[dict]:
    if not isinstance(pack, list) or not 1 <= len(pack) <= 128:
        raise ValueError("事件包必须是包含 1~128 条事件的数组")
    try:
        encoded = json.dumps(pack, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("事件包包含无效 JSON 数值") from exc
    if len(encoded.encode("utf-8")) > MAX_BODY:
        raise ValueError("编辑器事件包上限为 128KB")
    for index, event in enumerate(pack):
        try:
            validate_event(event)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"第 {index + 1} 条事件：{exc}") from exc
    return deepcopy(pack)


def integer(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} 必须是 {low}~{high} 的整数")
    return value


def simulate(payload: dict) -> dict:
    pack = deal_events(validate_pack(payload.get("pack")))
    seed = integer(payload.get("seed", 42), "随机种子", 0, 2**32 - 1)
    turns = integer(payload.get("rounds", 12), "回合数", 1, 100)
    mode = payload.get("mode", "selected")
    if mode not in ("selected", "race"):
        raise ValueError("测试模式无效")
    selected = integer(payload.get("selected", 0), "选中事件", 0, len(pack) - 1)
    players = payload.get("players")
    if not isinstance(players, list) or not 2 <= len(players) <= 8:
        raise ValueError("测试需要 2~8 匹马")
    settings = Settings.from_config({
        "setting_track_length": integer(payload.get("length", 20), "跑道长度", 15, 100),
        "max_rounds": turns,
        "event_rate": integer(payload.get("event_rate", 450), "事件概率", 0, 1000),
    })
    race = race_group(settings, rng=Random(seed))
    race.simulation_budget = 5000
    for index, player in enumerate(players):
        if not isinstance(player, dict) or not isinstance(player.get("name"), str):
            raise ValueError("马匹信息无效")
        name = " ".join(player["name"].split())[:24]
        if not name:
            raise ValueError("马名不能为空")
        location = integer(player.get("location", 0), "初始位置", 0, settings.setting_track_length - 1)
        race.add_player(name, str(index), name, location)
        if player.get("protected") is True:
            race.player[-1].grant_negative_immunity()
    actor = integer(payload.get("actor", 0), "发起马匹", 0, len(players) - 1)
    frames = []

    def frame(log: str) -> dict:
        return {"round": race.round, "log": log, "horses": [
            {"name": h.horse, "owner": h.player, "position": h.location,
             "delta": h.location_add, "dead": h.is_die(), "away": h.is_away(),
             "protected": h.negative_immunity, "buffs": [b[0] for b in h.buff if b[1] <= race.round <= b[2]]}
            for h in race.player
        ]}

    frames.append(frame("初始状态"))
    result = "达到测试回合上限"
    for turn in range(turns):
        race.round_add()
        race.del_buff_overtime()
        race.fullname()
        log = race.event_start(pack if mode == "race" else [])
        if mode == "selected" and turn == 0:
            log += event_main(race, actor, pack[selected])
        race.move()
        race.fullname()
        frames.append(frame(log or "本回合无事件"))
        winners = race.is_win_all()
        if winners:
            result = "胜者：" + winners.strip().replace("\n", "、")
            break
        if race.is_die_all():
            result = "全部马匹死亡或离场"
            break
    return {"seed": seed, "length": settings.setting_track_length,
            "mode": mode, "frames": frames, "result": result}
