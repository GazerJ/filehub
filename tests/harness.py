"""测试辅助：启动一个隔离的中转站实例（独立端口 + 独立数据目录）。"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Sandbox:
    def __init__(self, name, port, ttl_days=7.0, janitor=1.0, max_mb=2048):
        self.name = name
        self.port = port
        self.ttl_days = ttl_days
        self.janitor = janitor
        self.max_mb = max_mb
        self.dir = os.path.join(tempfile.gettempdir(), "filehub-test-" + name)
        self.proc = None
        self.log_path = os.path.join(self.dir, "server.log")

    # -- 生命周期 -----------------------------------------------------------
    def start(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        os.makedirs(self.dir, exist_ok=True)
        shutil.copy(os.path.join(ROOT, "server.py"), os.path.join(self.dir, "server.py"))
        os.symlink(os.path.join(ROOT, "static"), os.path.join(self.dir, "static"))
        log = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            [sys.executable, "-u", os.path.join(self.dir, "server.py"),
             "--port", str(self.port), "--ttl-days", str(self.ttl_days),
             "--janitor-interval", str(self.janitor), "--max-mb", str(self.max_mb), "--quiet"],
            cwd=self.dir, stdout=log, stderr=subprocess.STDOUT, text=True)
        for _ in range(60):
            time.sleep(0.2)
            try:
                self.call("GET", "/healthz")
                return self
            except Exception:
                if self.proc.poll() is not None:
                    raise SystemExit("实例启动失败:\n" + open(self.log_path).read())
        raise SystemExit("实例启动超时")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # -- 请求 ---------------------------------------------------------------
    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port

    def call(self, method, path, data=None, headers=None, raw=False):
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                return resp.status, (body if raw else body.decode("utf-8", "replace")), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, (body if raw else body.decode("utf-8", "replace")), dict(exc.headers)

    def upload(self, name, blob, mime="application/octet-stream"):
        query = urllib.parse.urlencode({"name": name, "mime": mime})
        status, body, headers = self.call("PUT", "/api/upload?" + query, data=blob,
                                          headers={"Content-Type": mime})
        record = None
        try:
            record = json.loads(body).get("file")
        except ValueError:
            pass
        return status, record, body

    def list_files(self):
        status, body, _ = self.call("GET", "/api/files")
        return json.loads(body)

    def blob_path(self, fid):
        return os.path.join(self.dir, "data", "blobs", fid)


class Checks:
    def __init__(self):
        self.ok = True

    def __call__(self, label, cond, extra=""):
        self.ok = self.ok and bool(cond)
        print(("  PASS  " if cond else "  FAIL  ") + label + (("  -> " + str(extra)) if extra else ""))
        return bool(cond)

    def report(self):
        print()
        print("全部通过" if self.ok else "存在失败项")
        return 0 if self.ok else 1
