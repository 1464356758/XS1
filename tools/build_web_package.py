#!/usr/bin/env python3
"""导出含可选网络函数的个人端、只读代发端和空管理仓库包；不打包小说和凭证。"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' https://api.github.com https://raw.githubusercontent.com; img-src 'self' data:; font-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'"
HEADERS = "/*\n  Referrer-Policy: no-referrer\n  X-Content-Type-Options: nosniff\n  X-Frame-Options: DENY\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n  Content-Security-Policy: " + CSP + "\n"


def archive(out, files, kind):
    manifest = {"format": "novel-workspace-package-v1", "package": kind, "version": "1.4.0", "contains_novel_data": False,
                "files": {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}}
    files = dict(files, **{"PACKAGE_MANIFEST.json": (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            z.writestr(name, data)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(name)).hexdigest() == sha for name, sha in manifest["files"].items())
        assert not any(name.startswith(("book/chapters/", "book/records/", ".git/")) for name in z.namelist())
    return {"path": str(out), "bytes": out.stat().st_size, "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "files": len(files)}


def build(root=ROOT, out_dir=None):
    root = Path(root).resolve()
    out = Path(out_dir or root).resolve()
    out.mkdir(parents=True, exist_ok=True)
    dist = root / "web/dist"
    common = {"_headers": HEADERS.encode(), "netlify.toml": b'[build]\n  publish = "."\n[functions]\n  directory = "netlify/functions"\n[[redirects]]\n  from = "/api/github"\n  to = "/.netlify/functions/github"\n  status = 200\n  force = true\n'}
    relay = (root / "web/server/github-relay.mjs").read_text()
    owner = {p.name: p.read_bytes() for p in dist.iterdir() if p.is_file() and p.suffix in (".html", ".js", ".mjs", ".css", ".svg", ".webmanifest")}
    owner.update(common)
    owner["netlify/functions/github.mjs"] = (relay + '\nexport default request=>handleGitHubRelay(request);\n').encode()
    owner["部署说明.txt"] = (root / "docs/网页部署与首次使用.md").read_bytes()
    partner_names = ["reader.html", "reader.js", "reading-state.mjs", "search.mjs", "hub-core.mjs", "core.mjs", "github-transport.mjs", "query-model.mjs", "ui.mjs", "hub.css", "icon.svg"]
    partner = {name: (dist / name).read_bytes() for name in partner_names}
    partner["index.html"] = partner["reader.html"]
    partner.update(common)
    partner["netlify/functions/github.mjs"] = (relay + '\nexport default request=>handleGitHubRelay(request,{allowWrites:false});\n').encode()
    partner["部署说明.txt"] = "根目录和reader.html均为代发阅读页。作者在个人端保存此站的reader.html网址，再生成代发链接。无需GitHub写入凭证。代发码不是保密措施。\nNetlify使用Git连接部署或支持函数的CLI部署，让netlify/functions/github.mjs随站点部署。仅拖拽静态文件不会启用函数；请连同函数部署，避免Git版本读取受到浏览器跨域限制。详见个人端部署说明。\n".encode()
    manager = {"books.json": (root / "templates/管理清单.json").read_bytes(),
               "README.md": "# 小说更新管理仓库\n\n本包只有空清单，没有小说正文或凭证。上传到独立公开仓库并产生初始提交后，在个人端连接此仓库。小说清单与最近7天查询记录由个人端保存；查询无需预先生成报告。\n".encode()}
    return {"owner": archive(out / "个人管理端部署包.zip", owner, "owner"),
            "partner": archive(out / "代发端部署包.zip", partner, "partner"),
            "management": archive(out / "管理仓库初始化包.zip", manager, "management")}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir")
    args = p.parse_args()
    print(json.dumps(build(out_dir=args.out_dir), ensure_ascii=False, indent=2))
