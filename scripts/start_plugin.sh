#!/bin/bash
# start_plugin.sh - 启动 TaskPane 菜单栏 App（Apple Reminders 插件模式）
DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
cd "$ROOT"

# 检查 Ollama
if ! curl -s --noproxy '*' http://127.0.0.1:11434/ > /dev/null 2>&1; then
  echo "⚠️  Ollama 未运行，正在启动..."
  env -u CONDA_DEFAULT_ENV -u CONDA_PREFIX -u CONDA_SHLVL ollama serve > /tmp/ollama_taskpane.log 2>&1 &
  sleep 3
fi

# 环境检查
echo "TaskPane - Apple Reminders 插件模式"
echo "===================================="
python3 taskpane_plugin.py check
echo ""

# 启动菜单栏 App
echo "启动菜单栏 App..."
exec python3 taskpane_menubar.py