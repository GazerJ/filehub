#!/usr/bin/env bash
# 复用同一条连接连发 N 个小请求，测隧道交互延迟（贴近浏览器的真实行为）
# 用法: probe_latency.sh <输出文件> [请求数] [URL]
set -u
OUT="${1:-/home/gazer/probe.txt}"
N="${2:-30}"
URL="${3:-https://file.gaoxiao.asia/healthz}"
CFG=/tmp/probe_curl.cfg

python3 - "${CFG}" "${N}" "${URL}" <<'PY'
import sys
cfg, n, url = sys.argv[1], int(sys.argv[2]), sys.argv[3]
with open(cfg, 'w') as fh:
    for _ in range(n):
        fh.write('url = "%s"\noutput = "/dev/null"\n' % url)
PY

curl -s -K "$CFG" -w '%{time_total}\n' > /tmp/probe_raw.txt 2>/dev/null

python3 - "${OUT}" <<'PY'
import sys
path = sys.argv[1]
vals = sorted(float(x) * 1000 for x in open('/tmp/probe_raw.txt') if x.strip())
n = len(vals)
line = 'n=%d  min %.0f  p50 %.0f  p90 %.0f  max %.0f  (ms)' % (
    n, vals[0], vals[n // 2], vals[int(n * 0.9)], vals[-1]) if n else '无数据'
print(line)
open(path, 'a').write(line + '\n')
PY
