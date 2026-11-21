# TaskPane · Apple Reminders AI 插件

把微信群 / QQ 群里的消息原样粘贴过来，自动解析成结构化的 **Apple Reminders 任务**：
标题带优先级、截止时间落到 Due 字段、原始消息和判断理由写进备注。

设计的核心取舍是 **不自己存一份任务数据**：Reminders 就是唯一数据源，靠 iCloud 跨设备同步，不额外引入数据库和 Web 面板——这样不会出现"两个地方各有一份、互相对不上"的经典问题。

```
群消息原文                     Apple Reminders
─────────────────────────     ────────────────────────────────────────
@小王 紧急！明天下班前         🔥 [P0] 提交Q3财报给李总
提交Q3财报给李总               Due: 2026-09-24 18:00
                              Body: 原文 + 💡 判断: @我+紧急+明天+写报告
```

## 工作原理

1. 从剪贴板或输入框拿到一段群消息
2. 交给本地 Ollama 上的小模型（qwen2.5:7b 或 qwen2:0.5b）做信息抽取：是否任务、优先级、截止时间、标题、负责人
3. 通过 pyobjc EventKit 写入 Reminders 指定列表
4. 可选：daemon 长期监听「快速提醒」列表，新条目出现就自动加工后搬到「TaskPane」列表

全程本地推理，除 Ollama 外不依赖任何云端 API。

## 环境要求

- macOS（依赖 EventKit 与 Reminders，Windows / Linux 不可用）
- Python 3.9+
- [Ollama](https://ollama.com)，本地已拉取至少一个模型
- 首次运行需在「系统设置 → 隐私与安全性 → 提醒事项」里授权终端 / python3

## 安装

```bash
git clone <this-repo> taskpane
cd taskpane

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 拉模型（二选一，7b 更准，0.5b 更快）
ollama pull qwen2.5:7b
ollama pull qwen2:0.5b
```

## 四种用法

### 1. 菜单栏 App

```bash
./scripts/start_plugin.sh
```

菜单栏出现 🔔：

- **📋 添加任务...** — 弹窗粘贴消息
- **📋 从剪贴板添加** — 一键读取剪贴板
- **📂 打开 Reminders 列表** — 跳到 Reminders.app

### 2. 单条命令行

```bash
python3 taskpane_plugin.py add "@小王 紧急！明天提交Q3财报"
```

### 3. 交互模式（逐行粘贴）

```bash
python3 taskpane_plugin.py interactive
```

### 4. 后台常驻（监听「快速提醒」列表）

```bash
python3 daemon.py start      # 启动
python3 daemon.py status     # 查看状态
python3 daemon.py stop       # 停止
./scripts/install_daemon.sh  # 装成 LaunchAgent，开机自启
```

## 任务字段约定

| 字段 | 取值 |
|---|---|
| 标题前缀 | 🔥 P0 紧急 / ⚠️ P1 重要 / 📌 P2 普通 / 📎 P3 不急 |
| Due | 解析出的日期时间，写入 Reminders 原生 dueDate |
| Priority | P0 / P1 映射为 Reminders 高优先级，其余留空 |
| Body | 原始消息 + 模型判断依据，便于事后回溯为什么这样排期 |

## 切换模型

```bash
export TASKPANE_MODEL=qwen2.5:7b    # 默认
export TASKPANE_MODEL=qwen2:0.5b    # 轻量，秒回
./scripts/start_plugin.sh
```

改 Reminders 目标列表名：编辑 `taskpane_plugin.py` 顶部的 `REMINDERS_LIST`。

## 测试

```bash
python3 prompt_optimizer.py             # 用默认模型跑 19 条真实场景
python3 prompt_optimizer.py qwen2.5:7b  # 指定模型
python3 test_accuracy.py                # 19 case 准确率
python3 test_quick.py                   # 5 条快速回归
```

测试集是 19 条真实群消息，覆盖 @我、含糊时间、纯通知等边界情况。

## 目录结构

```
taskpane/
├── taskpane_plugin.py     CLI + EventKit 写入，parse_to_reminder() 是主入口
├── taskpane_menubar.py    菜单栏 App（rumps）
├── taskpane_app.py        LLM 解析核心 call_ollama()、v1 独立 App 入口
├── daemon.py              监听「快速提醒」列表并自动加工
├── reminders_sync.py      与 Reminders 的双向同步（v1 遗留，仍可用）
├── model_manager.py       模型拉取与测速
├── prompt_optimizer.py    prompt 自动诊断 / 准确率评测
├── web_server.py          v1 的 SQLite + Web 面板（已弃用，保留供参考）
├── web/index.html         v1 前端
├── db_migrate.py          v1 数据库迁移
├── plugins/               群消息特征规则（QQ 群、微信工作群）
├── scripts/               启动、安装、测试脚本
└── README.md
```

## 已知限制

- 只支持 macOS；EventKit 首次授权必须从真实终端执行，在 IDE 内置终端里经常弹不出授权框
- 目标列表名 `TaskPane`、源列表名 `快速提醒` 是写死的；非中文系统下 Reminders 默认列表名不同，需要自行修改
- 模型能力有限：时间表达含糊（如"下周找个时间"）时倾向于不写 Due，而不是瞎猜
- v1 的 Web 面板模式已停止演进，SQLite 相关代码仅作参考

## License

MIT，见 [LICENSE](LICENSE)。
