#!/usr/bin/env bash
# 查看「文件中转站」运行状态与文件列表。
set -uo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8788}"
PIDFILE="data/filehub.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "进程：运行中（PID $(cat "$PIDFILE")）"
else
  echo "进程：未运行"
fi

if curl -sf "http://127.0.0.1:$PORT/healthz" > /dev/null 2>&1; then
  echo "端口：$PORT 可访问"
  curl -s "http://127.0.0.1:$PORT/api/files" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('文件：%d 个' % d['count'])
for f in d['files'][:15]:
    days = f['remaining'] // 86400
    print('  - %-40s %10d 字节  剩 %d 天' % (f['name'][:38], f['size'], days))
"
else
  echo "端口：$PORT 无响应"
fi

echo "数据占用：$(du -sh data 2>/dev/null | cut -f1)"
