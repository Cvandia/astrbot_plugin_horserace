"""Validated configuration; each race keeps a snapshot of its rules."""
from dataclasses import dataclass, fields
import math


@dataclass(frozen=True)
class Settings:
    setting_track_length: int = 20
    setting_random_min_length: int = 0
    setting_random_max_length: int = 15
    base_move_min: int = 1
    base_move_max: int = 3
    max_player: int = 8
    min_player: int = 2
    setting_over_time: int = 120
    event_rate: int = 450
    round_interval: float = 6.0
    max_rounds: int = 100
    image_mode: bool = False

    @classmethod
    def from_config(cls, config: dict) -> "Settings":
        defaults = cls()
        values = {}
        for f in fields(cls):
            default = getattr(defaults, f.name)
            raw = config.get(f.name, default)
            if isinstance(default, bool):
                if not isinstance(raw, bool):
                    raise ValueError(f"{f.name} 必须是布尔值")
                values[f.name] = raw
            elif isinstance(default, int):
                if isinstance(raw, bool) or not isinstance(raw, int):
                    raise ValueError(f"{f.name} 必须是整数")
                values[f.name] = raw
            else:
                if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
                    raise ValueError(f"{f.name} 必须是有限数值")
                values[f.name] = float(raw)
        s = cls(**values)
        if not (5 <= s.setting_track_length <= 100):
            raise ValueError("跑道长度必须在 5~100 之间")
        if not (0 <= s.setting_random_min_length <= s.setting_random_max_length <= s.setting_track_length):
            raise ValueError("随机位置范围必须位于跑道内，且最小值不大于最大值")
        if not (1 <= s.base_move_min <= s.base_move_max <= 20):
            raise ValueError("基础移动范围必须满足 1 <= 最小值 <= 最大值 <= 20")
        if not (2 <= s.min_player <= s.max_player <= 16):
            raise ValueError("人数必须满足 2 <= 最少人数 <= 最多人数 <= 16")
        if not (0 <= s.event_rate <= 1000 and 1 <= s.round_interval <= 60 and 1 <= s.max_rounds <= 500 and 10 <= s.setting_over_time <= 3600):
            raise ValueError("事件概率、回合间隔、回合上限或重置时间超出允许范围")
        return s
