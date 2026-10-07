#!/usr/bin/env bash
# 在【你自己的电脑】上运行（不是服务器），用来判断 code-server 卡在哪一段。
# 用法： bash client_check.sh
set -u

CF_IP="104.21.26.4"          # file.gaoxiao.asia / softmatter.gaoxiao.asia 的 Cloudflare anycast 地址
FRP_HOST=""                  # ← 填你樱花 frp 节点的域名或 IP，用来对比
URL="https://file.gaoxiao.asia/healthz"

echo "===== 1. 到 Cloudflare 边缘的延迟/抖动 ====="
ping -c 10 "$CF_IP" 2>&1 | tail -3

if [ -n "$FRP_HOST" ]; then
  echo "===== 2. 到 frp 节点的延迟/抖动（对比用）====="
  ping -c 10 "$FRP_HOST" 2>&1 | tail -3
else
  echo "===== 2. frp 对比：请把 FRP_HOST 填上再跑（樱花 frp 的节点地址）====="
fi

echo "===== 3. 一次完整请求的各阶段耗时（走 CF 隧道）====="
curl -s -o /dev/null -w 'DNS %{time_namelookup}s | TCP %{time_connect}s | TLS %{time_appconnect}s | 首字节 %{time_starttransfer}s | 总计 %{time_total}s\n' "$URL"

echo "===== 4. 热连接延迟（30 个复用连接请求，接近浏览器实际感受）====="
CFG=$(mktemp)
for _ in $(seq 1 30); do printf 'url = "%s"\noutput = "/dev/null"\n' "$URL" >> "$CFG"; done
curl -s -K "$CFG" -w '%{time_total}\n' > /tmp/_cc.txt 2>/dev/null
rm -f "$CFG"
python3 - <<'PY' 2>/dev/null || sort -n /tmp/_cc.txt | awk 'NR==1{min=$1} {a[NR]=$1} END{printf "min %.0f ms | p50 %.0f ms | max %.0f ms\n", min*1000, a[int(NR/2)]*1000, a[NR]*1000}'
import sys
v = sorted(float(x) * 1000 for x in open('/tmp/_cc.txt') if x.strip())
print('min %.0f ms | p50 %.0f ms | p90 %.0f ms | max %.0f ms' % (v[0], v[len(v)//2], v[int(len(v)*0.9)], v[-1]))
PY

echo "===== 5. 你本机有没有走代理（Clash 等）====="
env | grep -iE '_proxy|PROXY' || echo "(环境变量里没有代理)"
case "$(uname -s)" in
  Darwin) echo "--- macOS 系统代理 ---"; scutil --proxy | grep -iE 'HTTPEnable|HTTPPort|SOCKSEnable|SOCKSPort' ;;
  *)      echo "--- Linux ---"; gsettings get org.gnome.system.proxy mode 2>/dev/null || echo "(无法读取)" ;;
esac

echo
echo "判读方法："
echo "  第 1 项 ~30ms 且第 4 项 p50 ~60-90ms  → 路径本身正常，问题多半在客户端代理（第 5 项）或 Access 重认证"
echo "  第 1 项 100ms+ 或第 4 项 p50 300ms+   → 客户端到 CF 边缘那一段绕路了（国际出口 / 代理）"
echo "  第 2 项明显小于第 1 项                → 交互式应用走 frp 会明显更跟手，建议分流"
