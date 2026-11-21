#!/bin/bash
# test_qwen7b.sh - qwen2.5:7b 下载完后自动测试准确率
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

# 检查模型
if ! env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL ollama list 2>/dev/null | grep -q "qwen2.5:7b"; then
  echo "❌ qwen2.5:7b 还没下载完，请先跑 wait_for_qwen7b.sh"
  exit 1
fi

echo "✅ qwen2.5:7b 已就绪"
echo ""
echo "===== 速度测试 ====="
START=$(date +%s)
env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL \
  curl -s -X POST http://127.0.0.1:11434/api/generate \
  -d '{"model":"qwen2.5:7b","prompt":"用一句话介绍你自己","stream":false}' \
  | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
evals = d.get('eval_count', 0)
dur = d.get('eval_duration', 1) / 1e9  # to seconds
print(f'生成 tokens: {evals}')
print(f'耗时: {dur:.2f}s')
print(f'速度: {evals/dur:.1f} tok/s')
"
END=$(date +%s)
echo "总耗时: $((END-START))s"
echo ""
echo "===== 准确率测试 (10 个真实场景) ====="
TASKPANE_MODEL=qwen2.5:7b \
  env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL \
  python3 test_accuracy.py 2>&1 | tail -8