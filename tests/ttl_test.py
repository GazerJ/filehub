"""有效期与过期清理测试：用很短的 TTL 起一个临时实例。"""
import json, os, shutil, signal, subprocess, sys, time, urllib.request, urllib.parse

ROOT = "/home/gazer/filehub"
PORT = 8799
DATA = "/tmp/filehub-ttl-test"

shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(DATA, exist_ok=True)
shutil.copy(os.path.join(ROOT, "server.py"), os.path.join(DATA, "server.py"))
os.symlink(os.path.join(ROOT, "static"), os.path.join(DATA, "static"))

def start(ttl_days):
    proc = subprocess.Popen(
        [sys.executable, "-u", os.path.join(DATA, "server.py"), "--port", str(PORT),
         "--ttl-days", str(ttl_days), "--janitor-interval", "1", "--quiet"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=DATA)
    for _ in range(50):
        time.sleep(0.2)
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/healthz" % PORT, timeout=1).read()
            return proc
        except Exception:
            if proc.poll() is not None:
                raise SystemExit("实例启动失败:\n" + proc.stdout.read())
    raise SystemExit("实例启动超时")

def call(method, path, data=None, headers=None):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")

ok = True
def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))

# TTL = 2 秒
proc = start(2.0 / 86400)
try:
    q = urllib.parse.urlencode({"name": "short.txt"})
    s, b = call("PUT", "/api/upload?" + q, data=b"expire me soon")
    rec = json.loads(b)["file"]
    blob = os.path.join(DATA, "data", "blobs", rec["id"])
    s2, b2 = call("GET", "/api/files")
    check("刚上传时列表有 1 个文件", json.loads(b2)["count"] == 1)
    check("文件已落盘", os.path.isfile(blob))
    check("剩余时间 <= 2 秒", json.loads(b2)["files"][0]["remaining"] <= 2)

    time.sleep(3.2)
    s3, b3 = call("GET", "/api/files")
    check("过期后列表为空", json.loads(b3)["count"] == 0, b3[:120])
    s4, b4 = call("GET", "/d/" + rec["id"])
    check("过期后下载 404", s4 == 404, s4)
finally:
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)

# 重新启动：验证启动时清理 + 后台清理线程
proc = start(2.0 / 86400)
try:
    log = ""
    s, b = call("GET", "/healthz")
    check("重启后服务可用", s == 200)
    s, b = call("GET", "/api/files")
    check("重启后过期文件不出现", json.loads(b)["count"] == 0)
    time.sleep(1.0)
    # 上传一个文件 → 等过期 → 等 janitor（每分钟一次，这里直接调 purge 的行为由启动清理覆盖）
    q = urllib.parse.urlencode({"name": "second.txt"})
    s, b = call("PUT", "/api/upload?" + q, data=b"x" * 32)
    check("第二次上传成功", s == 200, b[:100])
    time.sleep(3.2)
    s, b = call("GET", "/api/files")
    check("过期的第二个文件也消失", json.loads(b)["count"] == 0)
    time.sleep(2.5)  # 等一轮巡检线程
    left = os.listdir(os.path.join(DATA, "data", "blobs"))
    check("巡检线程删除了磁盘文件", left == [], left)
finally:
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)
    time.sleep(0.5)
    alive = os.listdir(os.path.join(DATA, "data", "blobs"))
    check("磁盘上的过期文件已被删除", alive == [], alive)

print()
print("TTL 测试全部通过" if ok else "TTL 测试存在失败项")
sys.exit(0 if ok else 1)
