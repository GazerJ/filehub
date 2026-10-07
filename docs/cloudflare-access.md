# Cloudflare Access 配置记录（*.gaoxiao.asia）

> 记录 2026-10-07 起生效的 Zero Trust Access 配置，方便回滚和复现。
> 凭据：`~/.config/ssl-auto/cloudflare-access.env`（`CF_ACCESS_API_TOKEN` + `CF_ACCOUNT_ID`，chmod 600）
> 账号 `0c978051b8c9f0d43f023fb18181c0e6`，team domain `gaoxiao-dsh.cloudflareaccess.com`

## 现状

| 应用 domain | 作用 | session | 策略 |
| --- | --- | --- | --- |
| `dsh.gaoxiao.asia` | DSH Web GUI 主入口 | **720h（30 天）** | allow-owners → `jianggaoxiao@qq.com` |
| `softmatter.gaoxiao.asia` | code-server | **720h（30 天）** | allow-owners → `jianggaoxiao@qq.com` |
| `dsh.gaoxiao.asia/assets` | 前端 JS/CSS 包 | 24h | **bypass**（everyone） |
| `dsh.gaoxiao.asia/plugins` | 客户端插件 bundle | 24h | **bypass**（everyone） |
| `dsh.gaoxiao.asia/favicon.svg`、`dsh.gaoxiao.asia/manifest.webmanifest` | 图标 / PWA 清单 | 24h | **bypass**（everyone） |
| `softmatter.gaoxiao.asia/static` | code-server 前端资源 | 24h | **bypass**（everyone） |
| `softmatter.gaoxiao.asia/favicon.ico`、`softmatter.gaoxiao.asia/manifest.json` | 图标 / PWA 清单 | 24h | **bypass**（everyone） |

原理：Access 应用可以带路径（`host/path`），**匹配时按最长路径优先**。给静态前缀单独建一个
`decision=bypass` 的应用，这些请求就跳过 Access，而同一域名下的其他路径仍由主应用保护。

## 绝对不要 bypass 的路径

这些路径能读文件或转发请求，绕过 Access 等于把机器敞开：

- `softmatter.gaoxiao.asia/vscode-remote-resource` —— 可读远端任意文件
- `softmatter.gaoxiao.asia/proxy/` —— code-server 的端口代理
- `softmatter.gaoxiao.asia/update/`
- 任何 `/api/*`（例如 `dsh.gaoxiao.asia/api/*`）

## 复现 / 回滚

~~~bash
cd ~/filehub
python3 tests/bench/cf_access_list.py              # 列出所有应用与策略
python3 tests/bench/cf_access_bypass.py --dry-run  # 看会改什么
python3 tests/bench/cf_access_bypass.py            # 幂等执行：延 session + 建 bypass 应用
python3 tests/bench/cf_access_fix_policies.py      # 给已建应用补 bypass 策略（幂等）
~~~

**整个关掉某个域名的 Access**（两步都要先看 dry-run）：

~~~bash
cd ~/filehub
# A. 保留应用、策略改 bypass（推荐，一条命令可回退）
python3 tests/bench/cf_access_off.py --domain softmatter.gaoxiao.asia --mode bypass --dry-run
python3 tests/bench/cf_access_off.py --domain softmatter.gaoxiao.asia --mode bypass

# B. 彻底删除应用（连同该域名下的 /path 子应用）
python3 tests/bench/cf_access_off.py --domain softmatter.gaoxiao.asia --mode delete --dry-run
python3 tests/bench/cf_access_off.py --domain softmatter.gaoxiao.asia --mode delete

# 回退 A：把策略 decision 改回 allow 即可；回退 B：用 cf-access-setup.py 重建
python3 ~/git/Coder/ssl-auto/cf-access-setup.py --domain softmatter.gaoxiao.asia --email jianggaoxiao@qq.com --team gaoxiao-dsh
~~~

关闭后务必确认源站自身有鉴权：code-server 是 [[auth: password]]（容器 myCoderV2 的
[[/home/coder/.config/code-server/config.yaml]]），别用弱密码——公网会有机器人扫登录接口。

删掉某一个 bypass 应用（例如不想要 code-server 的）：

~~~bash
set -a; . ~/.config/ssl-auto/cloudflare-access.env; set +a
API=https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID
curl -s -H "Authorization: Bearer $CF_ACCESS_API_TOKEN" "$API/access/apps?per_page=100" \
  | python3 -c "import json,sys;[print(a['id'],a['domain']) for a in json.load(sys.stdin)['result'`"
curl -s -X DELETE -H "Authorization: Bearer $CF_ACCESS_API_TOKEN" "$API/access/apps/<app_id>"
~~~

## 验证

~~~bash
# 静态资源：应 200（不再 302 到 Access）
curl -s -o /dev/null -w '%{http_code}\n' https://dsh.gaoxiao.asia/assets/index-ClqxG24t.js
curl -s -o /dev/null -w '%{http_code}\n' https://softmatter.gaoxiao.asia/static/out/vs/code/browser/workbench/workbench.html
# 受保护路径：应 302 到 <team>.cloudflareaccess.com
curl -s -o /dev/null -w '%{http_code}\n' https://dsh.gaoxiao.asia/
curl -s -o /dev/null -w '%{http_code}\n' https://dsh.gaoxiao.asia/api/respond
curl -s -o /dev/null -w '%{http_code}\n' https://softmatter.gaoxiao.asia/proxy/
~~~

## 注意

- **30 天是 Cloudflare self-hosted 应用会话的上限**。会话越长，被窃取的 `CF_AppSession` cookie 可用时间越长。
- bypass 只跳过**边缘的身份校验**，源站自己的鉴权照旧：code-server 仍是 `auth: password`，
  所以绕过 Access 后 `/static/...` 返回 401（来自 code-server 而不是 Access）。
- 新增 hostname 时单独建应用，不要用通配符整站放行。
