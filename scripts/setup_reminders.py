#!/usr/bin/env python3
"""
TaskPane Reminders 集成 - 使用 pyobjc EventKit（绕过 osascript TCC bug）
用法:
  pip3 install pyobjc-framework-EventKit
  python3 setup_reminders.py init    # 创建列表
  python3 setup_reminders.py add "明天提交Q3财报"  # 添加任务
  python3 setup_reminders.py list   # 列出所有提醒
"""
import EventKit
import sys
from pathlib import Path
import subprocess
from datetime import datetime, timedelta

LIST_NAME = "TaskPane"
PRIORITY_EMOJI = {"P0": "🔥", "P1": "⚠️", "P2": "📌", "P3": "📎"}


def get_store():
    """获取 EKEventStore（首次会弹授权框）"""
    store = EventKit.EKEventStore.alloc().init()
    # macOS 14 新 API：直接请求 Reminders 完整访问
    # 用 ObjC 风格的 completion block（pyobjc 异步）
    granted = [False]

    def completion(granted_flag, error):
        granted[0] = granted_flag
        if error:
            print(f"⚠️  授权错误: {error}")

    store.requestFullAccessToRemindersWithCompletion_(completion)

    # 等待一下让授权框弹出（如果有）
    import time
    time.sleep(2)

    if not granted[0]:
        # 退回到 ObjC API
        print("尝试备用 API...")
        store.requestAccessToEntityType_completion_(0, completion)
        time.sleep(2)

    return store


def get_or_create_taskpane(store):
    """获取或创建 TaskPane 列表"""
    calendars = store.calendarsForEntityType_(0)
    for cal in calendars:
        if cal.title() == LIST_NAME:
            return cal

    # 创建新列表
    calendar = EventKit.EKCalendar.alloc().init()
    calendar.setTitle_(LIST_NAME)
    calendar.setEventStore_(store)  # 关联到 store

    # 必须设 source（否则保存报错）
    sources = store.sources()
    if sources and len(sources) > 0:
        # 优先用 iCloud，否则用第一个本地 source
        source = None
        for s in sources:
            if 'icloud' in s.title().lower() or 'iCloud' in s.title():
                source = s
                break
        if not source:
            source = sources[0]
        calendar.setSource_(source)
    else:
        print("❌ 没有可用的 source")
        return None

    # 调试输出
    print(f"    source: {source.title()}")

    # 保存 calendar
    result, error = store.saveCalendar_commit_error_(calendar, True, None)
    if result:
        print(f"✅ 创建列表: {LIST_NAME}")
        return calendar
    else:
        print(f"❌ 创建失败: {error}")
        return None


def parse_message(text):
    """调用 Ollama 解析（qwen2:0.5b）"""
    import requests
    import json
    from datetime import datetime

    # 复用 taskpane_app.py 的 call_ollama
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from taskpane_app import call_ollama
        parsed, err = call_ollama(text)
        return parsed, err
    except Exception as e:
        return None, str(e)


def cmd_init():
    """初始化：创建 TaskPane 列表"""
    print("=" * 50)
    print("TaskPane Reminders 初始化")
    print("=" * 50)
    print()

    store = get_store()
    print("✅ EventKit 授权完成")

    cal = get_or_create_taskpane(store)
    if cal:
        print(f"✅ 列表 ID: {cal.calendarIdentifier()}")
        print()
        print("下一步:")
        print("  1. 打开 Reminders App")
        print("  2. 按 Cmd+R 刷新")
        print("  3. 左侧栏应该看到 'TaskPane' 列表")
        print()
        print("测试添加任务:")
        print(f'  python3 {__file__} add "@小王 紧急！明天提交Q3财报"')


def cmd_add(text):
    """添加任务到 Reminders"""
    if not text:
        print("用法: python3 setup_reminders.py add \"消息\"")
        sys.exit(1)

    print(f">>> 消息: {text}")

    # 1. LLM 解析
    print("    LLM 解析中...", end=" ", flush=True)
    parsed, err = parse_message(text)
    if err:
        print(f"\n❌ 解析失败: {err}")
        sys.exit(1)
    if not parsed:
        print("\n❌ 未返回结果")
        sys.exit(1)

    if not parsed.get("is_task"):
        print(f"\n⏭  不是任务: {parsed.get('reasoning', '')}")
        return

    print(f"OK")
    title_raw = parsed.get('title', '(无标题)')[:100]
    priority = parsed.get('priority', 'P2')
    deadline_str = parsed.get('deadline')
    emoji = PRIORITY_EMOJI.get(priority, "")
    full_title = f"{emoji} [{priority}] {title_raw}"
    print(f"    → {full_title}")
    print(f"    → deadline: {deadline_str or '(无)'}")

    # 2. EventKit 写入
    print("    写入 Reminders...", end=" ", flush=True)
    store = get_store()
    cal = get_or_create_taskpane(store)
    if not cal:
        print("❌")
        sys.exit(1)

    reminder = EventKit.EKReminder.reminderWithEventStore_(store)
    reminder.setTitle_(full_title)
    reminder.setCalendar_(cal)

    # 设置 body（reasoning）
    if parsed.get("reasoning"):
        reminder.setNotes_(f"判断: {parsed['reasoning']}\n原文: {text}")

    # 设置 due date
    if deadline_str:
        try:
            dt = datetime.fromisoformat(deadline_str)
            comps = EventKit.NSDateComponents.alloc().init()
            comps.setYear_(dt.year)
            comps.setMonth_(dt.month)
            comps.setDay_(dt.day)
            comps.setHour_(dt.hour)
            comps.setMinute_(dt.minute)
            comps.setSecond_(dt.second)
            reminder.setDueDateComponents_(comps)
        except Exception as e:
            print(f"\n⚠️  日期解析失败: {e}")

    # 设置 priority（pyobjc 优先级: 0=none, 1=high, 5=medium, 9=low）
    if priority == "P0":
        reminder.setPriority_(1)  # high
    elif priority == "P1":
        reminder.setPriority_(5)  # medium

    result, error = store.saveReminder_commit_error_(reminder, True, None)
    if result:
        print("✅")
        print()
        print("🎉 已添加到 Reminders!")
        print("   打开 Reminders App → 看 'TaskPane' 列表")
    else:
        print(f"\n❌ 保存失败: {error}")


def cmd_list():
    """列出所有 Reminders 任务"""
    store = get_store()
    cal = get_or_create_taskpane(store)
    if not cal:
        sys.exit(1)

    # 获取 incomplete reminders
    predicate = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
        None, None, [cal]
    )
    reminders = store.remindersMatchingPredicate_(predicate) or []

    print(f"TaskPane 列表（{len(reminders)} 条未完成）:")
    print("=" * 50)

    for i, r in enumerate(reminders, 1):
        title = r.title() or "(无标题)"
        due = ""
        if r.dueDateComponents():
            comps = r.dueDateComponents()
            due = f"{comps.year()}-{comps.month():02d}-{comps.day():02d}"
            if comps.hour():
                due += f" {comps.hour():02d}:{comps.minute():02d}"
        prio_map = {1: "[P0]", 5: "[P1]", 9: "[P3]"}
        prio = prio_map.get(r.priority(), "[P2]")
        due_str = f" | Due: {due}" if due else ""
        print(f"  [{i}] {prio} {title}{due_str}")

    print()


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 setup_reminders.py init                    # 创建列表")
        print('  python3 setup_reminders.py add "消息内容"          # 添加任务')
        print("  python3 setup_reminders.py list                    # 列出任务")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        cmd_init()
    elif cmd == "add":
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        cmd_add(text)
    elif cmd == "list":
        cmd_list()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()