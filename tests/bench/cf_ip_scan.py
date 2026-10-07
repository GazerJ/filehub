"""并发扫描 Cloudflare anycast 段的 TCP 连接延迟，找最快入口。
   测 443（访客侧边缘）与 7844（Argo Tunnel 端口）。结果写 CSV。"""
import concurrent.futures as cf
import csv, socket, sys, time

CANDS = [
    ('104.21.26.4', 'zone-当前'), ('172.67.134.248', 'zone-当前'),
    ('198.41.192.37', 'tunnel-edge'), ('198.41.192.7', 'tunnel-edge'),
    ('198.41.200.43', 'tunnel-edge'), ('198.41.192.1', 'tunnel-段'),
    ('198.41.200.1', 'tunnel-段'), ('198.41.128.1', 'CF-198.41.128'),
    ('104.16.0.1', 'CF-104.16'), ('104.17.0.1', 'CF-104.17'),
    ('104.18.0.1', 'CF-104.18'), ('104.19.0.1', 'CF-104.19'),
    ('104.20.0.1', 'CF-104.20'), ('104.22.0.1', 'CF-104.22'),
    ('104.23.0.1', 'CF-104.23'), ('104.24.0.1', 'CF-104.24'),
    ('104.25.0.1', 'CF-104.25'), ('104.26.0.1', 'CF-104.26'),
    ('104.27.0.1', 'CF-104.27'), ('172.64.0.1', 'CF-172.64'),
    ('172.65.0.1', 'CF-172.65'), ('172.66.0.1', 'CF-172.66'),
    ('172.68.0.1', 'CF-172.68'), ('172.69.0.1', 'CF-172.69'),
    ('162.159.0.1', 'CF-162.159'), ('162.159.36.1', 'CF-162.159.36'),
    ('162.159.46.1', 'CF-162.159.46'), ('162.159.200.1', 'CF-162.159.200'),
    ('188.114.96.1', 'CF-188.114.96'), ('188.114.97.1', 'CF-188.114.97'),
    ('188.114.98.1', 'CF-188.114.98'), ('190.93.240.1', 'CF-190.93.240'),
    ('190.93.241.1', 'CF-190.93.241'), ('173.245.48.1', 'CF-173.245.48'),
    ('141.101.64.1', 'CF-141.101.64'), ('141.101.65.1', 'CF-141.101.65'),
    ('108.162.192.1', 'CF-108.162.192'), ('108.162.193.1', 'CF-108.162.193'),
    ('103.21.244.1', 'CF-103.21.244'), ('103.22.200.1', 'CF-103.22.200'),
    ('131.0.72.1', 'CF-131.0.72'),
]

def tcp_ms(ip, port, tries=2, timeout=1.5):
    best = None
    for _ in range(tries):
        s = socket.socket()
        s.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            s.connect((ip, port))
            dt = (time.perf_counter() - t0) * 1000
            best = dt if best is None else min(best, dt)
        except Exception:
            pass
        finally:
            s.close()
    return best

def probe(item):
    ip, tag = item
    return ip, tag, tcp_ms(ip, 443), tcp_ms(ip, 7844)

rows = []
with cf.ThreadPoolExecutor(max_workers=20) as ex:
    for r in ex.map(probe, CANDS):
        rows.append(r)

out = '/home/gazer/filehub/tests/bench/results/cf-ip-scan.csv'
with open(out, 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['ip', 'tag', 'tcp443_ms', 'tcp7844_ms'])
    for ip, tag, a, b in sorted(rows, key=lambda r: (r[2] is None, r[2] or 9e9)):
        w.writerow([ip, tag, '' if a is None else round(a, 1), '' if b is None else round(b, 1)])

lines = []
lines.append('%-18s %-16s %10s %10s' % ('IP', '备注', '443(ms)', '7844(ms)'))
for ip, tag, a, b in sorted(rows, key=lambda r: (r[2] is None, r[2] or 9e9)):
    lines.append('%-18s %-16s %10s %10s' % (ip, tag, ('%.1f' % a) if a else 'x', ('%.1f' % b) if b else 'x'))
ok443 = sorted([r for r in rows if r[2]], key=lambda r: r[2])
ok7844 = sorted([r for r in rows if r[3]], key=lambda r: r[3])
lines.append('')
lines.append('443 最快 6 个: ' + str([(r[0], round(r[2])) for r in ok443[:6]]))
lines.append('7844 最快 6 个: ' + str([(r[0], round(r[3])) for r in ok7844[:6]]))
lines.append('443 最慢 3 个: ' + str([(r[0], round(r[2])) for r in ok443[-3:]]))
open('/home/gazer/ipscan.txt', 'w').write('\n'.join(lines))
print('\n'.join(lines))
