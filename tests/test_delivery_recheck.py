"""End-to-end deliverable checks; all books and repositories are synthetic."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import make_init_package
import build_web_package
import build_site_worker
import online_state


class DeliveryRecheck(unittest.TestCase):
    def test_initial_package_rebuilds_itself_without_old_enrollment_or_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);first=tmp/'initial.zip';make_init_package.build(ROOT,first)
            with zipfile.ZipFile(first) as z:
                z.extractall(tmp/'new');names=z.namelist()
                self.assertFalse(any(n.startswith('docs/assets/') for n in names))
                self.assertNotIn('books.json',names)
                for n in names:
                    if n.startswith('docs/') and n.endswith('.md'):
                        self.assertNotIn('## 本次接入',z.read(n).decode())
                        self.assertNotIn('## 对现有小说的直接读取',z.read(n).decode())
                config=json.loads(z.read('project_config.json'))
                self.assertEqual(config['authority']['repository_url'],'')
                self.assertIsNone(json.loads(z.read('.automation/config.json'))['automation_id'])
                self.assertTrue(all(n.date_time==(1980,1,1,0,0,0) for n in z.infolist()))
            second=tmp/'second.zip';make_init_package.build(tmp/'new',second)
            self.assertEqual(first.read_bytes(),second.read_bytes())
            a=online_state.bootstrap(tmp/'new','https://github.com/example/new-book')
            self.assertEqual(a['phase'],'WAITING_PLATFORM')
            self.assertFalse(json.loads((tmp/'new/book/state.json').read_text())['chapters'])
            online_state.validate_index(tmp/'new')
            self.assertIsNone(json.loads((tmp/'new/.automation/config.json').read_text())['automation_id'])
            self.assertFalse((tmp/'new/book/daily/active.json').exists())

    def test_downloaded_package_matches_static_and_worker_delivery_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);initial=tmp/'initial.zip';make_init_package.build(ROOT,initial)
            builds=build_web_package.build(ROOT,tmp)
            with zipfile.ZipFile(builds['owner']['path']) as z:
                self.assertEqual(z.read('downloads/novel-init.zip'),initial.read_bytes())
                self.assertIn(b'./downloads/novel-init.zip',z.read('index.html'))
                version=json.loads((ROOT/'project_config.json').read_text())['workspace_version']
                self.assertEqual(json.loads(z.read('PACKAGE_MANIFEST.json'))['version'],version)
            worker=tmp/'worker.mjs';build_site_worker.build(ROOT,worker)
            partner=tmp/'partner.mjs';build_site_worker.build(ROOT,partner,partner=True)
            script="""import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const {default:w}=await import(process.argv[1]),{default:p}=await import(process.argv[2]);
const r=await w.fetch(new Request('https://example.test/downloads/novel-init.zip'));
assert.equal(r.status,200);assert.equal(r.headers.get('content-type'),'application/zip');
assert.deepEqual(Buffer.from(await r.arrayBuffer()),readFileSync(process.argv[3]));
const head=await w.fetch(new Request('https://example.test/downloads/novel-init.zip',{method:'HEAD'}));
assert.equal((await head.arrayBuffer()).byteLength,0);assert.equal(head.headers.get('x-content-sha256'),process.argv[4]);
assert.equal((await p.fetch(new Request('https://example.test/downloads/novel-init.zip'))).status,404);
"""
            run=subprocess.run(['node','--input-type=module','-e',script,worker.as_uri(),partner.as_uri(),str(initial),hashlib.sha256(initial.read_bytes()).hexdigest()],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
