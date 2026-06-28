# Cron 监控任务设置指南

## 通过 OpenClaw Cron 实现定时监控

### 创建 cron 任务

使用 OpenClaw 的 scheduled message / cron 能力创建定时触发：

```
检查会议室可用性：
- 地点：{building} {floor}层
- 日期：{date}
- 时段：{timeStart}-{timeEnd}
- 人数：{capacity}

执行步骤：
1. 打开 https://calendar.sankuai.com/rooms?date={date}
2. 筛选地点到 {city}/{building}，楼层 {floor}
3. 遍历所有会议室，检查 {timeStart}-{timeEnd} 是否有空位
4. 有空位 → 立即预定（主题：{subject}）→ 通知用户 → 删除此 cron
5. 全满 → 等待下次触发
6. 当前时间超过 {deadline} → 通知用户超时 → 删除此 cron
```

### 通过 Heartbeat 实现

在 HEARTBEAT.md 中添加监控检查项：

```markdown
## 会议室监控
- 检查 scripts/monitor-config.json 是否存在
- 如果存在且 status 为 "watching"，执行会议室检查流程
- 检查完成后更新 monitor-log.md
```

### 监控状态管理

monitor-config.json 中的 status 字段：

| 状态 | 含义 |
|------|------|
| watching | 监控中，继续检查 |
| booked | 已成功预定，停止 |
| timeout | 已超时，停止 |
| cancelled | 用户取消，停止 |
| error | 连续失败，需人工介入 |

### 停止监控

将 monitor-config.json 的 status 改为对应终态，或直接删除文件。
