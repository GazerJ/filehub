import base64, json, re, urllib.request, urllib.error

data = open('/home/gazer/.cloudflared/cert.pem').read()
m = re.search(r'-----BEGIN [A-Z ]+-----(.*?)-----END [A-Z ]+-----', data, re.S)
info = json.loads(base64.b64decode(''.join(m.group(1).split())))
token, acct = info['apiToken'], info['accountID']
TUNNEL = '8c10c6b5-d3c9-4955-825f-36e5155e84ca'

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

print('=== 隧道列表（看这个 token 能看到哪些隧道/账号）===')
s, d = api('/accounts/%s/cfd_tunnel?is_deleted=false' % acct)
print('status', s, 'success', d.get('success'))
for t in (d.get('result') or []):
    print('  - %s | %s | conns=%s' % (t.get('id', '')[:8], t.get('name'), len(t.get('connections') or [])))

print()
print('=== 隧道的远端配置（如果 Access 是在 Dashboard 上按 hostname 开的，会在这里）===')
s, d = api('/accounts/%s/cfd_tunnel/%s/configurations' % (acct, TUNNEL))
print('status', s, 'success', d.get('success'))
res = d.get('result') or {}
cfg = res.get('config') or {}
print('远端 config 是否存在:', bool(cfg))
if cfg:
    for ing in cfg.get('ingress', []):
        print('   ', json.dumps(ing, ensure_ascii=False)[:220])
else:
    print('   （无远端配置 → 隧道是本地 config 文件管理，Access 不在隧道配置里）')
print('源:', res.get('source'))
