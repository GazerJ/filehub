#!/usr/bin/env bash
set -u
OUT=/home/gazer/speed-diag3.txt
: > "$OUT"
B=http://127.0.0.1:8788

echo "===== A. 国内线路参照（清华/阿里云镜像）=====" >> "$OUT"
printf '清华 TUNA 下载 : ' >> "$OUT"
timeout 40 curl -s -o /dev/null -w '%{speed_download} B/s\n' --max-time 30 https://mirrors.tuna.tsinghua.edu.cn/ubuntu/ls-lR.gz >> "$OUT" 2>&1
printf '阿里云镜像下载 : ' >> "$OUT"
timeout 40 curl -s -o /dev/null -w '%{speed_download} B/s\n' --max-time 30 https://mirrors.aliyun.com/ubuntu/ls-lR.gz >> "$OUT" 2>&1

echo "===== B. 隧道单流 vs 4 并发（判断是“带宽封顶”还是“单流限速”）=====" >> "$OUT"
dd if=/dev/urandom of=/tmp/s100.bin bs=1M count=100 status=none
curl -s -X PUT --data-binary @/tmp/s100.bin "$B/api/upload?name=speedtest.bin" -o /tmp/sp.json
ID=$(python3 -c "import json;print(json.load(open('/tmp/sp.json'))['file']['id'])")
URL="https://file.gaoxiao.asia/d/$ID"

printf '单流           : ' >> "$OUT"
curl -s -o /dev/null -w '%{speed_download} B/s\n' "$URL" >> "$OUT"

printf '4 并发合计     : ' >> "$OUT"
for i in 1 2 3 4; do
  ( curl -s -o /dev/null --max-time 20 -w '%{speed_download}\n' "$URL" >> /tmp/par_$i.txt ) &
done
wait
python3 - <<'PY' >> "$OUT"
tot = 0
for i in (1, 2, 3, 4):
    try:
        tot += float(open('/tmp/par_%d.txt' % i).read().strip())
    except Exception:
        pass
print('%.0f B/s  (≈ %.1f MB/s, ≈ %.0f Mbps)' % (tot, tot / 1048576, tot * 8 / 1e6))
PY
rm -f /tmp/par_*.txt

echo "===== C. 隧道内上传测速（浏览器→CF→你这台机器）=====" >> "$OUT"
printf '公网上传 20MB  : ' >> "$OUT"
head -c 20000000 /dev/urandom > /tmp/u20.bin
timeout 90 curl -s -X PUT --data-binary @/tmp/u20.bin "https://file.gaoxiao.asia/api/upload?name=speedup.bin" -o /tmp/up.json -w '%{speed_upload} B/s\n' >> "$OUT" 2>&1
UPID=$(python3 -c "import json;print(json.load(open('/tmp/up.json')).get('file',{}).get('id',''))" 2>/dev/null)

echo "===== D. 清理 =====" >> "$OUT"
curl -s -X POST -H 'Content-Type: application/json' -d "{\"ids\":[\"$ID\",\"$UPID\"]}" "$B/api/delete" >> "$OUT"; echo >> "$OUT"
rm -f /tmp/s100.bin /tmp/u20.bin /tmp/sp.json /tmp/up.json
echo done
