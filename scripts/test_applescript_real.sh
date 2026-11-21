#!/bin/bash
# test_applescript_real.sh - 在你的 Terminal 真实测试 Apple Reminders 集成
# 跑这个脚本会：
# 1. 测 osascript 是否能调 Reminders（首次会弹 TCC 授权框）
# 2. 写一个真实的测试 Reminder
# 3. 验证 Reminders App 是否显示
# 4. 跑 taskpane_plugin.py parse_to_reminder 真实版

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

echo "============================================"
echo "TaskPane - Apple Reminders 真实测试"
echo "============================================"
echo ""

# Step 1: 检查环境
echo "[1/4] 检查环境..."
if ! command -v osascript &> /dev/null; then
    echo "❌ osascript 未找到"
    exit 1
fi
echo "  ✓ osascript: $(which osascript)"

if ! curl -s --noproxy '*' http://127.0.0.1:11434/ > /dev/null 2>&1; then
    echo "❌ Ollama 未运行 (启动: ollama serve)"
    exit 1
fi
echo "  ✓ Ollama: running"
echo ""

# Step 2: 测试 osascript → Reminders 访问（首次会弹 TCC 对话框）
echo "[2/4] 测试 osascript 访问 Reminders..."
echo "      ⚠️  首次会弹 macOS 权限对话框，请点 '好'"
echo ""

osascript <<'EOF' 2>&1
tell application "Reminders"
    return name of every list
end tell
EOF

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ osascript 访问 Reminders 失败"
    echo ""
    echo "解决方法（任选一）:"
    echo "  方案 A: 在'系统设置 → 隐私与安全性 → 自动化'"
    echo "         找到 Terminal 或 osascript，允许控制 Reminders"
    echo ""
    echo "  方案 B: 手动打开 Reminders App，然后回到 Terminal 重新跑本脚本"
    echo ""
    echo "  方案 C: 直接用菜单栏 App 触发（rumps 会用相同 osascript）"
    echo ""
    read -p "按 Enter 继续测试（已授权则继续，否则会失败）..."
fi
echo ""

# Step 3: 创建 TaskPane 列表（如果不存在）
echo "[3/4] 确保 TaskPane 列表存在..."
osascript <<'EOF' 2>&1
tell application "Reminders"
    if not (exists list "TaskPane") then
        make new list with properties {name:"TaskPane"}
        return "created"
    else
        return "exists"
    end if
end tell
EOF
echo ""

# Step 4: 跑 taskpane_plugin 真实版
echo "[4/4] 跑 taskpane_plugin 真实端到端测试..."
echo ""

test_messages=(
    "@小王 紧急！明天下班前提交Q3财报分析给李总"
    "帮我查一下 600519 的最新股价"
    "周末前把那个文档改了"
    "明天 3 点开会讨论 Q4 方向"
)

count=0
for msg in "${test_messages[@]}"; do
    echo ">>> $msg"
    if python3 "$ROOT/taskpane_plugin.py" add "$msg" 2>&1; then
        count=$((count + 1))
    fi
    echo ""
done

echo "============================================"
echo "✅ 测试完成: $count/${#test_messages[@]} 条成功"
echo "============================================"
echo ""
echo "下一步:"
echo "  1. 打开 Reminders App (Cmd+Space, 输入 'Reminders')"
echo "  2. 看左侧 'TaskPane' 列表"
echo "  3. 应该看到 $count 条新提醒"
echo ""
echo "如果没看到:"
echo "  - Cmd+R 刷新"
echo "  - 或在 Reminders 菜单 → 视图 → 显示所有提醒"