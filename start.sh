#!/usr/bin/env bash
# 启动「文件中转站」：默认监听 0.0.0.0:8788，上传的文件保留 7 天。
#   PORT=9000 TTL_DAYS=7 MAX_MB=4096 ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8788}"
TTL_DAYS="${TTL_DAYS:-7}"
MAX_MB="${MAX_MB:-2048}"
PIDFILE="data/filehub.pid"
LOG="data/server.log"

mkdir -p data/blobs

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "已经在运行（PID $(cat "$PIDFILE")）。要重启请先执行 ./stop.sh"
  exit 0
fi

setsid nohup python3 -u server.py --host 0.0.0.0 --port "$PORT" \
  --ttl-days "$TTL_DAYS" --max-mb "$MAX_MB" --quiet >> "$LOG" 2>&1 < /dev/null &
echo $! > "$PIDFILE"

for _ in $(seq 1 40); do
  sleep 0.3
  if curl -sf "http://127.0.0.1:$PORT/healthz" > /dev/null 2>&1; then
    IP="$(python3 -c 'import server; ips = server.local_ipv4(); print(ips[0] if ips else "127.0.0.1")')"
    echo "已启动：PID $(cat "$PIDFILE")，有效期 $TTL_DAYS 天，单文件上限 ${MAX_MB} MB"
    echo "  电脑访问：      http://$IP:$PORT"
    echo "  手机扫码上传页：http://$IP:$PORT/m"
    echo "  日志：$LOG"
    exit 0
  fi
done

echo "启动失败，日志最后几行："
tail -20 "$LOG" || true
exit 1
