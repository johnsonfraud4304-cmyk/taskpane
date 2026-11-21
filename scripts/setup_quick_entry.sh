#!/bin/bash
# setup_quick_entry.sh - 一键设置 TaskPane Quick Entry 完整流程
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

echo "============================================"
echo "TaskPane Quick Entry 一键设置"
echo "============================================"
echo ""

# 1. 检查 EventKit
echo "[1/4] 检查 EventKit..."
if ! python3 -c "import EventKit" 2>/dev/null; then
    echo "  装 pyobjc-framework-EventKit..."
    pip3 install pyobjc-framework-EventKit
fi
echo "  ✓ EventKit 已装"
echo ""

# 2. 启动 daemon（让它自动创建"快速提醒"和"TaskPane"列表）
echo "[2/4] 启动 daemon..."
echo "  ⚠️  如果弹授权框，请点 '好'"
python3 "$ROOT/daemon.py" start
sleep 3
echo ""

# 3. 检查 daemon 状态
echo "[3/4] 检查 daemon 状态..."
python3 "$ROOT/daemon.py" status
echo ""

# 4. 提示下一步
echo "[4/4] 设置 macOS Quick Entry 快捷键"
echo ""
echo "请手动设置快捷键:"
echo "  1. 系统设置 → 键盘 → 快捷键"
echo "  2. 左侧选 '提醒事项' 或 'Reminders'"
echo "  3. 启用 '显示快速提醒事项'（默认 Cmd+Ctrl+R）"
echo ""
echo "测试:"
echo "  1. 按 Cmd+Ctrl+R 弹出快速添加"
echo "  2. 输入消息原文，回车"
echo "  3. 看 Reminders → TaskPane 列表（应该有处理后的任务）"
echo ""
echo "看日志:"
echo "  tail -f logs/daemon.log"
echo ""
echo "停止 daemon:"
echo "  python3 $DIR/daemon.py stop"