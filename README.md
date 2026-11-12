<div align="center">

<img src="./logo.png" width="128" height="128" alt="赛马插件 Logo" />

# astrbot_plugin_horserace

<a href="https://github.com/Cvandia/astrbot_plugin_horserace">
  <img src="https://count.getloli.com/@astrbot_plugin_horserace?theme=booru-lewd" alt="像素人物访问计数器" />
</a>

_⭐ 基于 AstrBot 的多人随机事件赛马小游戏 ⭐_

[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16%2C%3C5-red)](https://github.com/AstrBotDevs/AstrBot)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/Cvandia/astrbot_plugin_horserace/blob/main/LICENSE)
[![Tests](https://github.com/Cvandia/astrbot_plugin_horserace/actions/workflows/tests.yml/badge.svg)](https://github.com/Cvandia/astrbot_plugin_horserace/actions/workflows/tests.yml)

**中文简体**

</div>

---

## 📝 介绍

让群友为自己的马取名，一起参加赛马比赛！支持多人报名、异步赛况播报、暂停恢复和超时自动开赛。

本插件由 [nonebot_plugin_horserace](https://github.com/shinianj/nonebot_plugin_horserace) 移植而来，使用 AstrBot 的平台无关消息接口和异步比赛任务。`main.py` 仅负责插件入口、生命周期和指令注册，业务逻辑独立拆分。

> [!WARNING]
> **该插件可能存在刷屏，请注意。** 比赛会逐回合播报赛况，建议在合适的群聊中使用，并按需调整回合间隔。

> [!NOTE]
> 适用于 AstrBot **>=4.16,<5** 和 Python **>=3.10**。比赛数据保存在内存中，重载插件或重启后结束；没有积分、下注或金币系统。已通过 81 项 Python 回归测试和 8 项积木编辑器测试，真实 AstrBot 群聊联调尚待完成。

## 📜 免责声明

本项目遵循 MIT License，按许可证“原样”提供。内置事件文字沿用上游，包含网络梗和粗俗内容，请根据群聊需要自行调整。

---

## 💿 安装

<details open>
<summary>AstrBot 管理面板安装（推荐）</summary>

在 AstrBot 的插件管理页面选择通过仓库链接安装，填写：

```text
https://github.com/Cvandia/astrbot_plugin_horserace
```

安装或重载后，发送 `赛马帮助` 查看指令。请按机器人设置添加唤醒前缀。

</details>

<details>
<summary>手动安装</summary>

在 AstrBot 根目录运行：

```bash
git clone https://github.com/Cvandia/astrbot_plugin_horserace.git data/plugins/astrbot_plugin_horserace
```

通过 AstrBot 管理面板重载插件。确保 `main.py`、`metadata.yaml` 直接位于 `data/plugins/astrbot_plugin_horserace/` 下。此插件无额外 Python 依赖。

</details>

## 🖥️ 图形化工作台

在支持插件 Pages 的 AstrBot 管理面板中，打开本插件的 **赛马游戏** 页面，通过类似 Scratch 的积木拖拽、buff 下拉选择和嵌套组合编写事件。支持撤销重做、草稿恢复、校验与导入导出，并通过真实引擎独立试跑和回放。JSON 编辑保留为可选高级入口；保存后自动重载自定义事件，进行中的比赛保留原事件快照。

页面源码位于 `page/dashboard/`，兼容运行入口位于 `pages/dashboard/`。使用方法、目录说明和开发验证见 [工作台文档](docs/dashboard.md)。旧版管理面板没有页面入口时，需升级至支持插件 Pages 的 AstrBot；直接打开 HTML 可离线编辑及导入导出。

## ⚙️ 配置

在 **AstrBot 管理面板 → 插件配置** 中修改。新比赛使用新配置，进行中的比赛保留创建时规则。

| 基础配置 | 类型 | 默认值 | 说明 |
| :--- | :---: | :---: | :--- |
| `setting_track_length` | int | 20 | 跑道长度，5~100 |
| `setting_random_min_length` | int | 0 | 随机传送最小位置 |
| `setting_random_max_length` | int | 15 | 随机传送最大位置，不得超出跑道 |
| `base_move_min` | int | 1 | 每回合基础移动最小值 |
| `base_move_max` | int | 3 | 每回合基础移动最大值；移动范围 1~20 |
| `min_player` | int | 2 | 手动及超时自动开赛的最少人数 |
| `max_player` | int | 8 | 最多玩家数；人数范围 2~16 |
| `setting_over_time` | int | 120 | 创建或最近一次开赛后，允许重置的等待秒数，10~3600 |
| `event_rate` | int | 450 | 随机事件概率，千分比；0 关闭普通随机事件 |
| `round_interval` | float | 6.0 | 回合播报后的等待秒数，1~60 |
| `max_rounds` | int | 100 | 回合上限，1~500；仍无胜者则平局 |
| `image_mode` | bool | false | 图片播报，依赖 AstrBot 文字转图片服务；失败回退文字 |

最小值须不大于对应最大值；`min_player <= max_player`。默认文字播报无需图片渲染服务。

## 🚀 使用

> [!NOTE]
> 指令是否需要前缀或 @ 机器人，取决于 AstrBot 唤醒配置。例如前缀为 `/`，发送 `/赛马创建`。马名与指令之间需要空格。

### 指令

| 指令 | 需要 @ | 范围 | 说明 | 权限 |
| :--- | :---: | :---: | :--- | :--- |
| `赛马帮助` | 根据配置 | 全部 | 查看帮助 | 所有人 |
| `赛马创建` | 根据配置 | 群聊 | 创建比赛 | 群成员 |
| `赛马加入 马名` | 根据配置 | 群聊 | 报名一次，马名最长 24 字符 | 群成员 |
| `赛马开始` | 根据配置 | 群聊 | 开始或继续比赛 | 创建者 / AstrBot 管理员 |
| `赛马状态` | 根据配置 | 群聊 | 查看当前状态 | 群成员 |
| `赛马重置` | 根据配置 | 群聊 | 超时后重置，可终止运行中的比赛 | 群成员 |
| `赛马暂停` | 根据配置 | 群聊 | 暂停并保留进度 | AstrBot 管理员 |
| `赛马清空` | 根据配置 | 群聊 | 立即取消本群比赛 | AstrBot 管理员 |
| `赛马事件重载` | 根据配置 | 全部 | 重载内置和自定义事件 | AstrBot 管理员 |

甲发送 `赛马创建` → 甲发送 `赛马加入 闪电` → 乙发送 `赛马加入 赤兔` → 甲发送 `赛马开始`。

同一平台实例下的同一群共享比赛，跨群、跨平台实例互相隔离。同回合到达终点者并列获胜。管理员指 AstrBot 管理员，群主/群管理身份不会自动获得插件管理权限。

**报名超时自动处理：** 创建后开始计时，每次成功加入重新计时。尚未开赛且连续 **60 秒** 无人成功加入时，达到 `min_player` 门槛（默认 **2 人**）就自动开始比赛；人数不足才清空场地，并通知群聊。无效或重复报名、查询状态不刷新计时；已开赛和暂停中的比赛不受此规则影响。创建者没有报名也可以自动开赛，只要实际报名人数达标。

## 🌙 Todo

- [x] AstrBot 原生指令、配置和管理员权限
- [x] 多群独立比赛、异步播报、暂停与恢复
- [x] 报名阶段 60 秒无人加入，人数达标自动开赛、不足则清场
- [x] 65 项本地测试及自动化测试工作流
- [ ] 真实 AstrBot 群聊联调与各平台兼容性验收

**喜欢记得点个 star ⭐**

## 💝 特别鸣谢

- [AstrBot](https://github.com/AstrBotDevs/AstrBot)：插件运行框架。
- [shinianj/nonebot_plugin_horserace](https://github.com/shinianj/nonebot_plugin_horserace)：本次移植上游，基线提交 `80b5bce36583d54814db6c917b3b062aa8b03c2f`。
- [冥乐 / Evan8440](https://github.com/Evan8440/zhenxun_bot_HorseRace)：原赛马项目作者。
- [Cvandia/uv-project-template](https://github.com/Cvandia/uv-project-template)：README 结构与展示样式参考。
- 上游事件包贡献者与原项目贡献者；保留原 MIT 版权声明。

## Contributer

<a href="https://github.com/Cvandia/astrbot_plugin_horserace/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Cvandia/astrbot_plugin_horserace&max=1000" alt="contributors" />
</a>

## 📚 更多帮助

更新记录：[CHANGELOG.md](CHANGELOG.md)。

1. 开发结构、规则边界和测试说明：[开发说明](docs/开发说明.md)。
2. 反馈问题：[提交 Issue](https://github.com/Cvandia/astrbot_plugin_horserace/issues)。请提供 AstrBot 版本、平台、指令步骤和脱敏日志。
3. 本地验证：`python -m unittest discover -s tests -v`。包含 200 个随机种子的整场模拟；传输层使用 API 替身，不能替代真实机器人联调。
