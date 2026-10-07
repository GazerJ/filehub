#!/usr/bin/env bash
# 停止「文件中转站」。
set -uo pipefail
cd "$(dirname "$0")"
PIDFILE="data/filehub.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.2; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
    echo "已停止（PID $PID）"
  else
    echo "进程不存在，清理 pid 文件"
  fi
  rm -f "$PIDFILE"
else
  PIDS="$(pgrep -f 'python3 -u server.py' || true)"
  if [ -n "$PIDS" ]; then
    # shellcheck disable=SC2086
    kill $PIDS && echo "已停止：$PIDS"
  else
    echo "没有在运行的中转站进程"
  fi
fi
