"""对比不同 CDN / 云厂商的 TCP 连接延迟，判断"绕开 Cloudflare"是否可行。"""
import concurrent.futures as cf
import socket, time

TARGETS = [
    ('www.apple.com', 'Apple/Akamai'),
    ('www.microsoft.com', 'Microsoft/Azure'),
    ('www.amazon.com', 'Amazon/AWS'),
    ('github.com', 'GitHub/Fastly'),
    ('www.cloudflare.com', 'Cloudflare'),
    ('dash.cloudflare.com', 'Cloudflare'),
    ('one.one.one.one', 'Cloudflare-1.1.1.1'),
    ('www.google.com', 'Google'),
    ('mirrors.aliyun.com', '阿里云-国内'),
    ('mirrors.cloud.tencent.com', '腾讯云-国内'),
    ('cdn.jsdelivr.net', 'jsDelivr/Fastly'),
    ('bunnycdn.com', 'Bunny.net'),
    ('www.fastly.com', 'Fastly'),
    ('www.akamai.com', 'Akamai'),
    ('www.digitalocean.com', 'DigitalOcean'),
    ('www.vultr.com', 'Vultr'),
    ('www.cloudflare-cn.com', 'CF 中国合作'),
]

def tcp(host, port=443, tries=3, timeout=3.0):
    try:
        ip = socket.gethostbyname(host)
    except Exception:
        return None, None
    best = None
    for _ in range(tries):
        s = socket.socket(); s.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            s.connect((ip, port))
            dt = (time.perf_counter() - t0) * 1000
            best = dt if best is None else min(best, dt)
        except Exception:
            pass
        finally:
            s.close()
    return ip, best

def probe(t):
    host, tag = t
    ip, ms = tcp(host)
    return host, tag, ip, ms

rows = []
with cf.ThreadPoolExecutor(max_workers=16) as ex:
    for r in ex.map(probe, TARGETS):
        rows.append(r)

out = []
out.append('%-26s %-16s %-16s %8s' % ('域名', '厂商', 'IP', '443(ms)'))
out.append('-' * 72)
for host, tag, ip, ms in sorted(rows, key=lambda r: (r[3] is None, r[3] or 9e9)):
    out.append('%-26s %-16s %-16s %8s' % (host, tag, ip or '-', ('%.1f' % ms) if ms else '超时'))
txt = '\n'.join(out)
open('/home/gazer/cdn-cmp.txt', 'w').write(txt)
print(txt)
