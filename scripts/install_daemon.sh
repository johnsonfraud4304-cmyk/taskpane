#!/bin/bash
# install_daemon.sh - 安装 TaskPane daemon 为系统服务（开机自启）
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "TaskPane Daemon 系统服务安装"
echo "============================================"
echo ""

# 1. 创建 LaunchAgent plist
PLIST="$HOME/Library/LaunchAgents/com.taskpane.daemon.plist"
mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$ROOT/logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.taskpane.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$DIR/daemon.py</string>
        <string>run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$ROOT/logs/daemon.out.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT/logs/daemon.err.log</string>
</dict>
</plist>
EOF

echo "✅ 创建 LaunchAgent: $PLIST"
echo ""

# 2. 卸载旧的
launchctl unload "$PLIST" 2>/dev/null

# 3. 加载
launchctl load "$PLIST"
if [ $? -eq 0 ]; then
    echo "✅ LaunchAgent 加载成功"
else
    echo "❌ 加载失败"
    exit 1
fi
echo ""

# 4. 启动
launchctl start com.taskpane.daemon
sleep 2

# 5. 检查状态
echo "Daemon 状态:"
launchctl list | grep taskpane
echo ""

# 6. 看日志
echo "日志位置: $ROOT/logs/daemon.log"
echo ""
echo "卸载方法:"
echo "  launchctl unload $PLIST"
echo "  rm $PLIST"