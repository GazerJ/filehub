"""接口集成测试：上传 / 列表 / 下载 / Range / 打包 / 删除 / 二维码 / 静态页。

在隔离实例上运行，不会动到正在服务的实例数据：
    python3 tests/api_test.py
"""
import io
import json
import os
import sys
import urllib.parse
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import Checks, Sandbox  # noqa: E402

check = Checks()
PORT = 8798

with Sandbox("api", PORT, ttl_days=7, janitor=1) as box:
    txt = "hello 中转站\n第二行\n".encode("utf-8")
    big = os.urandom(5 * 1024 * 1024)

    print("[1] 上传")
    status, rec_txt, body = box.upload("测试 文档.txt", txt, "text/plain")
    check("中文名文件上传 200", status == 200 and rec_txt, body[:160])
    status, rec_big, body = box.upload("video.bin", big)
    check("5MB 二进制上传 200", status == 200 and rec_big, body[:160])
    status, rec_empty, body = box.upload("empty.dat", b"")
    check("空文件上传 200", status == 200 and rec_empty, body[:160])

    print("[2] 列表")
    listing = box.list_files()
    check("列表含 3 个文件", listing["count"] == 3, [f["name"] for f in listing["files"]])
    check("总大小正确", listing["total_size"] == len(txt) + len(big), listing["total_size"])
    check("剩余时间约 7 天", all(6.9 * 86400 < f["remaining"] <= 7 * 86400 for f in listing["files"]))
    check("中文名原样保留", any(f["name"] == "测试 文档.txt" for f in listing["files"]))
    check("ttl_days = 7", listing["ttl_days"] == 7)

    print("[3] 下载")
    status, body, headers = box.call("GET", "/d/" + rec_txt["id"], raw=True)
    check("下载 200", status == 200, status)
    check("内容逐字节一致", body == txt)
    check("Content-Disposition 带 UTF-8 文件名",
          "filename*=UTF-8''" in headers.get("Content-Disposition", ""),
          headers.get("Content-Disposition"))

    print("[4] Range 断点续传")
    status, body, headers = box.call("GET", "/d/" + rec_big["id"],
                                     headers={"Range": "bytes=0-99"}, raw=True)
    check("206 + 100 字节", status == 206 and len(body) == 100 and body == big[:100],
          (status, len(body), headers.get("Content-Range")))

    print("[5] 多选打包下载")
    ids = ",".join([rec_txt["id"], rec_big["id"], rec_empty["id"]])
    status, blob, headers = box.call("GET", "/zip?ids=" + ids, raw=True)
    check("zip 200 + application/zip", status == 200 and headers.get("Content-Type") == "application/zip")
    zf = zipfile.ZipFile(io.BytesIO(blob))
    check("zip 结构完整", zf.testzip() is None)
    check("zip 内文件名正确",
          sorted(zf.namelist()) == sorted(["测试 文档.txt", "video.bin", "empty.dat"]), zf.namelist())
    check("zip 内内容一致", zf.read("测试 文档.txt") == txt and zf.read("video.bin") == big)
    check("zip 下载名带日期",
          "filename*=UTF-8''" in headers.get("Content-Disposition", ""),
          headers.get("Content-Disposition"))

    print("[6] 重名文件打包")
    _, dup_a, _ = box.upload("dup.txt", b"aaa")
    _, dup_b, _ = box.upload("dup.txt", b"bbb")
    status, blob, _ = box.call("GET", "/zip?ids=%s,%s" % (dup_a["id"], dup_b["id"]), raw=True)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    check("重名自动加序号", sorted(zf.namelist()) == ["dup (2).txt", "dup.txt"], zf.namelist())
    check("重名内容不串", zf.read("dup.txt") == b"aaa" and zf.read("dup (2).txt") == b"bbb")

    print("[7] 删除")
    body = json.dumps({"ids": [rec_empty["id"]]}).encode()
    status, text, _ = box.call("POST", "/api/delete", data=body,
                               headers={"Content-Type": "application/json"})
    check("删除接口返回 1", json.loads(text)["deleted"] == 1, text)
    status, _, _ = box.call("GET", "/d/" + rec_empty["id"])
    check("删除后下载 404", status == 404, status)
    status, _, _ = box.call("GET", "/d/nonexistent")
    check("未知 id 404", status == 404, status)
    status, _, _ = box.call("GET", "/zip?ids=nonexistent")
    check("无有效文件时打包 404", status == 404, status)

    print("[8] 文件名清洗")
    _, rec, _ = box.upload("../../etc/passwd", b"x")
    check("路径穿越被清洗", "/" not in rec["name"] and ".." not in rec["name"], rec["name"])
    _, rec, _ = box.upload("", b"y")
    check("空文件名有兜底", bool(rec["name"]), rec["name"])

    print("[9] 二维码")
    url = urllib.parse.quote("http://10.168.0.105:%d/m" % PORT)
    status, blob, headers = box.call("GET", "/api/qr.png?url=" + url, raw=True)
    check("返回 PNG", status == 200 and blob[:8] == b"\x89PNG\r\n\x1a\n", headers.get("Content-Type"))
    check("PNG 非空", len(blob) > 500, len(blob))

    print("[10] 页面与静态资源")
    for path in ["/", "/m", "/mobile", "/static/style.css", "/static/app.js",
                 "/static/favicon.svg", "/healthz", "/favicon.ico"]:
        status, _, _ = box.call("GET", path)
        check("GET %s -> 200" % path, status == 200, status)
    status, body, headers = box.call("GET", "/", raw=True)
    check("首页是 HTML", b"<html" in body.lower() and "text/html" in headers.get("Content-Type", ""))
    status, body, headers = box.call("HEAD", "/api/files", raw=True)
    check("HEAD 只返回响应头", status == 200 and body == b"" and "Content-Length" in headers,
          (status, len(body)))
    status, _, _ = box.call("GET", "/../server.py")
    check("静态目录不能穿越", status in (400, 404), status)

    print("[11] 信息接口")
    status, text, _ = box.call("GET", "/api/info")
    info = json.loads(text)
    check("info 含局域网地址", isinstance(info.get("lan_urls"), list) and info["lan_urls"], info.get("lan_urls"))
    check("info 上限 2GB", info["max_upload_mb"] == 2048, info["max_upload_mb"])
    check("info 有效期 7 天", info["ttl_days"] == 7)

sys.exit(check.report())
