import base64, json, re, urllib.request, urllib.error

data = open('/home/gazer/.cloudflared/cert.pem').read()
m = re.search(r'-----BEGIN [A-Z ]+-----(.*?)-----END [A-Z ]+-----', data, re.S)
info = json.loads(base64.b64decode(''.join(m.group(1).split())))
token, tunnel_acct = info['apiToken'], info['accountID']

def api(path):
    req = urllib.request.Request('https://api.cloudflare.com/client/v4' + path,
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw[:300]}
    except Exception as e:
        return -1, {'error': repr(e)}

print('隧道所在 account:', tunnel_acct)
s, d = api('/accounts')
print('GET /accounts ->', s)
accounts = d.get('result') or []
for a in accounts:
    print('  - %s | %s' % (a.get('id'), a.get('name')))
print('可见账号数:', len(accounts))

print()
print('逐账号查 Access 应用:')
for a in accounts:
    aid = a.get('id')
    s2, d2 = api('/accounts/%s/access/apps' % aid)
    if s2 == 200 and d2.get('success'):
        apps = d2['result']
        print('  [%s] %s -> %d 个应用' % (aid[:8], a.get('name'), len(apps)))
        for app in apps:
            print('      id=%s | name=%s | domain=%s | session=%s' % (
                app.get('id'), app.get('name'), app.get('domain'), app.get('session_duration')))
    else:
        print('  [%s] %s -> status %s %s' % (aid[:8], a.get('name'), s2,
              json.dumps(d2.get('errors') or d2)[:160]))
