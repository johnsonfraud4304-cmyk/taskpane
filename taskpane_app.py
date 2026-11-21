"""
TaskPane — macOS 菜单栏 App
功能：浮动窗口接收粘贴的消息，LLM 提取任务/截止/优先级，按优先级排序，自动提醒
作者: Hermes Agent
"""
import rumps
import json
import os
import sqlite3
import threading
import webbrowser
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ====== 配置 ======
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
LOG_DIR = APP_DIR / "logs"
PLUGIN_DIR = APP_DIR / "plugins"
WEB_DIR = APP_DIR / "web"
DB_PATH = DATA_DIR / "tasks.db"
LOG_FILE = LOG_DIR / "taskpane.log"

OLLAMA_URL = "http://127.0.0.1:11434"
# 默认模型：qwen2:0.5b（352MB, ~1s/次, 94.7% 准确率）
# 可切 qwen2.5:7b（4.7GB, ~12s/次, 100% 准确率）— export TASKPANE_MODEL=qwen2.5:7b
PRIMARY_MODEL = "qwen2:0.5b"  # 默认用 0.5b 追求速度
FALLBACK_MODEL = "qwen2:0.5b"


def get_active_model():
    """根据环境变量 + 已下载模型，自动选择可用模型"""
    env_model = os.environ.get("TASKPANE_MODEL")
    if env_model:
        return env_model
    # 检查主模型是否已下载
    try:
        import requests
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            if PRIMARY_MODEL in models or any(m.startswith(PRIMARY_MODEL) for m in models):
                return PRIMARY_MODEL
            if FALLBACK_MODEL in models:
                return FALLBACK_MODEL
    except Exception:
        pass
    return FALLBACK_MODEL


OLLAMA_MODEL = get_active_model()

# 全局端口（避免和已有服务冲突）
WEB_PORT = 8911

for d in [DATA_DIR, LOG_DIR, PLUGIN_DIR, WEB_DIR]:
    d.mkdir(exist_ok=True)


# ====== 数据库 ======
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        raw_text TEXT,
        title TEXT,
        deadline TEXT,
        priority TEXT,
        assigned_to_me INTEGER,
        source TEXT,
        status TEXT DEFAULT 'pending',
        auto_completable INTEGER DEFAULT 0,
        auto_handler TEXT,
        reminder_sent INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + "\n")


# ====== LLM 解析 =====
PARSE_PROMPT = """你是任务提取助手。判断消息是否是任务，并提取结构化字段。

【输出严格 JSON，无 markdown 包裹，无注释，无任何前缀，不要重复示例】
{
  "is_task": true或false,
  "title": "任务标题（动宾短语，不超过15字）",
  "deadline": "YYYY-MM-DDTHH:MM:SS 或 null",
  "priority": "P0|P1|P2|P3",
  "assigned_to_me": true或false,
  "auto_completable": true或false,
  "reasoning": "一句简短判断理由"
}

只输出 JSON 对象本身（一个 {...}），不要前缀如"输出:"、不要重复上面示例。

【判断 is_task】
- true: 有人被指派做事、要求提交/回复/查看/修改、有明确动作请求、群发布置（"麻烦大家..."）
- true 即使没明确@但有动作动词+截止时间（如"周末前把X改了""明天提交XX"）
- false: 闲聊/寒暄("大家好""吃了吗""哈哈""笑死")/通知/分享/感谢/通知类（"明天放假"=通知非任务）/纯信息/问好/接话/聊天/表情包
- false 关键词: "大家好""晚上好""早上好""哈哈""吃了吗""干嘛呢""在吗"
- true 关键词: "@""麻烦""请""帮忙""记得""别忘了""要""需要""布置""汇报""交""提交""完成""修改""更新""发到""整理""准备""把""那个"
- 关键：含"把...改/做/写/发/弄/弄好" + 任何时间词 → 通常是任务

【priority 优先级】
- P0: 含"紧急""急""马上""立刻""今天""今晚""P0""asap""截止明天""截止今天"
- P1: 含"尽快""本周""这周""周五""重要""优先""下午""帮忙"+"时间词"组合、"请X"+"时间词"组合
- P2: 普通任务，无明确加急词
- P3: "不急""有空再""建议""可以"
- 关键: "请/帮忙/劳驾"+"这周/尽快/尽快" → P1 (客气请求 + 时间约束 = 重要任务)
- 关键: "请/帮忙"+"无时间" → P2

【assigned_to_me】
- true: 含"@我名字""@我""@小王"且我名字匹配、消息直接对我说
- false: 指派给别人、群发、未指定具体人

【auto_completable 关键！】
- true: 数据查询("查股价""查天气""查文件")、信息检索、查日程、订会议室、拉取报告
- false: 写报告/写代码/做决策/分析问题/创作内容/技术方案/财务分析/PPT/翻译

【deadline 关键！】
- 必须输出 ISO 格式: YYYY-MM-DDTHH:MM:SS
- 现在是 {{NOW}}，请以此推算
- "明天/明天上午" → 明天日期 09:00:00（除非有具体时间）
- "明天 X 点" → 明天日期 X:00:00
- "今天" → 今天日期 18:00:00
- "今晚" → 今天日期 20:00:00
- "周五" → 下周五 18:00:00
- "周末前" → 本周六 18:00:00
- "下周" → 下周一 09:00:00
- "月底前/月末" → 当月最后一天 18:00:00
- "X月X日" → 该日期 18:00:00（无具体时间）
- 无明确截止 → null（必须是小写 null，不要写"无""未指定"）

【Few-shot 示例】

消息: "@我 紧急！明天下班前提交Q3财报分析给李总"
输出: {"is_task": true, "title": "提交Q3财报给李总", "deadline": "<明天日期>T18:00:00", "priority": "P0", "assigned_to_me": true, "auto_completable": false, "reasoning": "@我指派+紧急+截止明天+写报告"}

消息: "帮我查一下 600519 的最新股价"
输出: {"is_task": true, "title": "查600519股价", "deadline": null, "priority": "P2", "assigned_to_me": true, "auto_completable": true, "reasoning": "数据查询可自动"}

消息: "今天下午 3 点在 301 会议室开项目讨论会"
输出: {"is_task": true, "title": "参加3点项目讨论会", "deadline": "<今天日期>T15:00:00", "priority": "P1", "assigned_to_me": true, "auto_completable": false, "reasoning": "会议需出席"}

消息: "周末前把那个文档改了"
输出: {"is_task": true, "title": "修改文档", "deadline": "<本周六日期>T18:00:00", "priority": "P1", "assigned_to_me": true, "auto_completable": false, "reasoning": "截止周末+修改任务，即使无@也是任务"}

消息: "哈哈哈哈哈笑死我了"
输出: {"is_task": false, "title": null, "deadline": null, "priority": "P2", "assigned_to_me": false, "auto_completable": false, "reasoning": "闲聊"}

消息: "明天放假一天"
输出: {"is_task": false, "title": null, "deadline": null, "priority": "P2", "assigned_to_me": false, "auto_completable": false, "reasoning": "通知类非任务"}

消息: "写一份技术报告，比较 LeanDojo 和 Lean Copilot 的差异"
输出: {"is_task": true, "title": "写LeanDojo对比报告", "deadline": null, "priority": "P2", "assigned_to_me": false, "auto_completable": false, "reasoning": "明确的写作任务（写一份+具体内容），即使无人称也是任务"}

消息: "大家晚上好啊，吃了吗？"
输出: {"is_task": false, "title": null, "deadline": null, "priority": "P2", "assigned_to_me": false, "auto_completable": false, "reasoning": "寒暄聊天"}

消息: "Q4 应该重点发展哪个方向？大家讨论一下"
输出: {"is_task": true, "title": "讨论Q4发展方向", "deadline": null, "priority": "P2", "assigned_to_me": false, "auto_completable": false, "reasoning": "讨论/决策类任务"}

消息: "请张老师帮忙看下这周的课件，thanks"
输出: {"is_task": true, "title": "查看本周课件", "deadline": "<本周日日期>T18:00:00", "priority": "P1", "assigned_to_me": false, "auto_completable": false, "reasoning": "客气请求+这周时间约束→P1"}

【待解析消息】
"""


def extract_first_json(text):
    """从文本中提取第一个完整的 JSON 对象（栈匹配）"""
    start = text.find('{')
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\':
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


# 非任务的强信号关键词（基于 LLM reasoning 或 title）
NON_TASK_SIGNALS = ["闲聊", "寒暄", "通知", "问好", "接话", "聊天", "在吗", "吃了吗", "干嘛呢", "放假", "哈哈哈", "笑死"]

# 任务的强信号关键词
TASK_SIGNALS = ["紧急", "截止", "提交", "汇报", "修改", "写", "查", "整理", "准备", "记得", "别忘了", "@", "请", "麻烦"]


def post_process(parsed):
    """LLM 输出后处理：
    只做轻度规整，不改变 is_task 判定（让 LLM 决定）
    """
    # priority 标准化
    prio = parsed.get("priority", "P2")
    if prio not in ("P0", "P1", "P2", "P3"):
        parsed["priority"] = "P2"
    return parsed


def call_ollama(text):
    """调用本地 Ollama 提取任务"""
    import requests
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    weekday_cn = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
    now_str_full = f"{now_str} 星期{weekday_cn}"

    # 计算时间占位符
    tomorrow_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    today_date = now.strftime("%Y-%m-%d")
    days_to_sat = (5 - now.weekday()) % 7
    if days_to_sat == 0:
        days_to_sat = 7
    saturday_date = (now + timedelta(days=days_to_sat)).strftime("%Y-%m-%d")

    # 注入动态时间到 prompt
    prompt = PARSE_PROMPT.replace("{{NOW}}", now_str_full)
    prompt = prompt.replace("<明天日期>", tomorrow_date)
    prompt = prompt.replace("<今天日期>", today_date)
    prompt = prompt.replace("<本周六日期>", saturday_date)
    prompt = prompt + text

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "10m",  # 模型常驻内存 10 分钟（避免每次重新加载）
                "options": {
                    "temperature": 0.0,
                    "num_predict": 200,
                    "num_ctx": 2048,
                    "top_p": 0.9,
                    "repeat_penalty": 1.05,
                }
            },
            timeout=30
        )
        if r.status_code != 200:
            return None, f"Ollama HTTP {r.status_code}"
        response = r.json().get("response", "")
        response = response.strip()

        # 提取 JSON：先剥 markdown，再找完整对象
        if response.startswith("```"):
            response = response.split("```", 2)[1]
            if response.startswith("json"):
                response = response[4:]

        json_str = extract_first_json(response)
        if json_str:
            try:
                parsed = json.loads(json_str)
                parsed = post_process(parsed)  # 后处理：修复矛盾 + 边界
                return normalize_parsed(parsed), None
            except json.JSONDecodeError as e:
                return None, f"JSON parse error: {e} | raw: {json_str[:200]}"
        return None, f"No JSON in response: {response[:200]}"
    except requests.exceptions.ConnectionError:
        return None, "Ollama 未运行 (启动: ollama serve)"
    except Exception as e:
        return None, f"Error: {e}"


def normalize_parsed(parsed):
    """把 LLM 输出的字段规整"""
    # 标准化 deadline
    dl = parsed.get("deadline")
    if dl and isinstance(dl, str):
        dl = dl.strip()
        if dl.lower() in ("null", "none", "", "无", "未指定"):
            parsed["deadline"] = None
        else:
            # 如果是中文模糊表达"明天"，尝试规则化
            if not any(c.isdigit() for c in dl):
                parsed["deadline"] = fuzzy_to_iso(dl)
            else:
                # 已有数字，尝试 ISO 解析
                try:
                    parsed["deadline"] = datetime.fromisoformat(
                        dl.replace("/", "-").replace(" ", "T")
                    ).isoformat()
                except:
                    parsed["deadline"] = None
    # 标准化 priority
    p = str(parsed.get("priority", "P2")).upper().replace(" ", "")
    if p not in ("P0", "P1", "P2", "P3"):
        parsed["priority"] = "P2"
    else:
        parsed["priority"] = p
    # 标准化 auto_completable（必须 boolean）
    parsed["auto_completable"] = bool(parsed.get("auto_completable", False))
    parsed["assigned_to_me"] = bool(parsed.get("assigned_to_me", False))
    return parsed


def fuzzy_to_iso(text):
    """处理中文模糊日期"""
    text = text.strip()
    now = datetime.now()
    if "今天" in text:
        return now.replace(hour=18, minute=0, second=0).isoformat()
    if "明天" in text:
        return (now + timedelta(days=1)).replace(hour=18, minute=0, second=0).isoformat()
    if "后天" in text:
        return (now + timedelta(days=2)).replace(hour=18, minute=0, second=0).isoformat()
    if "周末" in text or "周末前" in text:
        days_to_sat = (5 - now.weekday()) % 7 or 7
        return (now + timedelta(days=days_to_sat)).replace(hour=18, minute=0, second=0).isoformat()
    if "月底" in text or "月末" in text:
        next_month = now.replace(day=1) + timedelta(days=31)
        last_day = next_month - timedelta(days=next_month.day)
        return last_day.replace(hour=18, minute=0, second=0).isoformat()
    if "下周一" in text:
        days = (7 - now.weekday()) % 7 or 7
        return (now + timedelta(days=days)).replace(hour=18, minute=0, second=0).isoformat()
    return None


def save_task(parsed, raw_text, source="manual"):
    """保存解析后的任务"""
    if not parsed.get("is_task"):
        return None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO tasks
        (created_at, raw_text, title, deadline, priority, assigned_to_me,
         source, auto_completable, auto_handler, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (datetime.now().isoformat(),
         raw_text[:500],
         parsed.get("title", "(untitled)")[:50],
         parsed.get("deadline"),
         parsed.get("priority", "P2"),
         int(parsed.get("assigned_to_me", False)),
         source,
         int(parsed.get("auto_completable", False)),
         parsed.get("suggested_action"),
         "pending"))
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    return task_id


def list_tasks(filter_status="pending"):
    """列出任务"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if filter_status == "all":
        c.execute("SELECT * FROM tasks ORDER BY "
                  "CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 "
                  "WHEN 'P2' THEN 2 ELSE 3 END, "
                  "COALESCE(deadline, '9999'), id DESC")
    else:
        c.execute("SELECT * FROM tasks WHERE status=? ORDER BY "
                  "CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 "
                  "WHEN 'P2' THEN 2 ELSE 'P3' END, "
                  "COALESCE(deadline, '9999'), id DESC",
                  (filter_status,))
    rows = c.fetchall()
    conn.close()
    cols = ['id', 'created_at', 'raw_text', 'title', 'deadline',
            'priority', 'assigned_to_me', 'source', 'status',
            'auto_completable', 'auto_handler', 'reminder_sent']
    return [dict(zip(cols, row)) for row in rows]


# ====== 提醒检查 ======
def check_reminders():
    """检查需要提醒的任务（截止前3天/1天/当天）"""
    now = datetime.now()
    tasks = list_tasks("pending")
    reminded = []
    for t in tasks:
        if not t['deadline']:
            continue
        try:
            dl = datetime.fromisoformat(t['deadline'])
        except:
            continue
        days_left = (dl - now).days
        # 截止前 3 天 / 1 天 / 当天 / 已过期
        if t['reminder_sent']:
            continue
        if days_left <= 3 and days_left >= 0:
            reminded.append((t, f"还有 {days_left} 天截止"))
        elif days_left < 0:
            reminded.append((t, f"已过期 {-days_left} 天！"))
        if days_left <= 3:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE tasks SET reminder_sent=1 WHERE id=?", (t['id'],))
            conn.commit()
            conn.close()
    return reminded


# ====== 菜单栏 App ======
class TaskPaneApp(rumps.App):
    def __init__(self):
        super().__init__("🔔", quit_button="退出 TaskPane")
        self.menu = [
            rumps.MenuItem("打开面板", callback=self.open_panel),
            None,
            rumps.MenuItem("📋 粘贴并解析...", callback=self.paste_and_parse),
            None,
            rumps.MenuItem("📊 当前任务", callback=self.show_tasks),
            rumps.MenuItem("⏰ 检查提醒", callback=self.check_reminders_menu),
            None,
            rumps.MenuItem("🔧 设置", callback=self.settings_menu),
        ]
        self.timer = rumps.Timer(self.periodic_check, 60)  # 每分钟检查
        self.timer.start()
        init_db()
        log("TaskPane started")

    def open_panel(self, _):
        url = f"http://127.0.0.1:{WEB_PORT}"
        webbrowser.open(url)

    def paste_and_parse(self, _):
        # 弹出窗口让用户粘贴
        response = rumps.Window(
            title="粘贴消息（多行 OK）",
            default_text="",
            ok="解析",
            cancel="取消",
            dimensions=(480, 240)
        ).run()
        if response.clicked and response.text.strip():
            text = response.text.strip()
            log(f"Parsing: {text[:80]}")
            parsed, err = call_ollama(text)
            if err:
                rumps.notification("TaskPane", "解析失败", err)
                return
            if not parsed:
                rumps.notification("TaskPane", "解析失败", "未返回结果")
                return
            if not parsed.get("is_task"):
                rumps.notification("TaskPane", "非任务消息", text[:60])
                return
            tid = save_task(parsed, text, "manual")
            title = parsed.get("title", "(无标题)")
            prio = parsed.get("priority", "P2")
            rumps.notification(
                "TaskPane · 新任务",
                f"[{prio}] {title}",
                f"截止: {parsed.get('deadline') or '未指定'} | "
                f"可自动: {'是' if parsed.get('auto_completable') else '否'}"
            )

    def show_tasks(self, _):
        tasks = list_tasks("pending")
        if not tasks:
            rumps.alert("TaskPane", "🎉 没有待办任务")
            return
        lines = []
        for t in tasks[:15]:
            dl = t['deadline'][5:16] if t['deadline'] else "无截止"
            star = "🤖" if t['auto_completable'] else "👤"
            lines.append(f"[{t['priority']}] {star} {t['title']} (截止 {dl})")
        rumps.alert("TaskPane 待办", "\n".join(lines))

    def check_reminders_menu(self, _):
        reminded = check_reminders()
        if not reminded:
            rumps.alert("TaskPane", "当前无新提醒")
            return
        lines = [f"· {t['title']} ({msg})" for t, msg in reminded]
        rumps.alert("TaskPane · 提醒", "\n".join(lines))

    def settings_menu(self, _):
        rumps.alert("TaskPane 设置",
                    f"Web 面板: http://127.0.0.1:{WEB_PORT}\n"
                    f"Ollama: {OLLAMA_URL}\n"
                    f"模型: {OLLAMA_MODEL}\n"
                    f"数据库: {DB_PATH}\n"
                    f"插件目录: {PLUGIN_DIR}")

    def periodic_check(self, _):
        # 每分钟静默检查提醒，发系统通知
        reminded = check_reminders()
        for t, msg in reminded:
            rumps.notification(
                "TaskPane 提醒",
                f"[{t['priority']}] {t['title']}",
                msg
            )


if __name__ == "__main__":
    # 同时启动 Web 服务（在后台线程）
    from web_server import start_server_thread
    start_server_thread(WEB_PORT, WEB_DIR, DB_PATH, PLUGIN_DIR)
    log(f"Web panel at http://127.0.0.1:{WEB_PORT}")
    TaskPaneApp().run()