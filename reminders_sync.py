"""
Apple Reminders 集成 (v2)
- 优先用 remindctl（如果已安装）
- 回退到 osascript 直接调 Reminders App
- 同步 TaskPane pending 任务到 Apple Reminders "TaskPane" 列表
"""
import subprocess
import shutil
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))


def _run(cmd, timeout=10):
    """执行命令"""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def check_reminder_tool():
    """检测可用的 reminder CLI"""
    if shutil.which("remindctl"):
        return "remindctl"
    if shutil.which("osascript"):
        return "osascript"
    return None


def add_reminder_osascript(title, note=None, due=None, list_name="TaskPane"):
    """用 osascript 添加 reminder"""
    # 转义 AppleScript 字符串
    def esc(s):
        return s.replace("\\", "\\\\").replace("\"", "\\\"")

    script_parts = []
    # 1. 确保 list 存在
    script_parts.append(f'tell application "Reminders"')
    script_parts.append(f'  if not (exists list "{list_name}") then')
    script_parts.append(f'    make new list with properties {{name:"{list_name}"}}')
    script_parts.append(f'  end if')

    # 2. 添加 reminder
    script_parts.append(f'  set newReminder to make new reminder at end of list "{list_name}"')
    script_parts.append(f'  set name of newReminder to "{esc(title)}"')
    if note:
        script_parts.append(f'  set body of newReminder to "{esc(note)}"')
    if due:
        # AppleScript date format
        date_str = due.strftime("%Y-%m-%d %H:%M:%S")
        script_parts.append(f'  set due date of newReminder to date "{date_str}"')
    script_parts.append(f'  return id of newReminder')
    script_parts.append(f'end tell')

    script = "\n".join(script_parts)
    r = _run(["osascript", "-e", script], timeout=15)
    if r.returncode == 0:
        return True, r.stdout.strip() or "已添加"
    return False, r.stderr or r.stdout


def add_reminder_remindctl(title, note=None, due=None, list_name="TaskPane"):
    """用 remindctl 添加 reminder"""
    cmd = ["remindctl", "add", title]
    if due:
        cmd.extend(["--when", due.strftime("%Y-%m-%d %H:%M")])
    if note:
        cmd.extend(["--notes", note[:1000]])
    try:
        cmd.extend(["--list", list_name])
    except: pass
    r = _run(cmd, timeout=10)
    return r.returncode == 0, r.stdout or r.stderr


def add_reminder(task):
    """添加单条任务到 Apple Reminders（自动选工具）"""
    tool = check_reminder_tool()
    if not tool:
        return False, "需要 remindctl 或 osascript（macOS 自带）"

    title = f"[{task['priority']}] {task['title']}"[:200]
    note_parts = []
    if task.get('raw_text'):
        note_parts.append(f"原文: {task['raw_text'][:200]}")
    if task.get('auto_handler'):
        note_parts.append(f"建议: {task['auto_handler']}")
    note = "\n".join(note_parts) if note_parts else None

    due = None
    if task['deadline']:
        try:
            due = datetime.fromisoformat(task['deadline'])
        except:
            pass

    if tool == "remindctl":
        return add_reminder_remindctl(title, note, due)
    return add_reminder_osascript(title, note, due)


def get_db_path():
    return Path(__file__).parent / "data" / "tasks.db"


def sync_all_tasks(filter_priority=None, force=False):
    """同步 pending 任务到 Apple Reminders"""
    db = get_db_path()
    if not db.exists():
        return [], "数据库不存在"

    conn = sqlite3.connect(db)
    c = conn.cursor()
    # 检查字段是否存在
    c.execute("PRAGMA table_info(tasks)")
    cols = [row[1] for row in c.fetchall()]
    if "synced_to_reminders" not in cols:
        # 自动迁移
        c.execute("ALTER TABLE tasks ADD COLUMN synced_to_reminders INTEGER DEFAULT 0")
        conn.commit()

    query = "SELECT * FROM tasks WHERE status='pending'"
    params = []
    if not force:
        query += " AND synced_to_reminders=0"
    if filter_priority:
        query += " AND priority=?"
        params.append(filter_priority)

    c.execute(query, params)
    rows = c.fetchall()
    col_names = ['id', 'created_at', 'raw_text', 'title', 'deadline',
                 'priority', 'assigned_to_me', 'source', 'status',
                 'auto_completable', 'auto_handler', 'reminder_sent',
                 'synced_to_reminders']
    conn.close()

    if not rows:
        return [], "没有需要同步的任务"

    results = []
    for row in rows:
        task = dict(zip(col_names, row))
        ok, msg = add_reminder(task)
        results.append({
            "id": task['id'],
            "title": task['title'],
            "ok": ok,
            "msg": msg,
        })
        if ok:
            conn = sqlite3.connect(db)
            c = conn.cursor()
            c.execute("UPDATE tasks SET synced_to_reminders=1 WHERE id=?", (task['id'],))
            conn.commit()
            conn.close()
        print(f"  [{'✓' if ok else '✗'}] {task['title']}: {msg}")

    return results, "完成"


def cmd_sync(priority=None, force=False):
    print("TaskPane → Apple Reminders")
    print("=" * 40)
    tool = check_reminder_tool()
    if not tool:
        print("❌ 没有可用的 reminder 工具")
        print("需要: macOS 自带 osascript（已确认） 或 brew install remindctl")
        sys.exit(1)
    print(f"✓ 使用工具: {tool}")
    print(f"  优先级过滤: {priority or '全部'}")
    print(f"  强制重同步: {'是' if force else '否'}")
    print()
    results, msg = sync_all_tasks(filter_priority=priority, force=force)
    print()
    print(f"结果: {msg}")
    if results:
        ok_count = sum(1 for r in results if r['ok'])
        print(f"  成功 {ok_count}/{len(results)}")
    print()
    print("打开 Reminders App 查看 TaskPane 列表")


def cmd_check():
    print("Tool 检查:")
    print(f"  remindctl: {'✓ 已安装' if shutil.which('remindctl') else '✗ 未安装'}")
    print(f"  osascript: {'✓ 已安装' if shutil.which('osascript') else '✗ 未安装'}")
    print()
    print(f"使用: {check_reminder_tool() or '无可用工具'}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "help":
        print("用法:")
        print("  python3 reminders_sync.py check         - 检查可用工具")
        print("  python3 reminders_sync.py sync          - 同步所有 pending 任务")
        print("  python3 reminders_sync.py sync P0       - 只同步 P0")
        print("  python3 reminders_sync.py sync P1 force - 强制重同步 P1")
    elif args[0] == "check":
        cmd_check()
    elif args[0] == "sync":
        priority = args[1] if len(args) > 1 and args[1] in ("P0", "P1", "P2", "P3") else None
        force = "force" in args
        cmd_sync(priority=priority, force=force)
