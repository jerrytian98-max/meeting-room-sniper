---
name: meeting-room-sniper
description: "会议室抢占监控工具。当目标时段的会议室全部被占满时，自动持续监控并在有人取消预定释放空位时第一时间抢占预定。适用场景：(1) 用户想预定会议室但目标时段已满，需要蹲守空位 (2) 用户说'帮我抢会议室'、'监控会议室'、'蹲一个会议室'、'有空位就帮我订' (3) 用户需要在热门时段抢占稀缺会议室资源。依赖 room-booking-helper skill 完成实际的 API 调用和预定提交。"

metadata:
  skillhub.creator: "zhouchi06"
  skillhub.updater: "zhouchi06"
  skillhub.version: "V5"
  skillhub.source: "FRIDAY Skillhub"
  skillhub.skill_id: "2934"
---

# 会议室抢占监控

当目标时段会议室已满时，**双管齐下**：同时创建系统监测任务 + 启动本地 sniper 脚本持续轮询，谁先抢到算谁的。

## 前置依赖

- **room-booking-helper** skill：负责 SSO 认证、API 调用、会议室查询与预定提交
- `/app/skills/room-booking-helper/cookie.json`：有效的登录 Cookie（通过 `sso-login.sh` 获取）

## 工作流程

### 1. 收集抢占参数

向用户确认以下信息（逐步询问，每次只问一个）：

| 参数 | 必填 | 说明 |
|------|------|------|
| 城市 | ✅ | 如：目标城市 |
| 园区/大楼 | ✅ | 如：目标办公楼 |
| 楼层 | ❌ | 不指定则不限楼层 |
| 日期 | ✅ | 具体日期，如 2099-01-01 |
| 时段 | ✅ | 开始-结束时间，如 12:00-13:00 |
| 人数 | ❌ | 默认 5 人 |
| 会议主题 | ❌ | 默认"会议" |
| 监控间隔 | ❌ | 默认 10 秒 |
| 截止时间 | ❌ | 默认为目标时段开始前 30 分钟，超时自动停止 |

### 2. 首次检查（直接 API）

通过 room-booking-helper skill 的 API 流程执行一次完整查询与预定尝试：

1. 确认 cookie.json 有效（过期则先执行 `sso-login.sh`）
2. 调用 `cityBuilding` 接口定位建筑 ID
3. 调用 `find-rooms` 接口查询目标时段会议室列表
4. 调用 `findRoomAppointmentsV2` 接口查预订情况，筛选空闲房间（同时过滤下线会议室：预订时长 > 20h）
5. 找到空闲房间 → 直接调用 `POST /api/v2/xm/schedules` 提交预定

**如果预定成功** → 通知用户，流程结束
**如果全满** → 进入 sniper 模式

### 3. Sniper 模式（全满时）

> ⚠️ **不再创建系统监测任务**
>
> 系统监测任务（`insertV2`）创建后无法通过 API 取消（取消接口需要 `appointmentRoomTaskId`，但 insertV2 不返回此 ID，查询自己监测列表的接口也未找到）。
> 为避免 sniper 预订成功后系统监测任务持续孤立运行，**sniper 模式下只启动本地轮询，不创建系统监测**。
>
> 调用 `quick_book.py` 时传入 `--skip-monitor` 参数，或调用 `quick_book()` 时传 `skip_monitor=True`。

#### 本地 sniper 脚本（10秒轮询）

启动 `sniper.py` 脚本，每 10 秒调一次 API 检查空位，发现空位立即抢占：

```bash
python3 ~/.openclaw/workspace/skills/meeting-room-sniper/sniper.py \
  --building-id <id> \
  --floor-ids <ids> \
  --date <YYYY-MM-DD> \
  --start <HH:MM> \
  --end <HH:MM> \
  --capacity <n> \
  --mis <mis> \
  --interval 10 \
  --deadline <ISO时间>
```

sniper.py 核心逻辑：
1. 读取 `/app/skills/room-booking-helper/cookie.json` 获取认证
2. 调用 `find-rooms` + `findRoomAppointmentsV2` 查空位
3. 发现空位立即调用 `/api/v2/xm/schedules` 提交预定
4. 成功 → 写入结果文件 + 大象通知用户 + 退出（无需取消系统监测，因为根本没创建）
5. 失败/超时 → 记录日志 + 继续轮询

### 4. 停止条件

满足任一条件即停止监控：

- ✅ 成功预定到会议室（任意路径）
- ⏰ 超过截止时间
- 🚫 用户手动取消
- ❌ Cookie 过期且无法自动续期

## 通知策略

| 事件 | 通知方式 |
|------|----------|
| 开始监控 | 告知用户已进入双管齐下模式，说明间隔和截止时间 |
| 抢占成功 | 立即大象通知，包含会议室名称、楼层、时间 |
| 监控超时 | 通知用户未能抢到，建议调整条件或时间段 |
| Cookie 过期 | 通知用户需重新认证，引导执行 sso-login.sh |
| 每次检查 | 不通知（避免打扰），仅记录日志 |

## 日志记录

将监控日志写入 `scripts/sniper-log.txt`，格式：

```
[11:05:02] 检查中... 全满（41间，0空闲）
[11:05:12] 检查中... 全满（41间，0空闲）
[11:05:22] 发现空位！双流厅 3层 cap:5 → 立即提交预定
[11:05:23] ✅ 预定成功！schedule_id: 2031207149161762906
```

## 关键 API 速查

| 接口 | 用途 |
|------|------|
| `POST /room/front/app/room/cityBuilding` | 获取建筑列表 |
| `POST /meeting/api/pc/room/appointment/v2/find-rooms` | 查询会议室列表 |
| `POST /meeting/api/pc/room/appointment/findRoomAppointmentsV2` | 查询预订情况 |
| `POST /api/v2/xm/schedules` | 提交预定 |
| `POST /room/front/appointment-room/insertV2` | 创建系统监测任务 |
| `POST /api/v2/xm/meeting/dataset/account` | 查询 empId |

## 注意事项

- 本地轮询间隔不小于 10 秒，避免对服务器造成压力
- 下线会议室识别：预订记录中存在时长 > 20 小时的记录，直接跳过
- Cookie 过期立刻通知用户，不要静默失败
- 预定规则：8天窗口、每日同一会议室3次上限、单次4小时上限
