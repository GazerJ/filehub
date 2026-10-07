import base64, json, re, urllib.request, urllib.error

data = open('/home/gazer/.cloudflared/cert.pem').read()
m = re.search(r'-----BEGIN [A-Z ]+-----(.*?)-----END [A-Z ]+-----', data, re.S)
info = json.loads(base64.b64decode(''.join(m.group(1).split())))
token, acct = info['apiToken'], info['accountID']

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

for path, label in [
    ('/accounts/%s/access/organizations' % acct, 'Access 组织（team domain）'),
    ('/accounts/%s/access/identity_providers' % acct, '身份提供商'),
    ('/accounts/%s/access/apps' % acct, 'Access 应用'),
    ('/accounts/%s/access/policies' % acct, 'Access 策略'),
    ('/zones?account.id=%s' % acct, '账号下的域名'),
]:
    s, d = api(path)
    ok = d.get('success')
    print('%-28s status=%s success=%s' % (label, s, ok))
    if s == 200 and ok:
        res = d.get('result')
        if label.startswith('Access 组织'):
            print('     ', json.dumps(res, ensure_ascii=False)[:300])
        elif label.startswith('账号下的域名'):
            print('     域名:', [z.get('name') for z in (res or [])][:10])
        else:
            print('      数量:', len(res or []))
    else:
        print('      错误:', json.dumps(d.get('errors') or d, ensure_ascii=False)[:250])
