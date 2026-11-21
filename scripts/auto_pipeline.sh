#!/bin/bash
# auto_pipeline.sh - 一站式：等下载 → 测速 → 测准确率 → 优化 → 报告
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

echo "============================================="
echo "TaskPane Auto Pipeline"
echo "  1. 等 qwen2.5:7b 下载"
echo "  2. 测速"
echo "  3. 测准确率 (10 case)"
echo "  4. 调 prompt"
echo "  5. 报告"
echo "============================================="
echo

# 1. 等下载
echo "[1/5] 等待 qwen2.5:7b 下载完成..."
while true; do
  if env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL ollama list 2>/dev/null | grep -q "qwen2.5:7b"; then
    echo "✅ 下载完成"
    break
  fi
  PROGRESS=$(tail -50 /tmp/qwen7b_final.log 2>/dev/null | grep -oE "[0-9]+%" | tail -1)
  echo "  $PROGRESS  $(date +%H:%M:%S)"
  sleep 60
done
echo

# 2. 测速
echo "[2/5] 测速 qwen2.5:7b..."
env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL \
  curl -s -X POST http://127.0.0.1:11434/api/generate \
  -d '{"model":"qwen2.5:7b","prompt":"用一句话介绍你自己","stream":false}' \
  | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
evals = d.get('eval_count', 0)
dur = d.get('eval_duration', 1) / 1e9
print(f'  速度: {evals/dur:.1f} tok/s')
print(f'  响应: {d.get(\"response\", \"\")[:80]}')
"
echo

# 3. 测准确率
echo "[3/5] 测准确率 (10 个真实场景)..."
TASKPANE_MODEL=qwen2.5:7b \
  env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL \
  python3 prompt_optimizer.py qwen2.5:7b 2>&1 | tee /tmp/qwen7b_accuracy.log | tail -40
echo

# 4. 提取失败 case
echo "[4/5] 失败 case 分析..."
ACC=$(grep "准确率:" /tmp/qwen7b_accuracy.log | tail -1)
echo "  $ACC"

if echo "$ACC" | grep -q "100.0%"; then
  echo "  ✅ qwen2.5:7b 100% 准确率，不需要再调 prompt"
else
  echo "  ⚠️  qwen2.5:7b 需要 prompt 优化"
  echo "  查看 /tmp/qwen7b_accuracy.log 找失败 case"
fi
echo

# 5. 报告
echo "[5/5] 总结"
echo "============================================="
echo "✅ qwen2.5:7b 已就绪"
echo ""
echo "下一步："
echo "  1. 启动 TaskPane（自动用 qwen2.5:7b）: start.sh"
echo "  2. 打开面板: open http://127.0.0.1:8911"
echo "  3. 测试 Apple Reminders 集成: test_reminders.sh"
echo ""
echo "详细报告: /tmp/qwen7b_accuracy.log"
echo "============================================="