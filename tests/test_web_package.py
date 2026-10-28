"""验证交付包的实际入口、依赖和小说隔离，不写入正式数据。"""
import json
import posixpath
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_web_package as package
import make_init_package as initial


class PackageTests(unittest.TestCase):
    def test_owner_and_partner_packages_have_independent_correct_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = package.build(ROOT, tmp)
            with zipfile.ZipFile(result["owner"]["path"]) as z:
                self.assertIn("hub.js", z.namelist())
                self.assertIn("reading-state.mjs", z.namelist())
                self.assertIn("search.mjs", z.namelist())
                self.assertIn("legacy.html", z.namelist())
                self.assertIn(b"hub.js", z.read("index.html"))
                self.assertIn("github-transport.mjs", z.namelist())
                self.assertIn("query-model.mjs", z.namelist())
                self.assertIn("netlify/functions/github.mjs", z.namelist())
            with zipfile.ZipFile(result["partner"]["path"]) as z:
                self.assertIn(b"reader.js", z.read("index.html"))
                self.assertNotIn("hub.js", z.namelist())
                self.assertNotIn("legacy.html", z.namelist())
                self.assertIn("hub-core.mjs", z.namelist())
                self.assertIn("reading-state.mjs", z.namelist())
                self.assertIn("search.mjs", z.namelist())
                self.assertIn("github-transport.mjs", z.namelist())
                self.assertIn("query-model.mjs", z.namelist())
                self.assertIn(b"allowWrites:false", z.read("netlify/functions/github.mjs"))
                self.assertFalse(any(name.startswith("book/") or name.startswith("qa-") for name in z.namelist()))

    def test_standalone_packages_contain_every_relative_module_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = package.build(ROOT, tmp)
            for kind in ("owner", "partner"):
                with zipfile.ZipFile(result[kind]["path"]) as archive:
                    names = set(archive.namelist())
                    for name in names:
                        if not name.endswith((".mjs", ".js")):
                            continue
                        for relative in re.findall(r"(?:from\s*|import\s*)['\"](\./[^'\"]+)['\"]", archive.read(name).decode()):
                            dependency = posixpath.normpath(posixpath.join(posixpath.dirname(name), relative))
                            self.assertIn(dependency, names, (kind, name, relative))

    def test_management_package_is_empty_and_contains_no_novel_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = package.build(ROOT, tmp)
            with zipfile.ZipFile(result["management"]["path"]) as z:
                data = json.loads(z.read("books.json"))
                self.assertEqual(data["books"], [])
                self.assertEqual(data["revision"], 0)
                self.assertNotIn("token", data)
                self.assertFalse(any(name.startswith("book/") for name in z.namelist()))

    def test_initialization_archive_contains_executable_checker_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "init.zip"
            initial.build(ROOT, out)
            with zipfile.ZipFile(out) as z:
                for name in ("tools/check_updates.mjs", "tools/query_today.mjs", "web/dist/today-query.mjs", "web/dist/query-model.mjs", "tools/daily_update.py", "web/dist/hub-core.mjs", "web/dist/core.mjs", "web/dist/github-transport.mjs", "web/server/github-relay.mjs", "docs/每日自动更新.md", "docs/旧书接入工作台.md"):
                    self.assertIn(name, z.namelist())
                self.assertNotIn("book/daily/active.json", z.namelist())
                z.extractall(Path(tmp) / "extracted")
            import shutil
            if shutil.which("node"):
                run = subprocess.run(["node", "tools/check_updates.mjs", "--help"], cwd=Path(tmp) / "extracted", capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                run = subprocess.run(["node", "tools/query_today.mjs", "--help"], cwd=Path(tmp) / "extracted", capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)

    def test_site_worker_serves_both_real_entries_and_the_relay_health(self):
        import build_site_worker
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site.mjs"
            build_site_worker.build(ROOT, out)
            if shutil.which("node"):
                script = """import assert from 'node:assert/strict';
const {default:worker}=await import(process.argv[1]);
for(const path of ['/', '/reader.html', '/reading-state.mjs', '/search.mjs', '/github-transport.mjs', '/query-model.mjs', '/today-query.mjs']){const r=await worker.fetch(new Request('https://novel.example'+path));assert.equal(r.status,200);if(path.endsWith('.html')||path==='/')assert.match(await r.text(),/novel-github-transport/);}
const h=await worker.fetch(new Request('https://novel.example/api/github?health=1'));assert.equal((await h.json()).protocol,1);
assert.equal((await worker.fetch(new Request('https://novel.example/unknown'))).status,404);
"""
                run = subprocess.run(["node", "--input-type=module", "-e", script, out.as_uri()], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
