#!/usr/bin/env bash
set -u
OUT="${1:-/home/gazer/lat-diag.txt}"
: > "$OUT"

echo "===== 1. 到 CF 边缘的 RTT / 抖动 / 丢包（50 包）=====" >> "$OUT"
ping -c 50 -i 0.2 -W 2 1.1.1.1 2>&1 | tail -3 >> "$OUT"

echo "===== 2. 隧道小请求延迟分布（code-server 的体感来源）=====" >> "$OUT"
echo "--- file.gaoxiao.asia/healthz，20 次 ---" >> "$OUT"
for i in $(seq 1 20); do
  curl -s -o /dev/null -w '%{time_total}\n' https://file.gaoxiao.asia/healthz
done | python3 -c "
import sys
v = sorted(float(x) * 1000 for x in sys.stdin if x.strip())
n = len(v)
print('min %.0f ms | p50 %.0f ms | p90 %.0f ms | max %.0f ms | 抖动(max-min) %.0f ms' % (v[0], v[n//2], v[int(n*0.9)], v[-1], v[-1]-v[0]))
" >> "$OUT" 2>&1

echo "===== 3. TLS/HTTP2 握手分解（一次完整请求各阶段耗时）=====" >> "$OUT"
curl -s -o /dev/null -w 'DNS %{time_namelookup}s | TCP %{time_connect}s | TLS %{time_appconnect}s | 首字节 %{time_starttransfer}s | 总计 %{time_total}s\n' https://file.gaoxiao.asia/healthz >> "$OUT" 2>&1
curl -s -o /dev/null -w 'HTTP/2 复用后第二次: TCP %{time_connect}s | TLS %{time_appconnect}s | 首字节 %{time_starttransfer}s\n' https://file.gaoxiao.asia/healthz >> "$OUT" 2>&1

echo "===== 4. code-server 源站本机响应 =====" >> "$OUT"
ss -ltn | grep -E '17777' >> "$OUT" || echo "17777 未监听" >> "$OUT"
curl -sk -o /dev/null -w '本机 code-server: TCP %{time_connect}s TLS %{time_appconnect}s 首字节 %{time_starttransfer}s HTTP %{http_code}\n' https://127.0.0.1:17777/ >> "$OUT" 2>&1

echo "===== 5. 同一个域名解析到哪些 CF 节点（客户端会就近选，可能选的不是香港）=====" >> "$OUT"
for h in file.gaoxiao.asia softmatter.gaoxiao.asia dsh.gaoxiao.asia; do
  printf '%s -> ' "$h" >> "$OUT"; getent ahostsv4 "$h" | awk '{print $1}' | sort -u | tr '\n' ' ' >> "$OUT"; echo >> "$OUT"
done

echo "===== 6. 隧道当前协议与连接数 =====" >> "$OUT"
grep -nE '^protocol|haConnections|edge-ip-version|region' /home/gazer/.cloudflared/config-docker.yml >> "$OUT" 2>&1
docker logs cf-tunnel 2>&1 | grep -c 'Registered tunnel connection' >> "$OUT"
docker logs cf-tunnel 2>&1 | grep 'Registered tunnel connection' | tail -4 | sed 's/.*location=/location=/' >> "$OUT"

echo "===== 7. 本机是否跑着 clash/代理（浏览器可能被它代理，路径被拉长）=====" >> "$OUT"
ss -ltnp 2>/dev/null | grep -E ':(7890|7891|7892|1080|1087|8889|9090)\b' >> "$OUT" || echo '本机未监听常见代理端口' >> "$OUT"

echo done
