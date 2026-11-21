#!/bin/bash
# auto_test_when_ready.sh - 监控 + 下载完成自动测试
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

echo "🔍 监控 qwen2.5:7b 下载（最多 60 分钟）..."
echo "📊 每 30 秒检查一次"
echo ""

START_TIME=$(date +%s)
while true; do
  ELAPSED=$(( $(date +%s) - START_TIME ))
  if [ $ELAPSED -gt 3600 ]; then
    echo "⏰ 60 分钟到，请重跑此脚本"
    exit 1
  fi

  if env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL ollama list 2>/dev/null | grep -q "qwen2.5:7b"; then
    echo ""
    echo "✅ 下载完成！"
    MIN=$((ELAPSED / 60))
    SEC=$((ELAPSED % 60))
    echo "总耗时: ${MIN}分${SEC}秒"
    break
  fi

  # 进度
  PROGRESS=$(tail -50 /tmp/qwen7b_pull.log 2>/dev/null | grep -oE '[0-9]+%' | tail -1)
  SIZE=$(tail -50 /tmp/qwen7b_pull.log 2>/dev/null | grep -oE '[0-9]+ MB/[0-9.]+ GB' | tail -1)
  echo "  [${MIN}m${SEC}s] $PROGRESS  $SIZE"
  sleep 30
done

echo ""
echo "===== 测速 ====="
env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL \
  curl -s -X POST http://127.0.0.1:11434/api/generate \
  -d '{"model":"qwen2.5:7b","prompt":"用一句话介绍你自己","stream":false}' \
  | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
evals = d.get('eval_count', 0)
dur = d.get('eval_duration', 1) / 1e9
print(f'生成 tokens: {evals}')
print(f'耗时: {dur:.2f}s')
print(f'速度: {evals/dur:.1f} tok/s')
print(f'响应: {d.get("response", "")[:80]}')
"

echo ""
echo "===== 准确率测试 (10 个真实场景) ====="
TASKPANE_MODEL=qwen2.5:7b \
  env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL \
  python3 test_accuracy.py 2>&1 | tail -8
