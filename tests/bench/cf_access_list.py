import json, os, re, urllib.request, urllib.error

env = {}
for line in open('/home/gazer/.config/ssl-auto/cloudflare-access.env'):
    m = re.match(r'export\s+(\w+)="?([^"\n]+)"?', line.strip())
    if m:
        env[m.group(1)] = m.group(2)
token, acct = env['CF_ACCESS_API_TOKEN'], env['CF_ACCOUNT_ID']

def api(path, method='GET', payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request('https://api.cloudflare.com/client/v4' + path, data=body, method=method,
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw[:250]}

s, d = api('/accounts/%s/access/apps?per_page=100' % acct)
print('GET access/apps ->', s, d.get('success'))
apps = d.get('result') or []
print('应用数量:', len(apps))
print()
for a in apps:
    print('id=%s' % a.get('id'))
    print('  name=%s | domain=%s | type=%s' % (a.get('name'), a.get('domain'), a.get('type')))
    print('  session=%s | self_hosted_domains=%s' % (a.get('session_duration'), a.get('self_hosted_domains')))
    print('  allowed_idps=%s | auto_redirect=%s' % (a.get('allowed_idps'), a.get('auto_redirect_to_identity')))
    s2, d2 = api('/accounts/%s/access/apps/%s/policies?per_page=100' % (acct, a['id']))
    for p in (d2.get('result') or []):
        inc = json.dumps(p.get('include'), ensure_ascii=False)
        print('    策略: %s | decision=%s | include=%s' % (p.get('name'), p.get('decision'), inc[:120]))
    print()
