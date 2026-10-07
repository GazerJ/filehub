import base64, json, re, urllib.request, urllib.error

data = open('/home/gazer/.cloudflared/cert.pem').read()
m = re.search(r'-----BEGIN [A-Z ]+-----(.*?)-----END [A-Z ]+-----', data, re.S)
info = json.loads(base64.b64decode(''.join(m.group(1).split())))
token, zone = info['apiToken'], info['zoneID']

def api(path):
    req = urllib.request.Request('https://api.cloudflare.com/client/v4' + path,
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw[:150]}
    except Exception as e:
        return -1, {'error': repr(e)}

show = ['brotli', 'early_hints', 'http3', 'zero_rtt', 'rocket_loader', 'autominify',
        'browser_cache_ttl', 'cache_level', 'websockets', 'orange_to_orange', 'polish', 'mirage']
print('=== 影响交互体验的 zone 级设置 ===')
for name in show:
    s, d = api('/zones/%s/settings/%s' % (zone, name))
    if s == 200 and d.get('success'):
        print('  %-18s = %s' % (name, d['result'].get('value')))
    else:
        print('  %-18s 读取失败: %s' % (name, json.dumps(d.get('errors') or d)[:80]))

print()
print('=== Argo Smart Routing 状态 ===')
for path in ['/zones/%s/argo/smart_routing' % zone, '/zones/%s/argo/tiered_caching' % zone]:
    s, d = api(path)
    label = path.split('/')[-1]
    if s == 200 and d.get('success'):
        print('  %-16s = %s' % (label, d['result'].get('value')))
    else:
        print('  %-16s 读取失败: %s' % (label, json.dumps(d.get('errors') or d)[:80]))
