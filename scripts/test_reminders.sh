#!/bin/bash
# test_reminders.sh - 在 Terminal 直接测试 Apple Reminders 集成
# 你需要在 Terminal（不是 sandbox shell）跑这个脚本
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

echo "=========================================="
echo "TaskPane Apple Reminders 测试"
echo "=========================================="
echo

# 1. 检查工具
echo "[1/4] 检查工具..."
python3 reminders_sync.py check
echo

# 2. 写测试 reminder
echo "[2/4] 创建测试 reminder (会触发 TCC 权限对话框)..."
TEST_SCRIPT=$(cat << 'EOF'
tell application "Reminders"
    set newRem to make new reminder at end of default list
    set name of newRem to "TaskPane Test Reminder (可删除)"
    return "✓ Created: " & name of newRem
end tell
EOF
)

osascript -e "$TEST_SCRIPT" 2>&1
echo

if [ $? -ne 0 ]; then
    echo "⚠️  首次运行需要授权 AppleScript 调用 Reminders"
    echo "请在弹出的系统对话框中点 'OK' / '允许'"
    echo "然后再跑此脚本"
    exit 1
fi

# 3. 验证
echo "[3/4] 列出当前 reminders..."
osascript -e 'tell application "Reminders" to return name of every reminder' 2>&1 | tr ',' '\n' | head -10
echo

# 4. 同步 TaskPane 任务
echo "[4/4] 同步 TaskPane 任务到 Reminders..."
python3 reminders_sync.py sync 2>&1
echo

echo "=========================================="
echo "打开 Reminders App 看看 TaskPane 列表里是否有任务"
echo "=========================================="