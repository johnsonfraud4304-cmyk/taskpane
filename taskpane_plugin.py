"""
TaskPane - Apple Reminders 插件 (EventKit 版本)
=================================================
完全用 pyobjc EventKit API（绕过 osascript TCC bug）

用法:
  pip3 install pyobjc-framework-EventKit
  python3 taskpane_plugin.py check     # 检查环境
  python3 taskpane_plugin.py init      # 创建 TaskPane 列表
  python3 taskpane_plugin.py add "消息"  # 添加任务
  python3 taskpane_plugin.py list      # 列出任务
  python3 taskpane_plugin.py interactive  # 交互模式
"""
import sys
import os
import time
from pathlib import Path
from datetime import datetime

LIST_NAME = "TaskPane"
PRIORITY_EMOJI = {"P0": "🔥", "P1": "⚠️", "P2": "📌", "P3": "📎"}

# 强制本地小模型（速度优化）
os.environ.setdefault("TASKPANE_MODEL", "qwen2:0.5b")
sys.path.insert(0, str(Path(__file__).parent))


# ==================== EventKit 集成 ====================

def get_store():
    """获取 EKEventStore（首次会弹 EventKit 授权框）"""
    try:
        import EventKit
    except ImportError:
        return None, "未装 pyobjc-framework-EventKit (pip3 install pyobjc-framework-EventKit)"

    store = EventKit.EKEventStore.alloc().init()

    # macOS 14 新 API
    granted = [False]
    error_holder = [None]

    def completion(granted_flag, error):
        granted[0] = granted_flag
        error_holder[0] = error
        if granted_flag:
            print(f"   ✓ 授权成功")
        else:
            print(f"   ✗ 授权被拒: error={error}")

    print("   ⚠️  会弹授权框 'python3 想要访问 Reminders'，请点 '好'")
    try:
        store.requestFullAccessToRemindersWithCompletion_(completion)
    except AttributeError:
        # fallback: 老 API
        store.requestAccessToEntityType_completion_(0, completion)

    # 等授权（异步）— 最多等 30 秒
    for i in range(60):
        time.sleep(0.5)
        if granted[0]:
            break
        # 每 2 秒打印一次等待状态
        if i % 4 == 0:
            print(f"   等待授权... {i//2 + 1}s")

    if not granted[0]:
        return None, f"EventKit 授权失败（用户拒绝或未弹窗）{error_holder[0] or ''}"

    return store, None


def get_or_create_taskpane(store):
    """获取 TaskPane 列表（如不存在返回 None 让用户手动建）"""
    import EventKit

    # 方法 1: 直接查 Reminders 列表
    calendars = store.calendarsForEntityType_(0)  # 0 = Reminder
    for cal in calendars:
        if cal.title() == LIST_NAME:
            return cal

    # 方法 2: macOS 14.6 EventKit bug — iCloud reminder 列表可能 entityType=1
    # 尝试 entityType=1 找 iCloud 上的列表
    all_cals = store.calendarsForEntityType_(1)  # 1 = Event
    for cal in all_cals:
        if cal.title() == LIST_NAME and cal.allowedEntityTypes() & 2:  # 2 = Reminder
            print(f"   ✓ 在 iCloud Events 里找到 TaskPane (entityType=1, allowed Reminders)")
            return cal

    # 方法 3: 用 default reminder 列表的 source 找所有可能
    default = store.defaultCalendarForNewReminders()
    if default:
        source = default.source()
        if source:
            try:
                source_cals = source.calendarsForEntityType_(0)
                for cal in source_cals:
                    if cal.title() == LIST_NAME:
                        return cal
            except:
                pass

    # 不存在 — 提示用户手动建
    print()
    print("   ⚠️  TaskPane 列表在 EventKit 里找不到")
    print()
    print("   💡 解决方法（macOS 14.6 EventKit bug: iCloud Reminders 列表可能不显示）:")
    print("      1. 打开 Reminders App")
    print("      2. 左侧栏底部点 '+' 按钮（或 Cmd+Shift+N）")
    print("      3. 输入 'TaskPane'，回车")
    print("      4. 回到 Terminal 重跑命令")
    print()
    return None


def add_reminder_eventkit(text, store, cal):
    """通过 EventKit 添加 reminder"""
    import EventKit
    from datetime import datetime

    # 1. LLM 解析
    from taskpane_app import call_ollama
    parsed, err = call_ollama(text)
    if err:
        return False, f"解析失败: {err}"
    if not parsed:
        return False, "未返回结果"
    if not parsed.get("is_task"):
        return False, f"不是任务 ({parsed.get('reasoning', '')})"

    # 2. 构建字段
    title = parsed.get("title", "(无标题)")[:200]
    priority = parsed.get("priority", "P2")
    emoji = PRIORITY_EMOJI.get(priority, "")
    full_title = f"{emoji} [{priority}] {title}"

    # 3. 创建 reminder
    reminder = EventKit.EKReminder.reminderWithEventStore_(store)
    reminder.setTitle_(full_title)
    reminder.setCalendar_(cal)

    # body
    body = []
    if text:
        body.append(f"📨 原文:\n{text[:500]}")
    if parsed.get("reasoning"):
        body.append(f"💡 判断: {parsed['reasoning']}")
    reminder.setNotes_("\n\n".join(body))

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
            reminder.setDueDateComponents_(comps)
        except Exception as e:
            pass  # 静默忽略日期错误

    # priority (1=high, 5=medium, 9=low)
    if priority == "P0":
        reminder.setPriority_(1)
    elif priority == "P1":
        reminder.setPriority_(5)

    # 4. 保存
    result, error = store.saveReminder_commit_error_(reminder, True, None)
    if result:
        return True, full_title
    return False, str(error or "save failed")


def list_reminders_eventkit(store, cal):
    """列出 TaskPane 列表的所有未完成 reminders"""
    predicate = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
        None, None, [cal]
    )
    reminders = store.remindersMatchingPredicate_(predicate) or []
    results = []
    for r in reminders:
        title = r.title() or "(无标题)"
        due = ""
        if r.dueDateComponents():
            comps = r.dueDateComponents()
            due = f"{comps.year()}-{comps.month():02d}-{comps.day():02d}"
            if comps.hour():
                due += f" {comps.hour():02d}:{comps.minute():02d}"
        prio_map = {1: "[P0]", 5: "[P1]", 9: "[P3]"}
        prio = prio_map.get(r.priority(), "[P2]")
        results.append({
            "title": title,
            "due": due,
            "priority": prio,
        })
    return results


# ==================== 命令行入口 ====================

def cmd_check():
    """检查环境"""
    print("=" * 50)
    print("TaskPane 环境检查")
    print("=" * 50)

    # 1. pyobjc
    try:
        import EventKit
        print(f"✅ pyobjc-framework-EventKit: 已装")
    except ImportError:
        print(f"❌ pyobjc-framework-EventKit: 未装")
        print(f"   安装: pip3 install pyobjc-framework-EventKit")
        return False

    # 2. Ollama
    import requests
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m['name'] for m in r.json().get('models', [])]
            print(f"✅ Ollama: {len(models)} 模型")
            for m in models[:3]:
                print(f"     {m}")
    except:
        print(f"❌ Ollama: 未运行 (启动: ollama serve)")
        return False

    # 3. EventKit 授权
    store, err = get_store()
    if err:
        print(f"❌ EventKit: {err}")
        return False
    print(f"✅ EventKit: 授权成功")

    # 4. TaskPane 列表
    cal = get_or_create_taskpane(store)
    if cal:
        print(f"✅ TaskPane 列表: 就绪")
    else:
        print()
        print("⚠️  TaskPane 列表不存在 — 需要手动创建")
        print("=" * 50)
        return False

    print()
    print("✅ 所有检查通过！可以开始使用:")
    print(f'   python3 {__file__} add "@小王 紧急！明天提交Q3财报"')
    return True


def cmd_init():
    """初始化：创建 TaskPane 列表"""
    print("=" * 50)
    print("TaskPane Reminders 初始化")
    print("=" * 50)
    print()
    print("⚠️  会弹 macOS 授权框 'python3 想要访问 Reminders'")
    print("   请点 '好'")
    print()

    store, err = get_store()
    if err:
        print(f"❌ {err}")
        sys.exit(1)
    print("✅ EventKit 授权完成")

    cal = get_or_create_taskpane(store)
    if cal:
        print(f"✅ TaskPane 列表就绪")
        print()
        print("下一步:")
        print("  1. 打开 Reminders App → Cmd+R 刷新")
        print("  2. 左侧栏应该有 'TaskPane' 列表")
    else:
        print("❌ 创建失败")
        sys.exit(1)


def cmd_add(text):
    """添加任务"""
    if not text:
        print('用法: python3 taskpane_plugin.py add "消息内容"')
        sys.exit(1)

    print(f">>> 消息: {text}")

    store, err = get_store()
    if err:
        print(f"❌ {err}")
        sys.exit(1)

    cal = get_or_create_taskpane(store)
    if not cal:
        print("❌ TaskPane 列表不可用")
        sys.exit(1)

    ok, msg = add_reminder_eventkit(text, store, cal)
    if ok:
        print(f"✅ 已添加: {msg}")
        print("   打开 Reminders App 查看")
    else:
        print(f"❌ 失败: {msg}")
        sys.exit(1)


def cmd_list():
    """列出 TaskPane 列表"""
    store, err = get_store()
    if err:
        print(f"❌ {err}")
        sys.exit(1)

    cal = get_or_create_taskpane(store)
    if not cal:
        print("❌ TaskPane 列表不可用")
        sys.exit(1)

    reminders = list_reminders_eventkit(store, cal)
    print(f"TaskPane 列表（{len(reminders)} 条未完成）:")
    print("=" * 50)
    for i, r in enumerate(reminders, 1):
        due_str = f" | Due: {r['due']}" if r['due'] else ""
        print(f"  [{i}] {r['priority']} {r['title']}{due_str}")
    print()


def cmd_interactive():
    """交互模式"""
    print("=" * 50)
    print("TaskPane 交互模式")
    print("=" * 50)
    print("粘贴消息后回车添加，输入 'quit' 退出")
    print()

    store, err = get_store()
    if err:
        print(f"❌ {err}")
        sys.exit(1)

    cal = get_or_create_taskpane(store)
    if not cal:
        sys.exit(1)

    print("✅ 就绪，开始粘贴消息:")
    print()

    while True:
        try:
            text = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出")
            break

        if not text or text.lower() in ('quit', 'exit', 'q'):
            break

        ok, msg = add_reminder_eventkit(text, store, cal)
        if ok:
            print(f"   ✅ {msg}")
        else:
            print(f"   ⏭  {msg}")
        print()


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 taskpane_plugin.py check                  # 检查环境")
        print("  python3 taskpane_plugin.py init                   # 创建 TaskPane 列表")
        print('  python3 taskpane_plugin.py add "消息内容"          # 添加任务')
        print("  python3 taskpane_plugin.py list                   # 列出任务")
        print("  python3 taskpane_plugin.py interactive            # 交互模式")
        sys.exit(1)

    cmd = sys.argv[1]
    arg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if cmd == "check":
        cmd_check()
    elif cmd == "init":
        cmd_init()
    elif cmd == "add":
        cmd_add(arg)
    elif cmd == "list":
        cmd_list()
    elif cmd in ("interactive", "i"):
        cmd_interactive()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()