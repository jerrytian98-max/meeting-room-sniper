# Meeting Room Sniper（会议室空位监控技能）

这是一个面向 OpenClaw 的会议室空位轮询与自动预订技能。当指定楼宇、日期和时段暂时没有可用会议室时，脚本会定期检查空位，并在发现可用房间后尝试立即提交预订。

> 该项目针对特定企业内部日历系统开发，不是开箱即用的通用订会议室程序。它依赖企业账号、有效的 SSO Cookie、内部接口权限以及另一个 `room-booking-helper` 技能。仓库不包含任何登录凭据。

## 来源说明

原始 `SKILL.md` 中记录的信息如下：

- 技能名称：`meeting-room-sniper`
- 创建者/更新者：`zhouchi06`
- 来源：`FRIDAY Skillhub`
- Skill ID：`2934`
- 原始版本：`V5`

本仓库保留上述元数据用于来源追踪，不宣称对原始代码拥有额外权利。

## 工作方式

1. 从 `room-booking-helper/cookie.json` 读取已登录会话。
2. 根据配置查询目标楼宇内符合容量要求的会议室。
3. 获取当天预订记录，排除目标时段有冲突或被标记为下线的房间。
4. 按固定间隔持续轮询。
5. 发现空位后提交预订；成功则写入结果并退出。
6. 到达截止时间、连续失败或认证失效时停止。

脚本将持续轮询并可能产生真实预订。请先核对日期、时间、楼宇、参会人和截止时间，再启动任务。

## 文件结构

```text
├─ SKILL.md                              # OpenClaw 技能定义及工作流程
├─ sniper.py                             # 轮询与自动预订脚本
├─ sniper-config.example.json            # 脱敏配置示例
├─ requirements.txt                      # Python 依赖
├─ references/cron-setup.md              # Cron/Heartbeat 监控参考
└─ scripts/monitor-config-template.json  # 监控状态配置模板
```

本地的 `sniper-config.json`、`sniper-result.json`、`sniper-log.txt`、Cookie 和 Python 缓存均已排除，不会上传到 Git。

## 前置条件

- Python 3.9 或更高版本
- OpenClaw 运行环境
- 已安装并可用的 `room-booking-helper` 技能
- 有权访问目标企业日历系统的账号
- 通过企业 SSO 获取的有效 Cookie
- 对目标楼宇和会议室具有合法预订权限

当前脚本默认使用以下部署路径：

```text
/root/.openclaw/workspace/skills/meeting-room-sniper/
/app/skills/room-booking-helper/cookie.json
```

如果部署目录不同，需要相应调整 `sniper.py` 顶部的 `LOG_PATH`、`CONFIG_PATH` 和 `COOKIE_PATH`。原始 `SKILL.md` 中的命令行参数示例与当前脚本实现并不完全一致：当前 `sniper.py` 实际从 JSON 配置文件读取参数。

## 安装

将仓库克隆到 OpenClaw 技能目录：

```bash
git clone https://github.com/jerrytian98-max/meeting-room-sniper.git \
  ~/.openclaw/workspace/skills/meeting-room-sniper
cd ~/.openclaw/workspace/skills/meeting-room-sniper
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 配置

复制脱敏模板：

```bash
cp sniper-config.example.json sniper-config.json
```

主要字段：

| 字段 | 说明 |
| --- | --- |
| `buildingId` | 内部系统中的楼宇 ID |
| `buildingName` | 日志中显示的楼宇名称 |
| `date` | 目标日期，格式为 `YYYY-MM-DD` |
| `startTime` / `endTime` | 目标时段，格式为 `HH:MM` |
| `capacityMin` / `capacityMax` | 会议室容量范围 |
| `mis` | 用于查询组织者 ID 的企业账号 |
| `title` | 创建会议时使用的主题 |
| `deadline` | 停止监控的 ISO 8601 时间，必须包含时区 |
| `extraAttendees` | 额外参会人的内部 ID 列表 |

不要把真实账号、Cookie、参会人、会议主题或实际日程提交到仓库。

## 运行

完成配置并确认 SSO Cookie 有效后：

```bash
python sniper.py
```

脚本默认每 10 秒检查一次。成功、超时或连续 5 次异常后会退出，并在本地写入日志/结果文件。

## 安全与合规

- 仅可在获得授权的企业账号和会议室资源上使用。
- 自动预订会产生真实业务操作；不要在生产环境中用示例配置直接运行。
- Cookie 等同于登录凭据，不应写入代码、日志、Issue、提交记录或聊天内容。若曾泄露，应立即注销会话并重新认证。
- 不要缩短轮询间隔；当前 10 秒是降低接口压力的最低约束，不代表企业系统允许任意自动化访问。
- 使用前应确认企业安全政策、内部系统使用规则和自动化预订规定。
- 内部接口结构变化、Cookie 过期、网络错误和权限变化都可能导致任务失败。
- 当前代码没有完整的重试退避、结构化审计、并发锁或预订幂等保护，部署多个实例可能造成重复操作。

## 已知限制

- 与特定企业域名和 API 数据结构耦合，无法直接用于其他会议系统。
- 依赖另一个未包含在本仓库中的技能和 SSO 登录流程。
- 部署路径目前写死在脚本中。
- `SKILL.md` 提到的“大象通知”在当前 `sniper.py` 中没有独立实现。
- 非成功 HTTP 响应和部分 JSON 结构异常的错误信息有限。
- “时长超过 20 小时即下线”的判断属于业务启发式规则，可能存在误判。

## 许可

仓库当前未附带开源许可证。在原始权利人明确授权前，默认保留全部权利；公开可见不代表允许复制、修改或再分发。
