#!/usr/bin/env bash
# 分段测速：磁盘/本机 → 局域网 → 公网隧道
set -u
B=http://127.0.0.1:8788
OUT=/home/gazer/speed-diag.txt
: > "$OUT"

echo "===== 1. 网卡与链路 =====" >> "$OUT"
cat /sys/class/net/enp1s0/speed 2>/dev/null | sed 's/^/网卡速率(Mb\/s): /' >> "$OUT"
ip -brief addr show enp1s0 >> "$OUT" 2>&1
echo "默认路由:" >> "$OUT"; ip route | head -3 >> "$OUT"

echo "===== 2. 准备 100MB 测试文件 =====" >> "$OUT"
dd if=/dev/urandom of=/tmp/speed100.bin bs=1M count=100 status=none
curl -s -X PUT --data-binary @/tmp/speed100.bin "$B/api/upload?name=speedtest.bin" -o /tmp/sp.json
ID=$(python3 -c "import json;print(json.load(open('/tmp/sp.json'))['file']['id'])")
echo "文件 id=$ID" >> "$OUT"

echo "===== 3. 分段下载测速（数字越大越快）=====" >> "$OUT"
printf '本机回环  : ' >> "$OUT"
curl -s -o /dev/null -w '%{speed_download} B/s  (%{time_total}s)\n' "$B/d/$ID" >> "$OUT"
printf '局域网    : ' >> "$OUT"
curl -s -o /dev/null -w '%{speed_download} B/s  (%{time_total}s)\n' "http://10.168.0.105:8788/d/$ID" >> "$OUT"
printf '公网隧道  : ' >> "$OUT"
curl -s -o /dev/null -w '%{speed_download} B/s  (%{time_total}s)\n' "https://file.gaoxiao.asia/d/$ID" >> "$OUT"

echo "===== 4. 走隧道时的 CPU 占用 =====" >> "$OUT"
( curl -s -o /dev/null "https://file.gaoxiao.asia/d/$ID" & sleep 3; docker stats --no-stream --format '{{.Name}} CPU={{.CPUPerc}} MEM={{.MemUsage}} NET={{.NetIO}}' cf-tunnel >> "$OUT" 2>&1; wait ) 

echo "===== 5. 隧道连接到了哪个 Cloudflare 边缘 =====" >> "$OUT"
docker logs cf-tunnel 2>&1 | grep -iE "Registered tunnel connection|Initial protocol|edge" | tail -8 >> "$OUT" 2>&1
echo "config 里的协议:" >> "$OUT"; grep -E "^protocol|^edge|^haConnections|region" /home/gazer/.cloudflared/config-docker.yml >> "$OUT" 2>&1
echo "容器启动命令:" >> "$OUT"; docker inspect cf-tunnel --format '{{.Config.Cmd}}' >> "$OUT" 2>&1

echo "===== 6. 到 Cloudflare 的往返延迟 =====" >> "$OUT"
ping -c 5 -W 2 1.1.1.1 2>&1 | tail -2 >> "$OUT"
ping -c 5 -W 2 104.16.132.229 2>&1 | tail -2 >> "$OUT"

echo "===== 7. 清理测试文件 =====" >> "$OUT"
curl -s -X POST -H 'Content-Type: application/json' -d "{\"ids\":[\"$ID\"]}" "$B/api/delete" >> "$OUT"; echo >> "$OUT"
rm -f /tmp/speed100.bin /tmp/sp.json
echo "done"
