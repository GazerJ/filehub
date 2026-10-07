#!/usr/bin/env bash
# 24 小时路径监控：每 5 分钟采样一次，用来判断劣化是"时段性拥塞"还是"路由长期变更"。
# 用法： nohup bash path_monitor.sh > /dev/null 2>&1 &
set -u
OUT="${OUT:-/home/gazer/filehub/tests/bench/results/path-monitor.csv}"
INTERVAL="${INTERVAL:-300}"
PROBE=/home/gazer/filehub/tests/bench/probe_latency.sh

[ -f "$OUT" ] || echo "time,cf_rtt_ms,ali_rtt_ms,google_rtt_ms,cf_loss_pct,tunnel_p50_ms,aliyun_Bps" > "$OUT"

rtt() { ping -c 4 -i 0.2 -W 2 "$1" 2>/dev/null | tail -1 | awk -F'/' '{print $5}'; }
loss() { ping -c 8 -i 0.2 -W 2 "$1" 2>/dev/null | tail -2 | head -1 | awk -F', ' '{print $3}' | awk '{print $1}' | tr -d '%'; }

while true; do
  cf=$(rtt 1.1.1.1)
  al=$(rtt 223.5.5.5)
  gg=$(rtt 8.8.8.8)
  ls=$(loss 1.1.1.1)
  rm -f /tmp/_pm.txt
  bash "$PROBE" /tmp/_pm.txt 12 https://file.gaoxiao.asia/healthz > /dev/null 2>&1
  tp=$(tail -1 /tmp/_pm.txt 2>/dev/null | sed -E 's/.*p50 ([0-9]+).*/\1/')
  # 只拉 3MB 区间，避免监控本身吃掉带宽
  sp=$(curl -s -o /dev/null -m 15 -r 0-3000000 -w '%{speed_download}' https://mirrors.aliyun.com/ubuntu/ls-lR.gz 2>/dev/null)
  echo "$(date '+%Y-%m-%d %H:%M'),${cf:-},${al:-},${gg:-},${ls:-},${tp:-},${sp:-}" >> "$OUT"
  sleep "$INTERVAL"
done
