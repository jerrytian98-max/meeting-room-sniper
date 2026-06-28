#!/usr/bin/env python3
"""
会议室抢占脚本 - 持续轮询目标办公楼，发现空位立即预订
"""
import json, requests, time, sys
from datetime import datetime, timezone, timedelta

# ===== 配置 =====
COOKIE_PATH = "/app/skills/room-booking-helper/cookie.json"
LOG_PATH = "/root/.openclaw/workspace/skills/meeting-room-sniper/sniper-log.txt"
CONFIG_PATH = "/root/.openclaw/workspace/skills/meeting-room-sniper/sniper-config.json"

INTERVAL_SEC = 10      # 轮询间隔（秒）
TZ = timezone(timedelta(hours=8))

def log(msg):
    ts = datetime.now(TZ).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_cookie():
    with open(COOKIE_PATH) as f:
        return json.load(f)["cookie"]

def make_headers(cookie):
    return {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "M-UserContext": "eyJsb2NhbGUiOiJ6aCIsInRpbWVab25lIjoiQXNpYS9TaGFuZ2hhaSJ9",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Cookie": cookie,
    }

def get_organizer_id(headers, mis):
    """获取用户 empId"""
    url = "https://calendar.sankuai.com/api/v2/xm/meeting/dataset/account"
    r = requests.post(url, headers=headers, json={"filter": mis}, timeout=10)
    data = r.json()
    if data.get("code") == 200 and data.get("data"):
        return str(data["data"][0]["empId"])
    return None

def find_free_rooms(headers, building_id, date_ms, start_time, end_time, capacity_min, capacity_max):
    """查询空闲会议室"""
    # 1. 查候选列表
    url1 = "https://calendar.sankuai.com/meeting/api/pc/room/appointment/v2/find-rooms"
    payload1 = {
        "date": date_ms,
        "buildingId": str(building_id),
        "floorIds": [],
        "capacity": [{"capacityMin": capacity_min, "capacityMax": capacity_max}],
        "startTime": "08:00",
        "endTime": "20:00"
    }
    r1 = requests.post(url1, headers=headers, json=payload1, timeout=10)
    rooms = r1.json().get("data", [])
    if not rooms:
        return []

    room_ids = [rm["id"] for rm in rooms]

    # 2. 查预订情况
    url2 = "https://calendar.sankuai.com/meeting/api/pc/room/appointment/findRoomAppointmentsV2"
    r2 = requests.post(url2, headers=headers, json={"date": date_ms, "roomIds": room_ids}, timeout=10)
    appt_data = r2.json().get("data", [])
    appt_map = {a["roomId"]: a.get("appointmentVOS", []) or [] for a in appt_data}

    # 3. 筛选空闲
    OFFLINE_THRESHOLD = 20 * 3600 * 1000
    free = []
    for rm in rooms:
        rid = rm["id"]
        apts = appt_map.get(rid, [])
        # 下线检测
        if any((a["endTime"] - a["startTime"]) > OFFLINE_THRESHOLD for a in apts):
            continue
        # 时段冲突检测
        target_s = date_ms + int(start_time.split(":")[0]) * 3600000 + int(start_time.split(":")[1]) * 60000
        target_e = date_ms + int(end_time.split(":")[0]) * 3600000 + int(end_time.split(":")[1]) * 60000
        conflict = any(a["startTime"] < target_e and a["endTime"] > target_s for a in apts)
        if not conflict:
            free.append(rm)
    return free

def book_room(headers, room, date_ms, start_time, end_time, organizer_id, title, attendees=None):
    """提交预订"""
    url = "https://calendar.sankuai.com/api/v2/xm/schedules"
    ts_start = date_ms + int(start_time.split(":")[0]) * 3600000 + int(start_time.split(":")[1]) * 60000
    ts_end   = date_ms + int(end_time.split(":")[0])   * 3600000 + int(end_time.split(":")[1])   * 60000
    payload = {
        "title": title,
        "startTime": ts_start,
        "endTime": ts_end,
        "isAllDay": 0,
        "location": "",
        "attendees": attendees if attendees else [organizer_id],
        "noticeType": 0,
        "noticeRule": "P0Y0M0DT0H10M0S",
        "recurrencePattern": {"type": "NONE", "showType": "NONE"},
        "deadline": 0,
        "memo": "",
        "organizer": organizer_id,
        "room": {
            "id": room["id"],
            "name": room["name"],
            "email": room.get("email", ""),
            "capacity": room.get("capacity", 5),
            "floorId": room.get("floorId", 0),
            "floorName": room.get("floorName", ""),
            "buildingId": room.get("buildingId", 0),
            "buildingName": room.get("buildingName", ""),
        },
        "appKey": "meeting",
        "bookType": 11
    }
    r = requests.post(url, headers=headers, json=payload, timeout=10)
    return r.json()

def main():
    cfg = json.load(open(CONFIG_PATH))
    building_id = cfg["buildingId"]
    date_str    = cfg["date"]          # "2099-01-01"
    start_time  = cfg["startTime"]     # "14:00"
    end_time    = cfg["endTime"]       # "15:00"
    capacity_min = cfg.get("capacityMin", 1)
    capacity_max = cfg.get("capacityMax", 6)
    mis          = cfg["mis"]
    title        = cfg.get("title", "会议")
    deadline_str = cfg["deadline"]     # ISO8601

    # 计算日期时间戳（当天零点 UTC+8）
    dt_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TZ)
    date_ms = int(dt_date.timestamp() * 1000)

    deadline = datetime.fromisoformat(deadline_str)

    log(f"🎯 开始监控 {cfg.get('buildingName', '目标办公楼')} {date_str} {start_time}-{end_time}")
    log(f"   轮询间隔 {INTERVAL_SEC}s，截止 {deadline_str}")

    cookie = load_cookie()
    headers_dict = make_headers(cookie)

    organizer_id = get_organizer_id(headers_dict, mis)
    if not organizer_id:
        log("❌ 获取用户 empId 失败，退出")
        sys.exit(1)
    log("   已获取组织者身份")
    extra_attendees = cfg.get("extraAttendees", [])
    all_attendees = [organizer_id] + [str(x) for x in extra_attendees]

    check_count = 0
    fail_count = 0

    while datetime.now(TZ) < deadline:
        check_count += 1
        try:
            free = find_free_rooms(headers_dict, building_id, date_ms, start_time, end_time, capacity_min, capacity_max)
            log(f"  第{check_count}次检查：空闲 {len(free)} 间")

            if free:
                for rm in free:
                    log(f"  🚀 发现空位：{rm['name']}（{rm.get('floorName','')}），立即预订！")
                    result = book_room(headers_dict, rm, date_ms, start_time, end_time, organizer_id, title, all_attendees)
                    if result.get("message") == "成功" or result.get("data", {}).get("redirectUrl"):
                        log(f"  ✅ 预订成功！{rm['name']} {rm.get('floorName','')} {start_time}-{end_time}")
                        # 系统监测任务由 quick_book.py 的 skip_monitor=True 控制不创建，
                        # sniper 模式下无需取消（根本没有孤立监测任务）
                        # 写入结果文件
                        with open(CONFIG_PATH.replace("config", "result"), "w") as f:
                            json.dump({"status": "success", "room": rm, "time": start_time + "-" + end_time}, f, ensure_ascii=False, indent=2)
                        sys.exit(0)
                    elif "已下线" in str(result):
                        log(f"  ⚠️ {rm['name']} 已下线，尝试下一个")
                        continue
                    else:
                        log(f"  ❌ 预订失败：{result}")
                fail_count = 0
            else:
                fail_count = 0

        except Exception as e:
            fail_count += 1
            log(f"  ⚠️ 异常（{fail_count}/5）：{e}")
            if fail_count >= 5:
                log("  ❌ 连续5次失败，退出")
                sys.exit(2)

        time.sleep(INTERVAL_SEC)

    log("⏰ 已到截止时间，未能抢到会议室，监控结束")
    with open(CONFIG_PATH.replace("config", "result"), "w") as f:
        json.dump({"status": "timeout"}, f)
    sys.exit(3)

if __name__ == "__main__":
    main()
