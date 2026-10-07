import base64, json, re, urllib.request, urllib.error

data = open('/home/gazer/.cloudflared/cert.pem').read()
m = re.search(r'-----BEGIN [A-Z ]+-----(.*?)-----END [A-Z ]+-----', data, re.S)
info = json.loads(base64.b64decode(''.join(m.group(1).split())))
token, acct, zone = info['apiToken'], info['accountID'], info['zoneID']

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
            return e.code, {'raw': raw[:200]}
    except Exception as e:
        return -1, {'error': repr(e)}

tests = [
    '/zones/%s/access/apps' % zone,
    '/accounts/%s/access/apps?per_page=100&page=1' % acct,
    '/accounts/%s/access/apps/9f22d2c01436d9dc851c58c886b159db63c19b2b05424a1762554e8c48e30a22' % acct,
    '/accounts/%s/access/certificates' % acct,
    '/accounts/%s/access/groups' % acct,
]
for p in tests:
    s, d = api(p)
    ok = d.get('success')
    extra = ''
    if s == 200 and ok:
        res = d.get('result')
        extra = '数量=%s' % (len(res) if isinstance(res, list) else type(res).__name__)
    else:
        errs = d.get('errors') or d
        extra = json.dumps(errs, ensure_ascii=False)[:150]
    print('%-72s status=%s ok=%s %s' % (p[:72], s, ok, extra))
