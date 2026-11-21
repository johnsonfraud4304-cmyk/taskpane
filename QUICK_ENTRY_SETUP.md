# TaskPane Quick Entry 设置指南

## 🎯 目标
按 `Cmd+Ctrl+R` 弹出 Reminders 快速添加 → 输入原文 → 自动 AI 解析 → TaskPane 列表生成格式化任务

## 1️⃣ 启用 macOS Quick Entry

1. 打开 **系统设置** → **键盘** → **快捷键**
2. 左侧找 **"焦点中的提醒事项"** 或 **"Reminders"**
3. 启用 **"显示快速提醒事项"** 快捷键（默认 `Cmd+Ctrl+R`）

⚠️ 如果没看到这个选项，**升级到 macOS 13+** 或更新 Reminders App

## 2️⃣ 准备 Reminders 列表

1. 打开 **Reminders App**
2. 确保有两个列表：
   - **TaskPane**（你已有的，处理后的任务存这里）
   - **快速提醒**（macOS Quick Entry 默认会创建，**别删**）

## 3️⃣ 启动 TaskPane Daemon

```bash
# 在 Terminal 跑一次（确认环境 OK）
python3 scripts/taskpane_plugin.py check

# 启动后台 daemon
python3 scripts/daemon.py start

# 查看状态
python3 scripts/daemon.py status

# 看实时日志
tail -f scripts/logs/daemon.log

# 停止 daemon
python3 scripts/daemon.py stop
```

## 4️⃣ 测试完整流程

```bash
# 1. 启动 daemon（前台模式看日志）
python3 scripts/daemon.py run
```

然后：
1. 在任何地方按 `Cmd+Ctrl+R`
2. 弹出 Reminders 快速添加窗口
3. 输入：`@小王 紧急！明天下班前提交Q3财报分析给李总`
4. 回车保存
5. **看 daemon 日志**会显示处理过程
6. 打开 Reminders → TaskPane 列表 → 应该有 🔥 [P0] 提交Q3财报给李总

## 5️⃣ 日常使用

- **按 Cmd+Ctrl+R** → 输入消息 → 回车
- Daemon 后台运行，自动处理
- 3-5 秒后看 Reminders → TaskPane 列表

## 6️⃣ 故障排除

**Daemon 显示 "授权失败"**：
```bash
# 重跑授权
python3 scripts/taskpane_plugin.py check
# 弹框点"好"
```

**Cmd+Ctrl+R 没反应**：
- 系统设置 → 键盘 → 快捷键 → 确认启用
- 试用 `Cmd+Ctrl+Space`（系统默认）

**Daemon 看不到新 reminder**：
- 检查 Reminders App 是否运行
- 重启 daemon: `python3 scripts/daemon.py restart`

**Daemon 启动后立刻退出**：
- 看日志: `tail -f scripts/logs/daemon.log`
- 可能 "快速提醒"列表不存在 — 在 Reminders App 创建