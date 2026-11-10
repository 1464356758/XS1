"""使用临时合成原文，核验教材来源、练习顺序和正式写作入口。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import novel_library as library
import novel_state as workspace
import make_init_package

from test_narrative_quality import QualityFixture, ns


SOURCE = "第一章 合成前情\n甲要借一把伞，乙要守住店。\n第二章 合成选择\n甲答应修屋顶，乙才把伞借给她。\n第三章 合成后果\n雨停后甲回来修屋顶，发现乙已经搬走。\n"


class LibraryFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "library"
        library.initialize(self.root)
        self.source = self.base / "合成教材.txt"
        self.source.write_text(SOURCE, encoding="utf-8")
        self.book_id = library.import_book(self.root, self.source, platform="合成平台", genre="合成题材", signed=True)["book_id"]

    def evidence(self, chapter):
        item = library.read_chapter(self.root, self.book_id, chapter)
        return {key: item[key] for key in ("chapter", "start_line", "end_line", "sha256")} | {"quote": item["text"].splitlines()[-1]}

    def study(self):
        path = self.base / "study.json"
        library.study_request(self.root, self.book_id, "scene", 1, 2, path)
        value = workspace.read_json(path)
        value.update(decision="ready", read_full_scope=True, question="弱势者怎样求助",
                     observation="甲承担修屋顶的责任，乙交出伞。", interpretation="交换让求助有代价。",
                     technique="让主角承担对手不愿承担的风险。", applicability="双方确实有可交换的需求。",
                     failure_conditions="交换物对对手没有意义时失效。", terms=["求助", "交换代价"],
                     evidence=[self.evidence(2)])
        workspace.atomic_json(path, value)
        return path

    def attempt(self):
        task = self.base / "task.json"
        library.practice_request(self.root, self.book_id, 1, 2, "甲怎样让乙答应", task)
        draft = self.base / "draft.txt"
        draft.write_text("甲说了很多道理，乙把伞给她。", encoding="utf-8")
        return library.practice_save(self.root, task, draft)["attempt_id"]

    def review(self):
        attempt = self.attempt()
        path = self.base / "review.json"
        library.review_request(self.root, attempt, path)
        value = workspace.read_json(path)
        value.update(decision="ready", limitations="同上下文合成练习，未用真实读者。",
                     draft_choice="我用说理让对方轻易答应。", author_choice="原作用有实际价值的交换促成让步。",
                     gap="我的对手缺少让步动机。", lesson="让对方的决定源于自己的需求。",
                     applicability="双方有可以交换的需要。", failure_conditions="筹码对对方没有意义时失效。",
                     evidence=[self.evidence(2)])
        workspace.atomic_json(path, value)
        return path


class LibraryTests(LibraryFixture):
    def test_import_retry_preserves_source_and_does_not_claim_reading(self):
        result = library.import_book(self.root, self.source, platform="合成平台")
        self.assertEqual(result["book_id"], self.book_id)
        status = library.catalog_status(self.root)
        self.assertEqual(len(status["books"]), 1)
        self.assertEqual(status["books"][0]["declared_read_chapters"], 0)
        self.assertEqual(status["books"][0]["signing"]["status"], "author_reported")

    def test_chinese_utf16_and_gb18030_sources_share_normalized_identity(self):
        for encoding in ("utf-16", "gb18030"):
            path = self.base / (encoding + ".txt")
            path.write_bytes(SOURCE.replace("\n", "\r\n").encode(encoding))
            self.assertEqual(library.import_book(self.root, path)["book_id"], self.book_id)

    def test_preface_and_blank_prefix_keep_every_source_character(self):
        for text, expected in (("\n\n" + SOURCE, 3), ("合成前言\n" + SOURCE, 4)):
            _, chapters = library.chapter_ranges(text)
            self.assertEqual(len(chapters), expected)
            lines = text.splitlines(keepends=True)
            recovered = "".join("".join(lines[x["start_line"] - 1:x["end_line"]]) for x in chapters)
            self.assertEqual(recovered, text)

    def test_reading_budget_has_explicit_character_batches_for_long_lines(self):
        path = self.base / "long.txt"
        path.write_text("合成正文" * 10000, encoding="utf-8")
        book = library.import_book(self.root, path)["book_id"]
        with self.assertRaisesRegex(workspace.WorkspaceError, "预算"):
            library.read_chapter(self.root, book, 1, max_chars=50)
        result = library.read_chapter(self.root, book, 1, max_chars=50, start_char=30, end_char=70)
        self.assertEqual(len(result["text"]), 40)

    def test_pending_false_quote_and_incomplete_book_scope_are_rejected(self):
        path = self.study()
        value = workspace.read_json(path)
        value["decision"] = "pending"
        workspace.atomic_json(path, value)
        with self.assertRaises(workspace.WorkspaceError):
            library.study_check(self.root, path)
        value["decision"] = "ready"
        value["evidence"][0]["quote"] = "这句话从未出现在原文。"
        workspace.atomic_json(path, value)
        with self.assertRaisesRegex(workspace.WorkspaceError, "引文"):
            library.study_check(self.root, path)
        with self.assertRaisesRegex(workspace.WorkspaceError, "整本"):
            library.study_request(self.root, self.book_id, "book", 1, 2, self.base / "partial.json")

    def test_source_tampering_and_path_escape_fail_before_export(self):
        study_id = library.study_check(self.root, self.study())["study_id"]
        catalog = library.load(self.root)
        manifest, _ = library.book_data(self.root, catalog, self.book_id)
        source = self.root / manifest["text_path"]
        source.write_text(SOURCE + "合成篡改", encoding="utf-8")
        with self.assertRaisesRegex(workspace.WorkspaceError, "版本"):
            library.export_packet(self.root, [study_id], [], "求助", self.base / "bad.json")
        with self.assertRaises(workspace.WorkspaceError):
            workspace.inside(self.root, "../outside.txt")

    def test_learning_retry_is_idempotent_and_search_uses_matching_platform(self):
        path = self.study()
        first = library.study_check(self.root, path)["study_id"]
        self.assertEqual(first, library.study_check(self.root, path)["study_id"])
        self.assertEqual(library.catalog_status(self.root)["books"][0]["declared_read_chapters"], 2)
        matches = library.search(self.root, "求助 交换代价", platform="合成平台")
        self.assertEqual(matches["results"][0]["study_id"], first)
        self.assertFalse(library.search(self.root, "求助", platform="另一个平台")["results"])

    def test_existing_writer_lock_blocks_partial_import(self):
        before = (self.root / "catalog.json").read_bytes()
        with workspace.writer_lock(self.root):
            with self.assertRaises(workspace.WorkspaceError):
                library.import_book(self.root, self.source)
        self.assertEqual((self.root / "catalog.json").read_bytes(), before)

    def test_bookmark_resumes_partial_reading_without_claiming_finished_study(self):
        library.bookmark(self.root, self.book_id, 2, 4, 3, "本批读到第二章该行第三个字符，后半待读。")
        entry = library.catalog_status(self.root)["books"][0]
        self.assertEqual(entry["reading_position"]["next_char"], 3)
        self.assertEqual(entry["declared_read_chapters"], 0)
        with self.assertRaisesRegex(workspace.WorkspaceError, "字符"):
            library.bookmark(self.root, self.book_id, 2, 4, 90000, "无效位置")

    def test_review_requires_saved_attempt_and_evidence_from_the_answer(self):
        with self.assertRaises(workspace.WorkspaceError):
            library.review_request(self.root, "missing", self.base / "missing.json")
        path = self.review()
        value = workspace.read_json(path)
        value["evidence"] = [self.evidence(1)]
        workspace.atomic_json(path, value)
        with self.assertRaisesRegex(workspace.WorkspaceError, "范围"):
            library.review_check(self.root, path)

    def test_modified_attempt_or_review_cannot_be_reused(self):
        path = self.review()
        review_id = library.review_check(self.root, path)["review_id"]
        catalog = library.load(self.root)
        saved = self.root / catalog["reviews"][review_id]["path"]
        saved.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(workspace.WorkspaceError, "修改"):
            library.export_packet(self.root, [], [review_id], "求助", self.base / "packet.json")

    def test_packet_exports_lessons_and_pins_without_source_quotes_or_drafts(self):
        study_id = library.study_check(self.root, self.study())["study_id"]
        review_id = library.review_check(self.root, self.review())["review_id"]
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()
        git("init"); git("config", "user.name", "Synthetic Test"); git("config", "user.email", "test@example.invalid")
        git("remote", "add", "origin", "https://github.com/example/library")
        git("add", "."); git("commit", "-m", "Synthetic fixture")
        commit = git("rev-parse", "HEAD")
        out = self.base / "packet.json"
        library.export_packet(self.root, [study_id], [review_id], "怎样让对手自愿让步", out,
                              "https://github.com/example/library", commit)
        packet = library.validate_packet(workspace.read_json(out))
        self.assertEqual(len(packet["lessons"]), 2)
        self.assertNotIn("quote", out.read_text())
        self.assertNotIn("甲说了很多道理", out.read_text())
        with self.assertRaisesRegex(workspace.WorkspaceError, "提交"):
            library.export_packet(self.root, [study_id], [], "求助", self.base / "fake.json",
                                  "https://github.com/example/library", "a" * 40)
        with self.assertRaisesRegex(workspace.WorkspaceError, "提交"):
            library.export_packet(self.root, [study_id], [], "求助", self.base / "unversioned.json",
                                  "https://github.com/example/library")

    def test_library_archive_runs_its_normal_cli_after_extraction(self):
        archive = self.base / "library.zip"
        make_init_package.build_library(ROOT, archive)
        destination = self.base / "extracted"
        with zipfile.ZipFile(archive) as package:
            self.assertNotIn("catalog.json", package.namelist())
            self.assertFalse(any(name.startswith(("texts/", "book/")) for name in package.namelist()))
            package.extractall(destination)
        for command in (["init"], ["import", "--source", str(self.source)], ["catalog"]):
            result = subprocess.run([sys.executable, "tools/novel_library.py", "--root", ".", *command],
                                    cwd=destination, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)


class ReferenceBriefTests(QualityFixture):
    def packet(self):
        packet = {"format": library.PACKET_FORMAT, "library_id": "synthetic-library", "library_revision": 1,
                  "origin": {"repository_url": "https://github.com/example/library", "commit": "a" * 40},
                  "question": "怎样写交接钥匙的代价", "lessons": [
                      {"kind": "study", "id": "synthetic-study", "sha256": "b" * 64,
                       "lesson": "让交接改变下一场的选择。", "applicability": "双方交换了真实控制权。",
                       "feedback_origin": "model",
                       "failure_conditions": "交接后仍可随意开门时失效。", "book_id": "synthetic-book", "source_sha256": "c" * 64}]}
        path = Path(self.temp.name) / "packet.json"
        workspace.atomic_json(path, packet)
        return path, packet

    def test_bound_book_requires_references_through_normal_brief_entry(self):
        config = self.root.parent / "project_config.json"
        workspace.atomic_json(config, {"reference_library": {"repository_url": "https://github.com/example/library", "branch": "main"}})
        with self.assertRaisesRegex(ns.WorkspaceError, "参考库"):
            self.q.request_brief(self.root, self.root.parent / "no-ref.json", self.a)
        path, packet = self.packet()
        requested = self.root.parent / "requested.json"
        self.q.request_brief(self.root, requested, self.a, path)
        _, brief = self.brief()
        brief["references"] = workspace.read_json(requested)["references"]
        workspace.atomic_json(requested, brief)
        with self.assertRaisesRegex(ns.WorkspaceError, "原创安排"):
            self.q.check_brief(self.root, requested, self.a)
        brief["references"].update(application="甲要用交出钥匙换乙留下，代价是独自失去出门机会。",
                                    originality="甲因自己受伤选择交接，乙因此承担守门风险。")
        workspace.atomic_json(requested, brief)
        self.q.check_brief(self.root, requested, self.a)
        result = workspace.context(self.root, profile="writer")
        self.assertIn("乙因此承担守门风险", result)
        self.assertNotIn("synthetic-library", result)
        self.assertNotIn("synthetic-study", result)
        self.assertNotIn("https://github.com/example/library", result)
        with patch.object(self, "register_brief", return_value=(None, brief)):
            draft, rec, _, report = self.prepare(1)
        report["narrative_review"]["reference_use"].update(
            outcome="adapted", application_observed="合成用法检查，不代表文学效果。",
            originality_review="仅检查合成测试自身角色和后果。",
            evidence=[{"chapter": 1, "sha256": ns.digest(draft.read_text()), "quote": draft.read_text().split("。")[0] + "。"}])
        self.gate(draft, rec, report)
        ns.adopt(self.root, draft, rec)
        self.assertIn("1", ns.load_state(self.root)["serialization"]["frozen"])

    def test_reference_review_cannot_be_missing_pending_stale_or_without_current_evidence(self):
        _, packet = self.packet()
        _, brief = self.brief()
        brief["references"] = {"packet": packet, "packet_sha256": ns.digest(self.q.encoded(packet)),
                               "application": "交出钥匙改变下一场选择。", "originality": "自己的守门风险和交接原因。"}
        path = self.root.parent / "reference-brief.json"
        ns.atomic_json(path, brief); self.q.check_brief(self.root, path, self.a)
        with patch.object(self, "register_brief", return_value=(None, brief)):
            draft, rec, _, report = self.prepare(1)
        usage = report["narrative_review"]["reference_use"]
        with self.assertRaisesRegex(ns.WorkspaceError, "教材效果"):
            self.gate(draft, rec, report)
        usage.update(outcome="not_used", application_observed="合成任务中该教材不适合，没有沿用。",
                     originality_review="合成角色和后果独立设计。")
        usage["packet_sha256"] = "0" * 64
        with self.assertRaisesRegex(ns.WorkspaceError, "教材版本"):
            self.gate(draft, rec, report)
        usage["packet_sha256"] = brief["references"]["packet_sha256"]
        usage["evidence"] = [{"chapter": 1, "sha256": ns.digest(draft.read_text()), "quote": "正文没有这句话"}]
        with self.assertRaisesRegex(ns.WorkspaceError, "引文"):
            self.gate(draft, rec, report)

    def test_packet_change_and_wrong_library_are_rejected(self):
        path, packet = self.packet()
        _, brief = self.brief()
        brief["references"] = {"packet": packet, "packet_sha256": "wrong",
                               "application": "合成用法", "originality": "合成原创安排"}
        with self.assertRaisesRegex(ns.WorkspaceError, "版本"):
            self.q.validate_brief(workspace.load_state(self.root), brief, self.a)
        workspace.atomic_json(self.root.parent / "project_config.json", {"reference_library": {"repository_url": "https://github.com/other/library"}})
        with self.assertRaisesRegex(ns.WorkspaceError, "参考库"):
            self.q.request_brief(self.root, self.root.parent / "wrong-library.json", self.a, path)

    def test_invalid_packet_is_a_clean_cli_error(self):
        packet = self.root.parent / "invalid.json"
        workspace.atomic_json(packet, {"format": "wrong"})
        result = subprocess.run([sys.executable, str(ROOT / "tools/novel_state.py"), "--root", str(self.root),
                                 "brief-request", "--references", str(packet), "--out", str(self.root.parent / "out.json")],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("教材摘要格式", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
