#!/bin/bash
# wait_for_qwen7b.sh - 等待 qwen2.5:7b 下载完成（最多 30 分钟）
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG=/tmp/qwen7b_pull.log

echo "🔍 检查 qwen2.5:7b 状态..."
if env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL ollama list 2>/dev/null | grep -q "qwen2.5:7b"; then
  echo "✅ qwen2.5:7b 已安装！"
  exit 0
fi

echo "📥 qwen2.5:7b 未安装，启动下载（后台，~25 分钟）..."

# 杀掉旧 pull 进程
pkill -f "ollama pull qwen2.5:7b" 2>/dev/null
sleep 1

# detach 到 nohup
nohup env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL \
  ollama pull qwen2.5:7b > $LOG 2>&1 < /dev/null &
PID=$!
disown $PID 2>/dev/null
echo "📌 后台 PID: $PID"
echo "📊 监控日志: $LOG"
echo ""

# 监控循环
for i in $(seq 1 60); do
  sleep 30
  if env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL ollama list 2>/dev/null | grep -q "qwen2.5:7b"; then
    echo "✅ 下载完成！"
    tail -3 $LOG
    exit 0
  fi
  if [ -f $LOG ]; then
    PROGRESS=$(tail -20 $LOG | grep -oE "[0-9]+%" | tail -1)
    SIZE=$(tail -20 $LOG | grep -oE "[0-9]+ MB/[0-9.]+ GB" | tail -1)
    echo "  [$i/60] $PROGRESS  $SIZE"
  else
    echo "  [$i/60] 等待日志..."
  fi

  # 检查进程
  if ! pgrep -f "ollama pull qwen2.5:7b" > /dev/null; then
    echo "⚠️  进程已退出，查看日志："
    tail -10 $LOG
    exit 1
  fi
done

echo "⏰ 30 分钟到，请重跑此脚本继续等待"