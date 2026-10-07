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
            return e.code, {'raw': raw[:300]}

s, d = api('/zones/%s/dns_records?per_page=100' % zone)
print('DNS 记录查询 status', s, 'success', d.get('success'))
if d.get('success'):
    recs = d['result']
    print('记录数:', len(recs))
    for r in recs:
        content = r.get('content', '')
        if 'cfargotunnel.com' in content:
            content = content.split('.')[0][:8] + '…cfargotunnel.com'
        print('  %-28s %-6s %s' % (r.get('name'), r.get('type'), content))
