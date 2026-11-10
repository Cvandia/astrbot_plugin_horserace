"""Room management, command behavior and async race lifecycle."""
import asyncio
from dataclasses import dataclass
from pathlib import Path
import time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent

from .event_loader import load_events
from .race_group import race_group
from .settings import Settings


@dataclass
class Room:
    race: race_group
    owner: str
    task: asyncio.Task | None = None


class RaceService:
    def __init__(self, config: AstrBotConfig, data_dir: Path, render):
        self.render = render
        self.config = config
        self.rooms: dict[tuple[str, str], Room] = {}
        self.events: list[dict] = []
        self.custom_dir = data_dir / "events"
        self.custom_dir.mkdir(parents=True, exist_ok=True)
        self.builtin_dir = Path(__file__).parent / "events"
        self.loaded = False
        self.load_lock = asyncio.Lock()

    async def initialize(self) -> None:
        await self._load()

    async def _load(self) -> list[str]:
        async with self.load_lock:
            events, logs = await asyncio.to_thread(load_events, self.builtin_dir, self.custom_dir)
            if not events:
                raise ValueError("没有可用事件，原事件列表保持不变。" + "\n".join(logs))
            self.events = events
            self.loaded = True
            logger.info("[horserace] " + "\n".join(logs))
            return logs

    def _key(self, event: AstrMessageEvent) -> tuple[str, str]:
        # Use actual group ID even if AstrBot enables per-user group sessions.
        return str(event.get_platform_id()), str(event.get_group_id())

    def _room(self, event: AstrMessageEvent) -> Room | None:
        return self.rooms.get(self._key(event))

    @staticmethod
    def _clean_name(value: str) -> str:
        return " ".join(value.split())[:24]

    async def _cancel(self, room: Room) -> None:
        if room.task and not room.task.done():
            room.task.cancel()
            await asyncio.gather(room.task, return_exceptions=True)
        room.task = None

    async def help(self, event: AstrMessageEvent):
        """显示赛马指令。"""
        yield event.plain_result(
            "赛马创建 → 赛马加入 马名 → 赛马开始\n"
            "赛马状态：查看赛况；赛马重置：超时后重置\n"
            "赛马暂停 / 赛马清空 / 赛马事件重载：AstrBot 管理员专用\n"
            "暂停后由创建者或管理员发送 赛马开始 继续。"
        )

    async def create(self, event: AstrMessageEvent):
        """在当前群创建一场赛马。"""
        try:
            settings = Settings.from_config(self.config)
            if not self.loaded:
                await self._load()
        except ValueError as exc:
            yield event.plain_result(f"创建失败：{exc}")
            return
        key = self._key(event)
        if key in self.rooms:
            yield event.plain_result("本群已有赛马，请加入或查看赛马状态；超时可发送 赛马重置。")
            return
        self.rooms[key] = Room(race_group(settings), str(event.get_sender_id()))
        yield event.plain_result("赛马创建成功！发送 赛马加入 马名 报名。")

    async def join(self, event: AstrMessageEvent):
        """报名赛马，命令后跟马名，可含空格。"""
        # No typed argument: retain the complete remaining name, including spaces.
        text = event.message_str.strip()
        name = self._clean_name(text.partition("赛马加入")[2])
        room = self._room(event)
        if not room:
            reply = "请先发送 赛马创建。"
        elif room.race.start != 0:
            reply = "比赛已开始，不能继续报名。"
        elif not name:
            reply = "请输入马名：赛马加入 闪电"
        elif room.race.is_player_in(str(event.get_sender_id())):
            reply = "你已经报名了。"
        elif room.race.query_of_player() >= room.race.settings.max_player:
            reply = "赛马场已满。"
        else:
            room.race.add_player(name, str(event.get_sender_id()), self._clean_name(event.get_sender_name()) or str(event.get_sender_id()))
            reply = f"{name} 加入成功！{room.race.query_of_player()}/{room.race.settings.max_player} 人"
        yield event.plain_result(reply)

    async def start(self, event: AstrMessageEvent):
        """由创建者或管理员开始、继续比赛。"""
        room = self._room(event)
        if not room:
            reply = "请先发送 赛马创建。"
        elif str(event.get_sender_id()) != room.owner and not event.is_admin():
            reply = "只有比赛创建者或 AstrBot 管理员能开始比赛。"
        elif room.race.start == 1 or (room.task and not room.task.done()):
            reply = "比赛正在进行中。"
        elif room.race.query_of_player() < room.race.settings.min_player:
            reply = f"至少需要 {room.race.settings.min_player} 人报名。"
        else:
            room.race.start = 1
            room.race.time = time.time()
            # Reserve running state before yielding, launch only after acknowledgement.
            try:
                await event.send(event.plain_result("比赛开始！"))
            except Exception:
                room.race.start = 2 if room.race.round else 0
                raise
            if self.rooms.get(self._key(event)) is room and room.race.start == 1:
                room.task = asyncio.create_task(self._run(event, self._key(event), room, self.events))
            return
        yield event.plain_result(reply)

    async def _send_board(self, event: AstrMessageEvent, text: str, image: bool) -> None:
        if image:
            try:
                url = await asyncio.wait_for(self.render(text), timeout=20)
                await event.send(event.image_result(url))
                return
            except Exception as exc:
                logger.warning(f"[horserace] 图片发送失败，使用文字：{exc}")
        # Bound message length on platforms with small text limits.
        for offset in range(0, len(text), 1800):
            await event.send(event.plain_result(text[offset:offset + 1800]))

    async def _run(self, event: AstrMessageEvent, key: tuple[str, str], room: Room, events: list[dict]) -> None:
        race = room.race
        try:
            while self.rooms.get(key) is room and race.start == 1:
                race.round_add()
                race.del_buff_overtime()
                race.fullname()
                text = race.event_start(events)
                race.move()
                race.fullname()
                await self._send_board(event, f"第 {race.round} 回合（终点在左侧）\n{text}\n{race.display()}", race.settings.image_mode)
                winners = race.is_win_all()
                if winners:
                    result = "比赛结束，胜者为：" + winners
                elif race.is_die_all():
                    result = "比赛结束，无马生还（或全员离场）。"
                elif race.round >= race.settings.max_rounds:
                    result = "已到回合上限，本场平局。"
                else:
                    await asyncio.sleep(race.settings.round_interval)
                    continue
                await event.send(event.plain_result(result))
                break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[horserace] 比赛异常，已清理当前房间")
            try:
                await event.send(event.plain_result("比赛异常终止，房间已释放；请管理员查看日志。"))
            except Exception:
                logger.exception("[horserace] 异常通知发送失败")
        finally:
            # Pause preserves room and state. Old tasks never remove replacement rooms.
            if race.start != 2 and self.rooms.get(key) is room:
                self.rooms.pop(key, None)

    async def status(self, event: AstrMessageEvent):
        """查看当前群的赛马状态。"""
        room = self._room(event)
        if not room:
            yield event.plain_result("本群没有赛马活动。")
            return
        race = room.race
        state = {0: "等待报名", 1: "比赛中", 2: "已暂停"}[race.start]
        names = "、".join(p.horse for p in race.player)
        yield event.plain_result(f"{state} | 第 {race.round} 回合 | {len(race.player)} 匹马\n{names}")

    async def reset(self, event: AstrMessageEvent):
        """比赛开始或创建超时后释放房间。"""
        key, room = self._key(event), self._room(event)
        if not room:
            reply = "本群没有需要重置的赛马。"
        elif time.time() - room.race.time < room.race.settings.setting_over_time:
            remaining = max(1, int(room.race.settings.setting_over_time - (time.time() - room.race.time)) + 1)
            reply = f"尚未超时，请在 {remaining} 秒后重置。"
        else:
            self.rooms.pop(key, None)
            await self._cancel(room)
            reply = "赛马场已重置。"
        yield event.plain_result(reply)

    async def pause(self, event: AstrMessageEvent):
        """管理员暂停比赛，保留当前进度。"""
        room = self._room(event)
        if not room or room.race.start != 1:
            yield event.plain_result("没有正在进行的比赛。")
            return
        room.race.start = 2
        await self._cancel(room)
        yield event.plain_result("已暂停。发送 赛马开始 可继续。")

    async def clear(self, event: AstrMessageEvent):
        """管理员立即清空当前群的赛马。"""
        room = self.rooms.pop(self._key(event), None)
        if room:
            await self._cancel(room)
        yield event.plain_result("本群赛马场已清空。")

    async def reload_events(self, event: AstrMessageEvent):
        """管理员重载内置和自定义事件包，不重复追加。"""
        try:
            logs = await self._load()
            text = f"已加载 {len(self.events)} 条事件。进行中的比赛下次开始/继续时使用新事件。\n" + "\n".join(logs)
        except ValueError as exc:
            text = str(exc)
        for offset in range(0, len(text), 1800):
            yield event.plain_result(text[offset:offset + 1800])

    async def terminate(self) -> None:
        rooms = list(self.rooms.values())
        self.rooms.clear()
        await asyncio.gather(*(self._cancel(room) for room in rooms))
