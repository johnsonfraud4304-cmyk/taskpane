"""
TaskPane Daemon - 监控 Reminders 自动处理新任务
================================================
工作流程：
1. 监控"快速提醒"(Quick)列表的新增 reminder
2. 调 LLM 解析（@小王 紧急！明天下班前提交Q3财报）
3. 在 TaskPane 列表创建格式化任务（🔥 [P0] 提交Q3财报给李总）
4. 从"快速提醒"删除原 reminder（避免重复处理）

用法：
  python3 daemon.py start    # 后台启动
  python3 daemon.py stop     # 停止
  python3 daemon.py status   # 查看状态
  python3 daemon.py run      # 前台运行（看日志）
"""
import sys
import os
import time
import json
import signal
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

# 强制本地小模型（速度优化）
os.environ.setdefault("TASKPANE_MODEL", "qwen2:0.5b")
sys.path.insert(0, str(Path(__file__).parent))

QUICK_LIST = "快速提醒"  # macOS Quick Entry 默认列表（中文系统）
TARGET_LIST = "TaskPane"  # 处理后的目标列表
LOG_FILE = Path.home() / "taskpane" / "logs" / "daemon.log"
PID_FILE = Path.home() / "taskpane" / "logs" / "daemon.pid"


def log(msg):
    """写日志"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_store():
    """获取 EventKit store"""
    import EventKit
    store = EventKit.EKEventStore.alloc().init()
    granted = [False]

    def completion(g, e):
        granted[0] = g

    try:
        store.requestFullAccessToRemindersWithCompletion_(completion)
    except AttributeError:
        store.requestAccessToEntityType_completion_(0, completion)

    for _ in range(20):
        time.sleep(0.5)
        if granted[0]:
            break

    if not granted[0]:
        return None
    return store


def find_list(store, list_name):
    """在 store 里找指定名字的列表（兼容 iCloud entityType=1 bug）"""
    import EventKit

    # 方法 1: 直接查
    cals = store.calendarsForEntityType_(0)
    for cal in cals:
        if cal.title() == list_name:
            return cal

    # 方法 2: iCloud Event type (entityType=1)
    cals1 = store.calendarsForEntityType_(1)
    for cal in cals1:
        if cal.title() == list_name and cal.allowedEntityTypes() & 2:
            return cal

    # 方法 3: 通过 default reminder 的 source 找
    default = store.defaultCalendarForNewReminders()
    if default:
        try:
            source_cals = default.source().calendarsForEntityType_(1)
            for cal in source_cals:
                if cal.title() == list_name:
                    return cal
        except:
            pass

    return None


def create_calendar(store, list_name):
    """创建 calendar（用 EKCalendar + iCloud source）"""
    import EventKit

    # 找 iCloud source
    default = store.defaultCalendarForNewReminders()
    if not default:
        return None
    source = default.source()
    if not source:
        return None

    calendar = EventKit.EKCalendar.alloc().init()
    calendar.setTitle_(list_name)
    calendar.setSource_(source)
    calendar.setEventStore_(store)

    ok, error = store.saveCalendar_commit_error_(calendar, True, None)
    if ok:
        return calendar
    log(f"  创建 calendar 失败: {error}")
    return None


def get_incomplete_reminders(store, calendar):
    """获取列表中所有未完成的 reminder"""
    predicate = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
        None, None, [calendar]
    )
    return store.remindersMatchingPredicate_(predicate) or []


def process_reminder(store, target_cal, reminder):
    """处理一条 reminder：解析 → 写新 → 删旧"""
    import EventKit

    title = reminder.title() or ""
    if not title:
        return False

    log(f"处理: {title}")

    # 1. LLM 解析
    from taskpane_app import call_ollama
    parsed, err = call_ollama(title)
    if err:
        log(f"  解析失败: {err}")
        return False
    if not parsed or not parsed.get("is_task"):
        log(f"  不是任务: {parsed.get('reasoning') if parsed else '无'}")
        return False

    # 2. 构建新任务
    PRIORITY_EMOJI = {"P0": "🔥", "P1": "⚠️", "P2": "📌", "P3": "📎"}
    new_title = parsed.get("title", title)[:200]
    priority = parsed.get("priority", "P2")
    emoji = PRIORITY_EMOJI.get(priority, "")
    full_title = f"{emoji} [{priority}] {new_title}"

    log(f"  → {full_title}")

    # 3. 创建新 reminder 到 TaskPane
    new_reminder = EventKit.EKReminder.reminderWithEventStore_(store)
    new_reminder.setTitle_(full_title)
    new_reminder.setCalendar_(target_cal)

    body = []
    if parsed.get("reasoning"):
        body.append(f"💡 判断: {parsed['reasoning']}")
    body.append(f"📨 原文: {title}")
    new_reminder.setNotes_("\n\n".join(body))

    # due date
    if parsed.get("deadline"):
        try:
            dt = datetime.fromisoformat(parsed["deadline"])
            comps = EventKit.NSDateComponents.alloc().init()
            comps.setYear_(dt.year)
            comps.setMonth_(dt.month)
            comps.setDay_(dt.day)
            comps.setHour_(dt.hour if dt.hour is not None else 18)
            comps.setMinute_(dt.minute if dt.minute is not None else 0)
            comps.setSecond_(dt.second if dt.second is not None else 0)
            new_reminder.setDueDateComponents_(comps)
        except:
            pass

    # priority
    if priority == "P0":
        new_reminder.setPriority_(1)
    elif priority == "P1":
        new_reminder.setPriority_(5)

    # 4. 保存
    ok, error = store.saveReminder_commit_error_(new_reminder, True, None)
    if not ok:
        log(f"  保存失败: {error}")
        return False

    # 5. 删除原 reminder
    ok2, error2 = store.removeReminder_commit_error_(reminder, True, None)
    if not ok2:
        log(f"  删除原 reminder 失败: {error2}")

    log(f"  ✅ 完成")
    return True


def run_loop(stop_event):
    """主循环：每 5 秒检查一次"""
    log("=" * 50)
    log("TaskPane Daemon 启动")
    log(f"源列表: {QUICK_LIST}")
    log(f"目标列表: {TARGET_LIST}")
    log("=" * 50)

    store = get_store()
    if not store:
        log("❌ EventKit 授权失败")
        return

    log("✅ EventKit 授权成功")

    # 找两个列表（不存在则持续等待，可能用户在设置 Quick Entry）
    quick_cal = find_list(store, QUICK_LIST)
    if not quick_cal:
        log(f"⚠️  '{QUICK_LIST}' 列表不存在")
        log(f"   按 Cmd+Ctrl+R 触发一次 Quick Entry 让 macOS 创建")
        log(f"   daemon 会持续等待...")
        while not quick_cal and not stop_event.is_set():
            time.sleep(5)  # 每 5 秒检查一次
            store = get_store()  # 重新拿 store
            quick_cal = find_list(store, QUICK_LIST) if store else None
            if quick_cal:
                log(f"✅ 检测到 '{QUICK_LIST}' 列表已创建")
                break
        if not quick_cal:
            return

    target_cal = find_list(store, TARGET_LIST)
    if not target_cal:
        log(f"⚠️  '{TARGET_LIST}' 列表不存在")
        log(f"   在 Reminders App 手动创建一个名为 '{TARGET_LIST}' 的列表")
        log(f"   daemon 会持续等待...")
        while not target_cal and not stop_event.is_set():
            time.sleep(5)
            store = get_store()
            target_cal = find_list(store, TARGET_LIST) if store else None
            if target_cal:
                log(f"✅ 检测到 '{TARGET_LIST}' 列表已创建")
                break
        if not target_cal:
            return

    log(f"✅ 源列表: {quick_cal.title()}")
    log(f"✅ 目标列表: {target_cal.title()}")
    log("")
    log("🔄 开始监控新 reminder...")
    log("   按 Ctrl+C 退出")
    log("")

    # 已处理的 reminder ID 缓存（避免重复处理）
    processed = set()

    while not stop_event.is_set():
        try:
            reminders = get_incomplete_reminders(store, quick_cal)
            for r in reminders:
                rid = r.calendarItemIdentifier()
                if rid in processed:
                    continue
                # 新 reminder
                processed.add(rid)
                process_reminder(store, target_cal, r)
        except Exception as e:
            log(f"循环错误: {e}")

        # 每 3 秒检查一次
        for _ in range(6):
            if stop_event.is_set():
                break
            time.sleep(0.5)

    log("Daemon 停止")


def cmd_start():
    """后台启动"""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            print(f"Daemon 已在运行 (PID {pid})")
            return
        except (ProcessLookupError, ValueError):
            pass

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 用 nohup + subprocess.Popen 后台启动
    proc = subprocess.Popen(
        ["python3", __file__, "run"],
        stdout=open(LOG_FILE, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
        cwd=Path(__file__).parent
    )
    PID_FILE.write_text(str(proc.pid))
    print(f"✅ Daemon 启动 (PID {proc.pid})")
    print(f"   日志: {LOG_FILE}")
    print(f"   停止: python3 {__file__} stop")


def cmd_stop():
    """停止 daemon"""
    if not PID_FILE.exists():
        print("Daemon 未运行")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"✅ Daemon 停止 (PID {pid})")
    except ProcessLookupError:
        print("Daemon 进程不存在")
    finally:
        PID_FILE.unlink(missing_ok=True)


def cmd_status():
    """查看状态"""
    if not PID_FILE.exists():
        print("❌ Daemon 未运行")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        print(f"✅ Daemon 运行中 (PID {pid})")
        print(f"   日志: {LOG_FILE}")
        print(f"   看日志: tail -f {LOG_FILE}")
    except ProcessLookupError:
        print("❌ Daemon 进程不存在")
        PID_FILE.unlink(missing_ok=True)


def cmd_run():
    """前台运行"""
    stop_event = __import__('threading').Event()
    def handle_sigint(*_):
        stop_event.set()
    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        run_loop(stop_event)
    except KeyboardInterrupt:
        pass


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print(f"  python3 {sys.argv[0]} start    # 后台启动")
        print(f"  python3 {sys.argv[0]} stop     # 停止")
        print(f"  python3 {sys.argv[0]} status   # 状态")
        print(f"  python3 {sys.argv[0]} run      # 前台运行（看日志）")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    elif cmd == "run":
        cmd_run()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()