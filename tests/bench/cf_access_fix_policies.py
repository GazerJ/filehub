"""给已创建的 bypass-static-* 应用补上 bypass 策略（幂等）。"""
import json, re, urllib.request, urllib.error

env = {}
for line in open('/home/gazer/.config/ssl-auto/cloudflare-access.env'):
    m = re.match(r'export\s+(\w+)="?([^"\n]+)"?', line.strip())
    if m:
        env[m.group(1)] = m.group(2)
TOKEN, ACCT = env['CF_ACCESS_API_TOKEN'], env['CF_ACCOUNT_ID']

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
apps = d.get('result') or []
bypass_apps = [a for a in apps if a.get('domain', '').count('/') == 1]   # host/path 形式
print('带路径的 bypass 应用数量:', len(bypass_apps))
print()
for a in sorted(bypass_apps, key=lambda x: x['domain']):
    host, path = a['domain'].split('/', 1)
    s2, d2 = api('/accounts/%s/access/apps/%s/policies?per_page=100' % (ACCT, a['id']))
    existing = d2.get('result') or []
    if any(p.get('decision') == 'bypass' for p in existing):
        print('  %-42s 策略已存在 (%s)' % (a['domain'], [p.get('name') for p in existing]))
        continue
    pol = {'name': 'bypass-static', 'decision': 'bypass', 'include': [{'everyone': {}}]}
    s3, d3 = api('/accounts/%s/access/apps/%s/policies' % (ACCT, a['id']), 'POST', pol)
    ok = s3 in (200, 201) and d3.get('success')
    print('  %-42s 策略创建 status=%s %s' % (a['domain'], s3, '✅ bypass' if ok else json.dumps(d3.get('errors') or d3, ensure_ascii=False)[:150]))

print()
print('=== 复核：全部应用及其策略 ===')
s, d = api('/accounts/%s/access/apps?per_page=100' % ACCT)
for a in sorted(d.get('result') or [], key=lambda x: x['domain']):
    s2, d2 = api('/accounts/%s/access/apps/%s/policies?per_page=100' % (ACCT, a['id']))
    pols = ', '.join('%s(%s)' % (p.get('name'), p.get('decision')) for p in (d2.get('result') or []))
    print('  %-42s session=%-5s %s' % (a['domain'], a.get('session_duration'), pols or '(无策略!)'))
