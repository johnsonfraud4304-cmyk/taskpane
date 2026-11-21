#!/bin/bash
# TaskPane 启动脚本

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

# 检查 Ollama
if ! curl -s --noproxy '*' http://127.0.0.1:11434/ > /dev/null 2>&1; then
  echo "⚠️  Ollama 未运行，正在启动..."
  ollama serve > /tmp/ollama_taskpane.log 2>&1 &
  sleep 3
fi

# 默认模型：qwen2.5:7b（中文最强 + 4.7GB + M3 友好）
# 也可设为: qwen2.5:3b（更快）、qwen2:0.5b（最轻）、deepseek-r1:8b（推理强）
MODEL=${TASKPANE_MODEL:-qwen2.5:7b}

# 检查模型
if ! env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL ollama list 2>/dev/null | grep -qE "^${MODEL}[[:space:]]"; then
  echo "📥 下载模型 ${MODEL}（首次，4.7GB，约 5 分钟）..."
  env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL ollama pull ${MODEL}
fi

export TASKPANE_MODEL=${MODEL}
echo "✅ TaskPane 启动中（模型: ${MODEL}）"
# 启动 TaskPane
exec python3 taskpane_app.py