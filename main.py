"""Plugin entry point: lifecycle wiring and command registration only."""
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools

from .service import RaceService
from .dashboard_api import DashboardAPI


class HorseRacePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.service = RaceService(
            config, StarTools.get_data_dir("astrbot_plugin_horserace"), self.text_to_image
        )
        self.dashboard = DashboardAPI(context, self.service)

    async def initialize(self) -> None:
        await self.service.initialize()

    async def terminate(self) -> None:
        self.dashboard.closed = True
        await self.service.terminate()

    @filter.command("赛马帮助")
    async def help(self, event: AstrMessageEvent):
        """赛马帮助。"""
        async for result in self.service.help(event):
            yield result

    @filter.command("赛马创建")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def create(self, event: AstrMessageEvent):
        """赛马创建。"""
        async for result in self.service.create(event):
            yield result

    @filter.command("赛马加入")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def join(self, event: AstrMessageEvent):
        """赛马加入。"""
        async for result in self.service.join(event):
            yield result

    @filter.command("赛马开始")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def start(self, event: AstrMessageEvent):
        """赛马开始。"""
        async for result in self.service.start(event):
            yield result

    @filter.command("赛马状态")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def status(self, event: AstrMessageEvent):
        """赛马状态。"""
        async for result in self.service.status(event):
            yield result

    @filter.command("赛马重置")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def reset(self, event: AstrMessageEvent):
        """赛马重置。"""
        async for result in self.service.reset(event):
            yield result

    @filter.command("赛马暂停")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def pause(self, event: AstrMessageEvent):
        """赛马暂停。"""
        async for result in self.service.pause(event):
            yield result

    @filter.command("赛马清空")
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def clear(self, event: AstrMessageEvent):
        """赛马清空。"""
        async for result in self.service.clear(event):
            yield result

    @filter.command("赛马事件重载")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def reload_events(self, event: AstrMessageEvent):
        """赛马事件重载。"""
        async for result in self.service.reload_events(event):
            yield result
