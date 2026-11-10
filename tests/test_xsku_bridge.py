"""临时合成Git原文测试：网页分段、版本证据及真实参考库连接。"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import novel_library as library
import novel_state as workspace
import reference_bridge as bridge


class RepositoryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base / "library"; self.root.mkdir()
        self.repository = "https://github.com/example/synthetic-library"
        self.git("init"); self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("remote", "add", "origin", self.repository)
        self.source = self.root / "【合成测试小说-合成作者】-第2章"
        self.source.write_text('<b>www.example.invalid</b>\n<p>第一章 合成资源</p><p>甲搬来木料，乙守住炉子。</p>\n'
                               '<b>www.example.invalid</b>\n<p>第二章 合成交换</p><p>甲交出木料，乙让出炉边的空位。</p>\n')
        self.commit()
        indexed = library.sync_repository(self.root, self.repository)
        self.assertEqual(indexed["indexed_files"], 1)
        self.book_id = next(iter(library.load(self.root)["books"]))
        request = self.base / "study.json"
        library.study_request(self.root, self.book_id, "scene", 1, 2, request)
        value = workspace.read_json(request)
        chapter = library.read_chapter(self.root, self.book_id, 2)
        ev = {k: chapter[k] for k in ("chapter", "start_line", "end_line", "sha256")}
        ev["quote"] = "甲交出木料，乙让出炉边的空位。"
        value.update(decision="ready", read_full_scope=True, question="求助怎样有代价", observation="甲交木料。",
                     interpretation="乙获得需要的资源。", technique="把让步绑定到双方自己的需要。",
                     applicability="双方确有可交换的资源。", failure_conditions="一方没有需求时失效。",
                     terms=["求助", "交换"], evidence=[ev])
        workspace.atomic_json(request, value)
        self.study_id = library.study_check(self.root, request)["study_id"]
        self.commit()
        self.project = self.base / "project"; self.project.mkdir()
        workspace.atomic_json(self.project / "project_config.json", {"reference_library": {
            "repository_url": self.repository, "branch": "main", "library_id": library.load(self.root)["library_id"],
            "require_source_locations": True}})

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git("add", "."); self.git("commit", "-m", "Synthetic fixture")
        return self.git("rev-parse", "HEAD")


class XskuBridgeTests(RepositoryFixture):
    def test_extensionless_web_source_retains_page_ranges_and_source_hashes(self):
        data = library.read_chapter(self.root, self.book_id, 2)
        self.assertEqual(data["text"], "第二章 合成交换\n甲交出木料，乙让出炉边的空位。\n")
        raw = self.source.read_text()[data["raw_start_char"]:data["raw_end_char"]]
        self.assertIn("第二章", raw); self.assertNotIn("第一章", raw)
        manifest, _ = library.book_data(self.root, library.load(self.root), self.book_id)
        self.assertEqual(manifest["segmentation"], "html_reading_units")
        self.assertEqual(data["source_origin"]["blob_sha"], self.git("hash-object", self.source.name))

    def test_sync_is_idempotent_for_a_committed_source_version_and_ignores_untracked_input(self):
        (self.root / "【合成未提交-某人】").write_text("第一章 未提交")
        library.sync_repository(self.root, self.repository)
        self.assertEqual(len(library.load(self.root)["books"]), 1)
        self.assertEqual(library.record(self.root, library.load(self.root), "studies", self.study_id)["question"], "求助怎样有代价")

    def test_online_export_carries_locations_without_quotes_and_checks_real_commit(self):
        out = self.base / "packet.json"
        library.export_packet(self.root, [self.study_id], [], "交换", out, self.repository, self.git("rev-parse", "HEAD"))
        value = library.validate_packet(workspace.read_json(out))
        self.assertIn("source_origin", value["lessons"][0]); self.assertIn("evidence_sources", value["lessons"][0])
        scope = value["lessons"][0]["source_scope"]
        self.assertEqual(scope["from_unit"], 1)
        self.assertEqual(scope["to_unit"], 2)
        self.assertEqual(scope["level"], "scene")
        self.assertEqual(scope["han_count"], sum(workspace.han_count(library.read_chapter(self.root, self.book_id, n)["text"]) for n in (1, 2)))
        self.assertNotIn("甲交出木料", out.read_text())
        bad = copy.deepcopy(value); bad["lessons"][0]["source_origin"]["path"] = "../outside"
        with self.assertRaises(workspace.WorkspaceError): library.validate_packet(bad)

    def test_export_rejects_uncommitted_catalog_and_changed_original(self):
        commit = self.git("rev-parse", "HEAD")
        catalog = library.load(self.root); catalog["revision"] += 1
        workspace.atomic_json(self.root / "catalog.json", catalog)
        with self.assertRaisesRegex(workspace.WorkspaceError, "未提交"):
            library.export_packet(self.root, [self.study_id], [], "交换", self.base / "bad.json", self.repository, commit)
        self.git("checkout", "--", "catalog.json")
        self.source.write_text(self.source.read_text() + "合成修改")
        with self.assertRaisesRegex(workspace.WorkspaceError, "版本"):
            library.export_packet(self.root, [self.study_id], [], "交换", self.base / "changed.json", self.repository, commit)

    def test_platform_unknown_is_visible_but_never_reported_as_verified(self):
        found = library.search(self.root, "求助", platform="七猫")
        self.assertEqual(found["results"][0]["platform_match"], "unverified")
        catalog = library.load(self.root); catalog["books"][self.book_id]["platform"] = "另一个平台"
        workspace.atomic_json(self.root / "catalog.json", catalog)
        self.assertEqual(library.search(self.root, "求助", platform="七猫")["results"], [])

    def test_prepare_and_profile_use_current_checked_commit_without_modifying_the_library(self):
        before = (self.root / "catalog.json").read_bytes()
        out = self.base / "prepared.json"
        result = bridge.prepare(self.project, self.root, "求助", out, platform="七猫")
        self.assertEqual(result["source"]["commit"], self.git("rev-parse", "HEAD"))
        self.assertEqual(result["selected"][0]["platform"], "待核")
        snapshot = self.base / "profile.json"; bridge.profile(self.project, self.root, snapshot)
        self.assertFalse(workspace.read_json(snapshot)["declared_study_scope"]["full_library_read"])
        self.assertEqual(before, (self.root / "catalog.json").read_bytes())
        with self.assertRaisesRegex(workspace.WorkspaceError, "未找到"):
            bridge.prepare(self.project, self.root, "无法命中的问题", self.base / "nothing.json")

    def test_new_opening_does_not_treat_short_scene_studies_as_two_full_openings(self):
        workspace.init(self.project / "book", "合成新书", {"serial_mode": True, "narrative_review_required": True, "opening_five_required": True})
        with self.assertRaisesRegex(workspace.WorkspaceError, "开篇教材不足"):
            bridge.prepare(self.project, self.root, "求助", self.base / "opening.json")

    def test_two_committed_long_opening_studies_can_be_selected_with_measured_scope(self):
        for name in ("甲", "乙"):
            source = self.root / f"【合成开篇{name}-合成作者{name}】"
            source.write_text('<b>www.example.invalid</b>\n<p>第一章 合成开篇</p><p>' + "测试" * 6000 +
                              f'</p>\n<b>www.example.invalid</b>\n<p>第二章 合成后果</p><p>{name}决定守门。</p>\n')
        self.commit(); library.sync_repository(self.root, self.repository)
        catalog = library.load(self.root)
        long_books = [key for key, entry in catalog["books"].items() if entry["title"].startswith("合成开篇")]
        for index, book in enumerate(long_books):
            request = self.base / f"arc-{index}.json"
            library.study_request(self.root, book, "arc", 1, 2, request)
            value = workspace.read_json(request); chapter = library.read_chapter(self.root, book, 2)
            evidence = {key: chapter[key] for key in ("chapter", "start_line", "end_line", "sha256")}
            evidence["quote"] = chapter["text"].splitlines()[-1]
            value.update(decision="ready", read_full_scope=True, question="开篇选择怎样产生后果", observation="合成场景中的守门决定。",
                         interpretation="合成输入用于验证范围。", technique="合成写法", applicability="只验证工程连接。",
                         failure_conditions="不验证文学质量。", terms=["开篇", "选择"], evidence=[evidence])
            workspace.atomic_json(request, value); library.study_check(self.root, request)
        self.commit()
        workspace.init(self.project / "book", "合成新书", {"serial_mode": True, "narrative_review_required": True, "opening_five_required": True})
        out = self.base / "opening-packet.json"; bridge.prepare(self.project, self.root, "开篇 选择", out)
        packet = library.validate_packet(workspace.read_json(out))
        self.assertEqual(len(packet["lessons"]), 2)
        self.assertEqual(len({item["source_scope"]["family_id"] for item in packet["lessons"]}), 2)
        self.assertTrue(all(item["source_scope"]["han_count"] >= 10000 and item["source_scope"]["level"] == "arc" for item in packet["lessons"]))


if __name__ == "__main__": unittest.main()
