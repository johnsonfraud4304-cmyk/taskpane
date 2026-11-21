"""
TaskPane Menu Bar App - 一键添加 Reminder
==========================================
功能：
- 菜单栏常驻 🔔 图标
- 点击 "📋 添加任务..." 弹粘贴窗口
- 自动调 LLM 解析 + 写入 Reminders
- 支持从剪贴板读取（如果用户已经复制了消息）
- 全局快捷键 Cmd+Shift+Y 触发剪贴板添加（避开录屏冲突）
"""
import rumps
import subprocess
import sys
import os
import threading
from pathlib import Path

APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR))

# 强制本地小模型（速度优化）
os.environ.setdefault("TASKPANE_MODEL", "qwen2:0.5b")

from taskpane_plugin import get_store, get_or_create_taskpane, add_reminder_eventkit, cmd_check
from taskpane_app import call_ollama


# 全局快捷键监听（用 PyObjC 直接调 NSEvent - 不需要 pynput）
def start_hotkey_listener(callback):
    """用 PyObjC 直接调 NSEvent.addGlobalMonitorForEventsMatchingMask:handler:
    在主线程注册监听器（需要 NSApplication run loop）
    """
    try:
        from AppKit import NSEvent, NSCommandKeyMask, NSShiftKeyMask
    except ImportError:
        print("⚠️  AppKit 未装，跳过全局快捷键")
        return

    Y_KEY_CODE = 16  # 'Y' key code on macOS

    def handler(event):
        flags = event.modifierFlags()
        keycode = event.keyCode()

        # 检查是否 Cmd+Shift+Y
        if (flags & NSCommandKeyMask) and (flags & NSShiftKeyMask) and keycode == Y_KEY_CODE:
            print(f"🔥 全局快捷键触发: Cmd+Shift+Y", flush=True)
            try:
                callback(None)
            except Exception as ex:
                print(f"callback 异常: {ex}", flush=True)
                import traceback
                traceback.print_exc()

    try:
        monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSCommandKeyMask | NSShiftKeyMask,
            handler
        )
        if monitor:
            print(f"✅ 全局快捷键已启用: Cmd+Shift+Y (NSEvent)")
        else:
            print(f"⚠️  NSEvent.addGlobalMonitor 返回 None")
    except Exception as ex:
        print(f"⚠️  NSEvent 监听失败: {ex}")


class TaskPaneMenuBar(rumps.App):
    def __init__(self):
        super().__init__("🔔", quit_button="退出 TaskPane")
        self.menu = [
            rumps.MenuItem("📋 添加任务...", callback=self.add_task_dialog),
            rumps.MenuItem("📋 从剪贴板添加 (Cmd+Shift+Y)", callback=self.add_from_clipboard),
            None,
            rumps.MenuItem("📂 打开 Reminders 列表", callback=self.open_reminders),
            rumps.MenuItem("🔧 检查环境", callback=self.check_env),
            None,
            rumps.MenuItem("ℹ️  使用说明", callback=self.show_help),
        ]

        # 启动全局快捷键监听（包装 callback 接受可选参数）
        def safe_callback(*args):
            print(f"[callback] 进入 callback, args={args}", flush=True)
            try:
                self.add_from_clipboard(None)
                print(f"[callback] callback 完成", flush=True)
            except Exception as ex:
                print(f"[callback] callback 异常: {ex}", flush=True)
                import traceback
                traceback.print_exc()
        start_hotkey_listener(safe_callback)

    def add_task_dialog(self, _):
        """弹粘贴窗口"""
        response = rumps.Window(
            title="粘贴微信/QQ 群消息",
            default_text="",
            ok="解析并添加",
            cancel="取消",
            dimensions=(500, 200)
        ).run()
        if response.clicked and response.text.strip():
            self._process(response.text.strip())

    def add_from_clipboard(self, _):
        """从剪贴板读取"""
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            text = r.stdout.strip()
            if not text:
                # 用 osascript 显示通知（绕过 rumps Info.plist 问题）
                self._notify("TaskPane", "剪贴板为空", "请先复制微信群消息")
                return
            self._process(text)
        except Exception as e:
            self._notify("TaskPane", "读取剪贴板失败", str(e))

    def _notify(self, title, subtitle, message):
        """显示 macOS 通知 - 多种 fallback 方式"""
        # 简化字符串防止引号问题
        title_clean = str(title).replace('"', "'").replace("\\", "")[:50]
        subtitle_clean = str(subtitle).replace('"', "'").replace("\\", "")[:50]
        message_clean = str(message).replace('"', "'").replace("\\", "")[:200]

        # 方法 1: rumps 内置 notification
        try:
            import rumps
            rumps.notification(title, subtitle, message)
            print(f"[通知] rumps: {title} | {subtitle}")
            return
        except Exception as e:
            print(f"rumps 通知失败: {e}")

        # 方法 2: osascript notification
        try:
            script = f'''
                try
                    display notification "{message_clean}" with title "{title_clean}" subtitle "{subtitle_clean}"
                on error errMsg
                    log errMsg
                end try
            '''
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                print(f"[通知] osascript: {title} | {subtitle}")
                return
            else:
                print(f"osascript returncode={result.returncode}, stderr={result.stderr[:100]}")
        except Exception as e:
            print(f"osascript 通知异常: {e}")

        # 方法 3: 改变菜单栏标题（必定可见）
        try:
            old_title = self.title
            self.title = f"🔔 ✓"
            import threading
            def reset_title():
                import time
                time.sleep(3)
                self.title = old_title
            threading.Thread(target=reset_title, daemon=True).start()
            print(f"[菜单栏更新] 🔔 → 🔔 ✓")
            return
        except Exception as e:
            print(f"菜单栏标题更新失败: {e}")

        # 方法 4: macOS 系统级声音（必定有反馈）
        try:
            subprocess.run(["afplay", "/System/Library/Sounds/Ping.aiff"],
                          capture_output=True, timeout=5)
            print(f"[声音] 播放 Ping 提示音")
        except Exception as e:
            print(f"声音播放失败: {e}")

        # 方法 5: 终端输出
        print(f"[通知] {title} | {subtitle} | {message}")

    def _process(self, text):
        """处理消息：解析 + 写入 Reminder"""
        # 1. 先用 LLM 解析（快速反馈）
        parsed, err = call_ollama(text)
        if err:
            self._notify("TaskPane LLM 解析失败", "", err[:200])
            return
        if not parsed:
            self._notify("TaskPane", "", "未返回结果")
            return

        # 显示解析结果
        if not parsed.get("is_task"):
            self._notify(
                "TaskPane ⏭ 不是任务",
                "",
                parsed.get("reasoning", "")
            )
            return

        PRIORITY_EMOJI = {"P0": "🔥", "P1": "⚠️", "P2": "📌", "P3": "📎"}
        priority = parsed.get("priority", "P2")
        emoji = PRIORITY_EMOJI.get(priority, "")
        title = f"{emoji} [{priority}] {parsed.get('title', '(无标题)')}"

        # 2. 写入 Reminders
        store, err = get_store()
        if err:
            self._notify("EventKit 错误", "", err)
            return

        cal = get_or_create_taskpane(store)
        if not cal:
            self._notify("TaskPane 错误", "", "TaskPane 列表找不到")
            return

        ok, msg = add_reminder_eventkit(text, store, cal)
        if ok:
            self._notify(
                "TaskPane ✓ 已添加",
                title[:50],
                "已写入 Reminders 'TaskPane' 列表"
            )
            print(f"✅ 已添加: {title}")
        else:
            self._notify("TaskPane 写入失败", "", msg)
            print(f"❌ 写入失败: {msg}")

    def open_reminders(self, _):
        """打开 Reminders App"""
        subprocess.run(["open", "-a", "Reminders"])

    def check_env(self, _):
        """环境检查"""
        import io
        import contextlib

        # 重定向 cmd_check 输出
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            try:
                cmd_check()
            except SystemExit:
                pass
        output = f.getvalue()

        rumps.alert("TaskPane 环境检查", output)

    def show_help(self, _):
        """使用说明"""
        help_text = """TaskPane 使用说明
=================

1. 复制微信/QQ 群消息
2. 点击菜单栏 🔔
3. 选择 '从剪贴板添加'
4. 自动解析 + 写入 Reminders 'TaskPane' 列表

或者：
1. 点击 🔔 → '添加任务...'
2. 在弹窗粘贴消息
3. 点 '解析并添加'

LLM: qwen2:0.5b (本地，1s 响应)
存储: Apple Reminders 'TaskPane' 列表
iPhone/iPad: 通过 iCloud 自动同步

启动 daemon 后台监控（可选）：
  python3 daemon.py start
"""
        rumps.alert("TaskPane 使用说明", help_text)


if __name__ == "__main__":
    import subprocess
    # 启动时弹一个明显的窗口确认（用户能看到）
    subprocess.Popen([
        "osascript", "-e",
        'display dialog "🔔 TaskPane 已启动！\\n\\n按 Cmd+Shift+Y 触发剪贴板添加\\n或点菜单栏 🔔 图标\\n\\n确认看到本窗口 = 通知工作" buttons {"OK"} default button "OK" with title "TaskPane 已启动"'
    ])
    TaskPaneMenuBar().run()