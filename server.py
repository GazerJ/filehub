#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件中转站 —— 扫码上传 / 选择文件上传 / 多选打包下载 / 7 天自动过期。

只用 Python 标准库（二维码用 qrcode + Pillow，缺失时降级为前端提示）。
启动:  python3 server.py --host 0.0.0.0 --port 8788 --ttl-days 7
"""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
BLOB_DIR = os.path.join(DATA_DIR, "blobs")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")

CHUNK = 256 * 1024
DAY = 86400
DEFAULT_TTL_DAYS = 7
DEFAULT_MAX_MB = 2048

INDEX_CACHE = {"mtime": 0.0}


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def clean_name(raw: str) -> str:
    """把浏览器给的文件名收拾成一个安全的单层文件名。"""
    name = unquote(raw or "")
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch >= " " and ch != "\x7f").strip()
    name = name.lstrip(".") or "未命名文件"
    if len(name) > 150:
        stem, ext = os.path.splitext(name)
        name = stem[:130] + ext[:19]
    return name


def content_disposition(name: str, inline: bool = False) -> str:
    kind = "inline" if inline else "attachment"
    fallback = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "download"
    return "%s; filename=\"%s\"; filename*=UTF-8''%s" % (kind, fallback, quote(name, safe=""))


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


VIRTUAL_IFACE = re.compile(r"^(docker|br-|veth|virbr|vmnet|tun|tap|zt|wg)")


def local_ipv4() -> list:
    """本机可用于手机访问的 IPv4 地址：真实的局域网地址排前面，Docker/虚拟网卡排后面。"""
    found = []  # [(ip, ifname)]

    def add(ip, ifname=""):
        if ip and not ip.startswith("127.") and all(ip != known for known, _ in found):
            found.append((ip, ifname))

    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True, timeout=3).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] == "inet":
                add(parts[3].split("/")[0], parts[1])
    except Exception:
        pass

    if not found:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                add(s.getsockname()[0])
            finally:
                s.close()
        except OSError:
            pass
        try:
            for ip in subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=3).stdout.split():
                add(ip)
        except Exception:
            pass
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                add(info[4][0])
        except OSError:
            pass

    # 有真实网卡地址时，就不再把 Docker/虚拟网桥地址列出来给手机用
    if any(not VIRTUAL_IFACE.match(ifname or "") for _, ifname in found):
        found = [(ip, ifname) for ip, ifname in found if not VIRTUAL_IFACE.match(ifname or "")]

    def rank(item):
        ip, ifname = item
        score = 0
        if VIRTUAL_IFACE.match(ifname or ""):
            score += 4
        if ip.startswith("192.168."):
            score += 0
        elif ip.startswith("10."):
            score += 1
        elif re.match(r"172.(1[6-9]|2d|3[01]).", ip):
            score += 3  # 常见于 Docker 网桥
        else:
            score += 2
        return score

    found.sort(key=rank)
    return [ip for ip, _ in found]


# --------------------------------------------------------------------------- #
# 元数据存储
# --------------------------------------------------------------------------- #
class Store:
    def __init__(self, ttl_seconds: int, max_bytes: int):
        self.ttl = ttl_seconds
        self.max_bytes = max_bytes
        self.lock = threading.RLock()
        self.records = {}
        os.makedirs(BLOB_DIR, exist_ok=True)
        self._load()

    # -- 持久化 --------------------------------------------------------------
    def _load(self):
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for rec in data.get("files", []):
                if isinstance(rec, dict) and rec.get("id"):
                    self.records[rec["id"]] = rec
        except FileNotFoundError:
            pass
        except Exception as exc:  # 索引损坏时不要阻止服务启动
            print("[store] 索引读取失败: %s" % exc, flush=True)

    def _save(self):
        tmp = INDEX_PATH + ".tmp"
        payload = {"version": 1, "saved_at": time.time(), "files": list(self.records.values())}
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, INDEX_PATH)

    # -- 查询 ----------------------------------------------------------------
    def blob_path(self, fid: str) -> str:
        return os.path.join(BLOB_DIR, fid)

    def active(self) -> list:
        now = time.time()
        with self.lock:
            items = [r for r in self.records.values() if r.get("expires_at", 0) > now]
        items.sort(key=lambda r: r.get("uploaded_at", 0), reverse=True)
        return items

    def get(self, fid: str):
        with self.lock:
            rec = self.records.get(fid)
        if not rec or rec.get("expires_at", 0) <= time.time():
            return None
        return rec

    def total_size(self) -> int:
        return sum(int(r.get("size", 0)) for r in self.active())

    # -- 写入 ----------------------------------------------------------------
    def add(self, name: str, size: int, mime: str, src: str) -> dict:
        now = time.time()
        rec = {
            "id": uuid.uuid4().hex[:16],
            "name": name,
            "size": int(size),
            "mime": mime or "application/octet-stream",
            "uploaded_at": now,
            "expires_at": now + self.ttl,
            "src": (src or "")[:64],
        }
        with self.lock:
            self.records[rec["id"]] = rec
            self._save()
        return rec

    def delete(self, ids) -> int:
        removed = 0
        with self.lock:
            for fid in ids:
                rec = self.records.pop(fid, None)
                if rec is None:
                    continue
                removed += 1
                try:
                    os.remove(self.blob_path(fid))
                except OSError:
                    pass
            if removed:
                self._save()
        return removed

    def purge_expired(self) -> int:
        now = time.time()
        with self.lock:
            dead = [fid for fid, r in self.records.items() if r.get("expires_at", 0) <= now]
            for fid in dead:
                self.records.pop(fid, None)
                try:
                    os.remove(self.blob_path(fid))
                except OSError:
                    pass
            # 清掉没有索引记录的孤儿文件（例如上传中途失败）
            try:
                known = set(self.records)
                for fn in os.listdir(BLOB_DIR):
                    if fn.endswith(".part"):
                        path = os.path.join(BLOB_DIR, fn)
                        if now - os.path.getmtime(path) > 3600:
                            os.remove(path)
                    elif fn not in known and now - os.path.getmtime(os.path.join(BLOB_DIR, fn)) > 3600:
                        os.remove(os.path.join(BLOB_DIR, fn))
            except OSError:
                pass
            if dead:
                self._save()
        return len(dead)


# --------------------------------------------------------------------------- #
# HTTP 处理
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "FileHub/1.0"
    protocol_version = "HTTP/1.0"  # 打包下载用“连接关闭”作为结束标志
    store: Store = None
    ttl_days: int = DEFAULT_TTL_DAYS
    quiet: bool = True

    # -- 日志 ----------------------------------------------------------------
    def log_message(self, fmt, *args):
        if not self.quiet:
            print("[http] %s - %s" % (self.address_string(), fmt % args), flush=True)

    def log_error(self, fmt, *args):
        print("[http] %s - %s" % (self.address_string(), fmt % args), flush=True)

    # -- 响应助手 ------------------------------------------------------------
    def wbody(self, data: bytes):
        """HEAD 请求只发响应头，不发响应体。"""
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, obj, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wbody(body)

    def send_text(self, text: str, status: int = 200, ctype: str = "text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wbody(body)

    def send_bytes(self, body: bytes, ctype: str, status: int = 200, max_age: int = 0):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=%d" % max_age if max_age else "no-store")
        self.end_headers()
        self.wbody(body)

    def serve_static(self, rel: str):
        safe = os.path.normpath(rel).lstrip("/")
        if safe.startswith(".."):
            return self.send_text("bad path", 400)
        path = os.path.join(STATIC_DIR, safe)
        if not os.path.isfile(path):
            return self.send_text("404 not found", 404)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        with open(path, "rb") as fh:
            body = fh.read()
        self.send_bytes(body, ctype)

    # -- 请求体读取 ----------------------------------------------------------
    def body_reader(self):
        """返回 (迭代器, 总长度或 None)，兼容 Content-Length 与 chunked。"""
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in te:
            return self._chunked_reader(), None
        length = self.headers.get("Content-Length")
        if length is None:
            length = self.headers.get("X-File-Size")
        total = int(length) if length and length.isdigit() else None

        def gen():
            remaining = total
            while remaining is None or remaining > 0:
                want = CHUNK if remaining is None else min(CHUNK, remaining)
                buf = self.rfile.read(want)
                if not buf:
                    break
                if remaining is not None:
                    remaining -= len(buf)
                yield buf

        return gen(), total

    def _chunked_reader(self):
        while True:
            line = self.rfile.readline(64).strip()
            if not line:
                break
            try:
                size = int(line.split(b";")[0], 16)
            except ValueError:
                break
            if size == 0:
                self.rfile.readline(64)
                break
            left = size
            while left > 0:
                buf = self.rfile.read(min(CHUNK, left))
                if not buf:
                    return
                left -= len(buf)
                yield buf
            self.rfile.readline(64)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return {}

    # -- 路由 ----------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                return self.serve_static("index.html")
            if path in ("/m", "/m/", "/mobile", "/mobile.html"):
                return self.serve_static("mobile.html")
            if path.startswith("/static/"):
                return self.serve_static(path[len("/static/"):])
            if path in ("/favicon.ico", "/apple-touch-icon.png"):
                return self.serve_static("favicon.svg")
            if path == "/api/files":
                return self.api_files()
            if path == "/api/info":
                return self.api_info()
            if path == "/api/qr.png":
                return self.api_qr(query)
            if path.startswith("/d/"):
                return self.serve_download(path[3:], inline=query.get("inline") == ["1"])
            if path == "/zip":
                ids = ",".join(query.get("ids", [])).split(",")
                return self.serve_zip([i.strip() for i in ids if i.strip()])
            if path == "/healthz":
                return self.send_json({"ok": True, "files": len(self.store.active())})
            return self.send_text("404 not found", 404)
        except BrokenPipeError:
            pass
        except Exception as exc:
            self.log_error("GET %s 失败: %r", self.path, exc)
            try:
                self.send_json({"error": "服务器内部错误: %s" % exc}, 500)
            except Exception:
                pass

    do_HEAD = do_GET

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/upload":
            return self.send_text("404 not found", 404)
        try:
            self.api_upload(parse_qs(parsed.query))
        except Exception as exc:
            self.log_error("上传失败: %r", exc)
            try:
                self.send_json({"error": "上传失败: %s" % exc}, 500)
            except Exception:
                pass

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/delete":
            data = self.read_json()
            ids = data.get("ids") or []
            if not isinstance(ids, list):
                return self.send_json({"error": "ids 必须是数组"}, 400)
            return self.send_json({"deleted": self.store.delete([str(i) for i in ids])})
        if parsed.path == "/api/upload":
            try:
                return self.api_upload(parse_qs(parsed.query))
            except Exception as exc:
                self.log_error("上传失败: %r", exc)
                return self.send_json({"error": "上传失败: %s" % exc}, 500)
        return self.send_text("404 not found", 404)

    # -- 接口实现 ------------------------------------------------------------
    def api_files(self):
        files = []
        now = time.time()
        for rec in self.store.active():
            item = dict(rec)
            item["remaining"] = max(0, int(rec["expires_at"] - now))
            item["url"] = "/d/" + rec["id"]
            files.append(item)
        self.send_json({
            "files": files,
            "now": now,
            "count": len(files),
            "total_size": self.store.total_size(),
            "ttl_days": self.ttl_days,
        })

    def api_info(self):
        host_hdr = self.headers.get("Host") or ""
        port = self.server.server_address[1]
        lan = ["http://%s:%d" % (ip, port) for ip in local_ipv4()]
        disk = shutil.disk_usage(DATA_DIR)
        self.send_json({
            "service": "文件中转站",
            "ttl_days": self.ttl_days,
            "max_upload_mb": self.store.max_bytes // (1024 * 1024),
            "host": host_hdr,
            "port": port,
            "lan_urls": lan,
            "mobile_path": "/m",
            "disk_free": disk.free,
            "disk_total": disk.total,
            "now": time.time(),
        })

    def api_qr(self, query):
        url = (query.get("url") or [""])[0]
        if not url:
            return self.send_text("缺少 url 参数", 400)
        try:
            png = make_qr_png(url)
        except Exception as exc:
            return self.send_json({"error": "二维码生成失败: %s" % exc}, 500)
        self.send_bytes(png, "image/png", max_age=3600)

    def api_upload(self, query):
        raw_name = (query.get("name") or [self.headers.get("X-File-Name") or ""])[0]
        name = clean_name(raw_name)
        mime = (query.get("mime") or [self.headers.get("Content-Type") or ""])[0]
        reader, total = self.body_reader()
        if total is not None and total > self.store.max_bytes:
            return self.send_json(
                {"error": "文件太大（上限 %s）" % human_size(self.store.max_bytes), "limit": self.store.max_bytes},
                413,
            )
        tmp = os.path.join(BLOB_DIR, uuid.uuid4().hex + ".part")
        written = 0
        try:
            with open(tmp, "wb") as fh:
                for buf in reader:
                    written += len(buf)
                    if written > self.store.max_bytes:
                        raise ValueError("文件超过上限 %s" % human_size(self.store.max_bytes))
                    fh.write(buf)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        if written == 0 and total not in (0, None):
            try:
                os.remove(tmp)
            except OSError:
                pass
            return self.send_json({"error": "上传内容为空，请重试"}, 400)
        src = self.headers.get("X-Forwarded-For") or self.client_address[0]
        rec = self.store.add(name, written, mime or "application/octet-stream", src.split(",")[0].strip())
        os.replace(tmp, self.store.blob_path(rec["id"]))
        item = dict(rec)
        item["remaining"] = self.ttl_days * DAY
        item["url"] = "/d/" + rec["id"]
        self.send_json({"ok": True, "file": item})

    def serve_download(self, fid: str, inline: bool = False):
        rec = self.store.get(fid)
        path = self.store.blob_path(fid)
        if not rec or not os.path.isfile(path):
            return self.send_text("文件不存在或已过期", 404)
        size = os.path.getsize(path)
        ctype = rec.get("mime") or mimetypes.guess_type(rec["name"])[0] or "application/octet-stream"
        start, end = 0, size - 1
        status = 200
        rng = self.headers.get("Range") or ""
        m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
        if m and size > 0:
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            elif m.group(2):
                start = max(0, size - int(m.group(2)))
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            end = min(end, size - 1)
            status = 206
        length = end - start + 1 if size else 0
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Disposition", content_disposition(rec["name"], inline=inline))
        self.send_header("Last-Modified", self.date_time_string(int(rec.get("uploaded_at", time.time()))))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                buf = fh.read(min(CHUNK, left))
                if not buf:
                    break
                self.wfile.write(buf)
                left -= len(buf)

    def serve_zip(self, ids):
        recs = []
        used = set()
        for fid in ids[:500]:
            rec = self.store.get(fid)
            if rec and os.path.isfile(self.store.blob_path(fid)):
                name = rec["name"]
                if name in used:
                    stem, ext = os.path.splitext(name)
                    n = 2
                    while "%s (%d)%s" % (stem, n, ext) in used:
                        n += 1
                    name = "%s (%d)%s" % (stem, n, ext)
                used.add(name)
                recs.append((rec, name))
        if not recs:
            return self.send_text("没有可打包的文件（可能已过期）", 404)
        zip_name = time.strftime("中转站_%Y%m%d_%H%M") + ".zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", content_disposition(zip_name))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if self.command == "HEAD":
            return

        class Stream(io.RawIOBase):
            def __init__(inner, handler):
                inner.handler = handler

            def writable(inner):
                return True

            def write(inner, data):
                inner.handler.wfile.write(data)
                return len(data)

            def flush(inner):
                inner.handler.wfile.flush()

        stream = Stream(self)
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for rec, name in recs:
                info = zipfile.ZipInfo(name, date_time=time.localtime(rec.get("uploaded_at", time.time()))[:6])
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o644 << 16
                with open(self.store.blob_path(rec["id"]), "rb") as src, zf.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst, CHUNK)
        try:
            self.wfile.flush()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 二维码
# --------------------------------------------------------------------------- #
_QR_CACHE: dict = {}


def make_qr_png(url: str) -> bytes:
    if url in _QR_CACHE:
        return _QR_CACHE[url]
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=9, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111111", back_color="#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png = buf.getvalue()
    if len(_QR_CACHE) > 64:
        _QR_CACHE.clear()
    _QR_CACHE[url] = png
    return png


# --------------------------------------------------------------------------- #
# 启动
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="文件中转站")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--ttl-days", type=float, default=DEFAULT_TTL_DAYS)
    ap.add_argument("--max-mb", type=int, default=DEFAULT_MAX_MB)
    ap.add_argument("--janitor-interval", type=float, default=60.0, help="过期文件巡检间隔（秒）")
    ap.add_argument("--quiet", action="store_true", help="关闭逐条请求日志")
    args = ap.parse_args()

    Handler.store = Store(int(args.ttl_days * DAY), args.max_mb * 1024 * 1024)
    Handler.ttl_days = int(args.ttl_days) if float(args.ttl_days).is_integer() else args.ttl_days
    Handler.quiet = args.quiet

    purged = Handler.store.purge_expired()

    def janitor():
        while True:
            time.sleep(max(1.0, args.janitor_interval))
            try:
                n = Handler.store.purge_expired()
                if n:
                    print("[janitor] 清理过期文件 %d 个" % n, flush=True)
            except Exception as exc:
                print("[janitor] 出错: %r" % exc, flush=True)

    threading.Thread(target=janitor, daemon=True).start()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    print("[启动] 文件中转站 http://%s:%d  (有效期 %s 天, 单文件上限 %s)"
          % (args.host, args.port, args.ttl_days, human_size(Handler.store.max_bytes)), flush=True)
    for url in ["http://%s:%d" % (ip, args.port) for ip in local_ipv4()]:
        print("[启动] 局域网访问 %s  (手机请连同一 Wi-Fi)" % url, flush=True)
    if purged:
        print("[启动] 启动时清理了 %d 个过期文件" % purged, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[退出] 收到中断信号，正在关闭…", flush=True)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
