"""给 Access 应用延长会话 + 为静态资源前缀添加 bypass 应用（幂等）。
   用法： python3 cf_access_bypass.py [--dry-run]
"""
import json, re, sys, urllib.request, urllib.error

DRY = '--dry-run' in sys.argv

env = {}
for line in open('/home/gazer/.config/ssl-auto/cloudflare-access.env'):
    m = re.match(r'export\s+(\w+)="?([^"\n]+)"?', line.strip())
    if m:
        env[m.group(1)] = m.group(2)
TOKEN, ACCT = env['CF_ACCESS_API_TOKEN'], env['CF_ACCOUNT_ID']

# 只放行“确定是静态资源”的前缀；绝不碰 /api /proxy /vscode-remote-resource 这类能读文件或转发请求的路径
PLAN = {
    'softmatter.gaoxiao.asia': ['/static', '/manifest.json', '/favicon.ico'],
    'dsh.gaoxiao.asia':        ['/assets', '/plugins', '/favicon.svg', '/manifest.webmanifest'],
}
SESSION = '720h'   # 30 天，Cloudflare self-hosted 应用的上限

def api(path, method='GET', payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request('https://api.cloudflare.com/client/v4' + path, data=body, method=method,
                                 headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw[:300]}

s, d = api('/accounts/%s/access/apps?per_page=100' % ACCT)
apps = {a['domain']: a for a in (d.get('result') or [])}
print('现有应用:', list(apps.keys()))

# 1) 会话延长到 30 天
print()
print('=== 1. 会话时长 -> %s ===' % SESSION)
for domain, app in list(apps.items()):
    if app.get('session_duration') == SESSION:
        print('  %-32s 已是 %s，跳过' % (domain, SESSION))
        continue
    if DRY:
        print('  %-32s [dry-run] 将改为 %s（当前 %s）' % (domain, SESSION, app.get('session_duration')))
        continue
    body = {
        'name': app['name'], 'domain': app['domain'], 'type': app.get('type', 'self_hosted'),
        'session_duration': SESSION,
        'app_launcher_visible': app.get('app_launcher_visible', False),
        'auto_redirect_to_identity': app.get('auto_redirect_to_identity', False),
        'allowed_idps': app.get('allowed_idps') or [],
        'self_hosted_domains': app.get('self_hosted_domains') or [app['domain']],
    }
    s2, d2 = api('/accounts/%s/access/apps/%s' % (ACCT, app['id']), 'PUT', body)
    if s2 in (200, 201) and d2.get('success'):
        print('  %-32s -> %s  ✅' % (domain, d2['result'].get('session_duration')))
    else:
        print('  %-32s 失败 status=%s %s' % (domain, s2, json.dumps(d2.get('errors') or d2, ensure_ascii=False)[:200]))

# 2) 静态资源 bypass 应用
print()
print('=== 2. 静态资源 bypass ===')
for host, paths in PLAN.items():
    for p in paths:
        fqdn = host + p
        if fqdn in apps:
            print('  %-42s 已存在，跳过' % fqdn)
            continue
        if DRY:
            print('  %-42s [dry-run] 将创建 bypass 应用' % fqdn)
            continue
        payload = {
            'name': 'bypass-static-' + fqdn.replace('/', '_'),
            'domain': fqdn,
            'type': 'self_hosted',
            'session_duration': '24h',
            'app_launcher_visible': False,
            'auto_redirect_to_identity': False,
            'allowed_idps': [],
            'self_hosted_domains': [fqdn],
        }
        s3, d3 = api('/accounts/%s/access/apps' % ACCT, 'POST', payload)
        if not (s3 in (200, 201) and d3.get('success')):   # 创建成功返回 201
            print('  %-42s 创建失败 status=%s %s' % (fqdn, s3, json.dumps(d3.get('errors') or d3, ensure_ascii=False)[:250]))
            continue
        app_id = d3['result']['id']
        pol = {'name': 'bypass-static', 'decision': 'bypass', 'include': [{'everyone': {}}]}
        s4, d4 = api('/accounts/%s/access/apps/%s/policies' % (ACCT, app_id), 'POST', pol)
        ok = s4 in (200, 201) and d4.get('success')
        print('  %-42s 应用已建(id=%s) 策略=%s %s' % (fqdn, app_id[:8], 'bypass' if ok else '失败', '✅' if ok else json.dumps(d4.get('errors') or d4, ensure_ascii=False)[:180]))
