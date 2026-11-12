"""Authenticated plugin extension routes; files stay in plugin data/events."""
import asyncio
import json
from pathlib import Path
import re
import os
import tempfile
import uuid

from astrbot.api import logger

from .dashboard_core import MAX_BODY, simulate, validate_pack
from .event_ai import EventAI


class DashboardAPI:
    def __init__(self, context, service):
        self.service = service
        self.ai = EventAI(context, service.config)
        self.lock = asyncio.Lock()
        self.closed = False
        for endpoint, method in (("packs", "GET"), ("capabilities", "GET"), ("validate", "POST"), ("simulate", "POST"), ("save", "POST"), ("delete", "POST"), ("ai_chat", "POST")):
            context.register_web_api(
                f"/astrbot_plugin_horserace/dashboard/{endpoint}",
                getattr(self, endpoint), [method], f"赛马事件开发：{endpoint}",
            )

    async def handle(self, action, body=None):
        if self.closed:
            raise ValueError("插件已卸载，请刷新页面")
        if action == "packs":
            return await asyncio.to_thread(self._packs)
        if action == "capabilities":
            return {**self.ai.capabilities(), "can_delete_custom": True}
        if not isinstance(body, dict):
            raise ValueError("请求内容必须是 JSON 对象")
        if action == "validate":
            return {"count": len(validate_pack(body.get("pack"))), "message": "校验通过"}
        if action == "simulate":
            return await asyncio.to_thread(simulate, body)
        if action == "ai_chat":
            result = await self.ai.chat(body)
            if self.closed:
                raise ValueError("插件已卸载，请刷新页面")
            return result
        if action == "delete":
            async with self.lock:
                if body.get("confirm") is not True:
                    raise ValueError("请先确认删除自定义事件包")
                pack_id = body.get("id", "")
                if not isinstance(pack_id, str) or not pack_id.startswith("custom/"):
                    raise ValueError("仅可删除自定义事件包，内置事件包不能删除")
                name = pack_id.removeprefix("custom/")
                if not name or any(char in name for char in "/\\:\x00") or not name.lower().endswith(".json"):
                    raise ValueError("无效事件包路径")
                root = self.service.custom_dir.parent.resolve()
                target = self.service.custom_dir / name
                if (self.service.custom_dir.is_symlink() or not self.service.custom_dir.resolve().is_relative_to(root)
                        or target.is_symlink() or target.resolve().parent != self.service.custom_dir.resolve()
                        or target.resolve().is_relative_to(self.service.builtin_dir.resolve())):
                    raise ValueError("无效事件包路径")
                if not target.is_file():
                    raise ValueError("事件包不存在或已经删除，请刷新列表")
                backup_dir = self.service.custom_dir.parent / "deleted_events"
                if backup_dir.is_symlink() or backup_dir.resolve().parent != root:
                    raise ValueError("无效备份目录")
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup = backup_dir / f"{name[:-5][:48]}-{uuid.uuid4().hex}.json"
                previous, loaded = self.service.events, self.service.loaded
                # Atomic metadata-only rename: no cancellation gap before rollback
                # becomes active, unlike an unfinished worker-thread rename.
                os.replace(target, backup)
                try:
                    await self.service._load()
                except BaseException:
                    os.replace(backup, target)
                    self.service.events, self.service.loaded = previous, loaded
                    raise
                return {"id": pack_id, "filename": name, "backup_filename": backup.name, "message": "已删除并重载，自定义包备份已保留"}
        if action == "save":
            async with self.lock:
                filename = body.get("filename", "")
                if not isinstance(filename, str) or not re.fullmatch(r"[\w\-\u4e00-\u9fff]{1,64}\.json", filename):
                    raise ValueError("文件名只允许中英文、数字、下划线和短横线，以 .json 结尾")
                pack = validate_pack(body.get("pack"))
                target = self.service.custom_dir / filename
                if target.is_symlink() or target.resolve().parent != self.service.custom_dir.resolve():
                    raise ValueError("无效文件路径")
                exists = target.exists()
                if exists and body.get("overwrite") is not True:
                    return {"conflict": True, "filename": filename, "message": "文件已存在，需要确认覆盖"}
                previous = target.read_bytes() if exists else None
                try:
                    await asyncio.to_thread(self._atomic_write, target, json.dumps(pack, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
                    logs = await self.service._load()
                except Exception:
                    if previous is not None:
                        await asyncio.to_thread(self._atomic_write, target, previous)
                    elif target.exists():
                        target.unlink()
                    raise
                return {"filename": filename, "count": len(pack), "message": "已保存并重载", "logs": logs}
        raise ValueError("未知接口")

    @staticmethod
    def _atomic_write(target: Path, content: bytes):
        fd, temp = tempfile.mkstemp(prefix=".horserace-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(content)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def _packs(self):
        packs, errors = [], []
        for source, folder in (("builtin", self.service.builtin_dir), ("custom", self.service.custom_dir)):
            for path in sorted(folder.glob("*.json")):
                try:
                    if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
                        raise ValueError("文件过大或为符号链接")
                    content = json.loads(path.read_text(encoding="utf-8-sig"))
                    packs.append({"id": f"{source}/{path.name}", "source": source, "filename": path.name, "pack": content})
                except (ValueError, OSError) as exc:
                    errors.append(f"{path.name}: {exc}")
                    if source == "custom" and not path.is_symlink() and path.is_file():
                        packs.append({"id": f"custom/{path.name}", "source": source, "filename": path.name, "pack": None, "error": str(exc)})
        return {"packs": packs, "errors": errors}

    async def _route(self, action):
        # New AstrBot uses api.web; Quart remains supported on older runtimes.
        try:
            from astrbot.api.web import request, json_response
            async def read():
                return await request.body()
            def response(data, status):
                return json_response(data, status_code=status)
        except ImportError:
            from quart import request, jsonify
            async def read():
                return await request.get_data()
            def response(data, status):
                return jsonify(data), status
        try:
            raw = b"" if action in ("packs", "capabilities") else await read()
            if len(raw) > MAX_BODY + (65536 if action == "ai_chat" else 16384):
                raise ValueError("请求体过大")
            body = json.loads(raw) if raw else None
            result = await self.handle(action, body)
            return response({"status": "ok", "data": result}, 200)
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            return response({"status": "error", "message": str(exc)}, 400)
        except Exception:
            logger.exception("[horserace] 页面接口失败")
            return response({"status": "error", "message": "操作失败，请查看 AstrBot 日志"}, 500)

    async def packs(self):
        return await self._route("packs")

    async def validate(self):
        return await self._route("validate")

    async def simulate(self):
        return await self._route("simulate")

    async def save(self):
        return await self._route("save")

    async def delete(self):
        return await self._route("delete")

    async def capabilities(self):
        return await self._route("capabilities")

    async def ai_chat(self):
        return await self._route("ai_chat")
