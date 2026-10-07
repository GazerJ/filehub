"""关闭指定域名的 Cloudflare Access（两种模式，均支持 --dry-run）。

用法：
  python3 cf_access_off.py --domain softmatter.gaoxiao.asia --mode bypass [--dry-run]   # 保留应用，策略改成 bypass（可秒级回退）
  python3 cf_access_off.py --domain softmatter.gaoxiao.asia --mode delete [--dry-run]   # 删除应用（连同策略）
                                                       [--keep-bypass]                 # delete 模式下保留 /path 的 bypass 子应用
"""
import argparse, json, re, urllib.request, urllib.error

ap = argparse.ArgumentParser()
ap.add_argument('--domain', required=True)
ap.add_argument('--mode', choices=['bypass', 'delete'], required=True)
ap.add_argument('--dry-run', action='store_true')
ap.add_argument('--keep-bypass', action='store_true', help='delete 模式下不清理该域名的 /path 子应用')
args = ap.parse_args()

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
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw[:250]}

s, d = api('/accounts/%s/access/apps?per_page=100' % ACCT)
apps = d.get('result') or []
main = [a for a in apps if a.get('domain') == args.domain]
subs = [a for a in apps if a.get('domain', '').startswith(args.domain + '/')]

if not main:
    print('没有找到域名 %s 的 Access 应用（可能已经关了）' % args.domain)
    raise SystemExit(0)

print('目标应用: %s (id=%s, session=%s)' % (main[0]['name'], main[0]['id'], main[0].get('session_duration')))
print('该域名下的 /path 子应用: %s' % ([a['domain'] for a in subs] or '无'))
print()

if args.mode == 'bypass':
    print('=== 计划：把策略改成 bypass（保留应用，可秒级回退）===')
    for a in main:
        s2, d2 = api('/accounts/%s/access/apps/%s/policies?per_page=100' % (ACCT, a['id']))
        for p in (d2.get('result') or []):
            print('  策略 %-14s decision=%s -> bypass' % (p.get('name'), p.get('decision')))
            if args.dry_run:
                continue
            body = dict(p)
            body['decision'] = 'bypass'
            body.setdefault('include', [{'everyone': {}}])
            body['include'] = [{'everyone': {}}] if p.get('decision') != 'bypass' else p.get('include')
            s3, d3 = api('/accounts/%s/access/apps/%s/policies/%s' % (ACCT, a['id'], p['id']), 'PUT', body)
            print('     -> status=%s %s' % (s3, '✅' if s3 in (200, 201) and d3.get('success') else json.dumps(d3.get('errors') or d3, ensure_ascii=False)[:150]))
else:
    print('=== 计划：删除应用（连同其策略）===')
    for a in main:
        print('  DELETE /access/apps/%s   (%s)' % (a['id'], a['domain']))
        if not args.dry_run:
            s2, d2 = api('/accounts/%s/access/apps/%s' % (ACCT, a['id']), 'DELETE')
            print('     -> status=%s %s' % (s2, '✅' if s2 in (200, 202) and d2.get('success') else json.dumps(d2.get('errors') or d2, ensure_ascii=False)[:150]))
    if subs and not args.keep_bypass:
        print('  该域名下的子应用在删除主应用后就没有意义了，一并清理：')
        for a in subs:
            print('    DELETE /access/apps/%s   (%s)' % (a['id'], a['domain']))
            if not args.dry_run:
                s3, d3 = api('/accounts/%s/access/apps/%s' % (ACCT, a['id']), 'DELETE')
                print('       -> status=%s %s' % (s3, '✅' if s3 in (200, 202) and d3.get('success') else json.dumps(d3.get('errors') or d3, ensure_ascii=False)[:150]))
    elif subs:
        print('  --keep-bypass：保留 %d 个子应用' % len(subs))

print()
print('dry-run' if args.dry_run else '已执行')
