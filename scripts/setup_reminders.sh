#!/bin/bash
# setup_reminders.sh - 一键创建 TaskPane 列表
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

echo "============================================"
echo "TaskPane Reminders 设置（EventKit 方式）"
echo "============================================"
echo ""

# 1. 检查 pyobjc
echo "[1/3] 检查 pyobjc-framework-EventKit..."
if ! python3 -c "import EventKit" 2>/dev/null; then
    echo "  装 pyobjc-framework-EventKit..."
    pip3 install pyobjc-framework-EventKit
    if [ $? -ne 0 ]; then
        echo "❌ 装失败"
        exit 1
    fi
fi
echo "  ✓ 已装"
echo ""

# 2. 初始化列表
echo "[2/3] 创建 TaskPane 列表..."
echo "      ⚠️  会弹授权框 'python3 想要访问 Reminders'"
echo "      ⚠️  请点 '好'"
echo ""
python3 "$DIR/setup_reminders.py" init
echo ""

# 3. 测试添加
echo "[3/3] 测试添加一条任务..."
python3 "$DIR/setup_reminders.py" add "@小王 紧急！明天下班前提交Q3财报分析给李总"
echo ""

echo "============================================"
echo "✅ 设置完成！"
echo "============================================"
echo ""
echo "下一步:"
echo "  1. 打开 Reminders App"
echo "  2. 按 Cmd+R 刷新"
echo "  3. 看左侧栏的 'TaskPane' 列表"
echo "  4. 应该有 1 条新提醒"
echo ""
echo "如果看不到:"
echo "  - 左侧栏底部 + → 检查 'TaskPane' 列表"
echo "  - 文件 → 显示所有提醒"
echo ""
echo "后续使用:"
echo "  python3 scripts/setup_reminders.py add '你的消息'"
echo "  python3 scripts/setup_reminders.py list"
