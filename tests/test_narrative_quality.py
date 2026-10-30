"""只用临时合成文本测证据与恢复边界，不自动给真实稿件判通过。"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from unittest.mock import patch

from test_novel_state import WorkspaceFixture, ns


TEXT = "甲把钥匙交给乙。乙决定独自守门。"
SOURCE = Path(__file__).resolve().parents[1]


class QualityFixture(WorkspaceFixture):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "book"
        ns.init(self.root, "合成机制测试书", {"strict_length": False, "serial_mode": True, "narrative_review_required": True})
        self.q = ns.narrative_module(); self.a = ns.serial_api(); self.serial = ns.serial_module()
        for kind, content in (("canon", "CANON_SECRET：未来答案只在作者资料里。"), ("roadmap", "ROADMAP_SECRET：未写出的未来计划。")):
            file = Path(self.temp.name) / (kind + ".md"); file.write_text(content, encoding="utf-8")
            ns.set_input(self.root, kind, file, "合成测试初始化", ns.load_state(self.root)["revision"])

    def brief(self, changes=None):
        state = ns.load_state(self.root)
        brief = self.q.brief_skeleton(state, self.a)
        brief.update(decision="ready", writer_brief="甲必须决定把钥匙交给谁，并承担失去开门机会的后果。",
                     hard_boundaries=["钥匙只有一把，交出后不能无故出现在甲手中。"],
                     reader_promise="看到选择的实际后果。", scene_plan=[{"purpose": "交接钥匙并改变守门选择", "target_han": 9000}],
                     history_queries=["钥匙"] if state["chapters"] else [])
        brief.update(changes or {})
        path = Path(self.temp.name) / "brief.json"; ns.atomic_json(path, brief)
        return path, brief

    def register_brief(self, changes=None):
        path, brief = self.brief(changes)
        return self.q.check_brief(self.root, path, self.a), brief

    def prepare(self, n, text=TEXT, record=None):
        self.register_brief()
        record = record or self.record(n, text, stage=f"S{(n-1)//10+1:02d}")
        path = Path(self.temp.name) / "draft.txt"; path.write_text(text, encoding="utf-8")
        recpath = Path(self.temp.name) / "record.json"; ns.atomic_json(recpath, record)
        ns.candidate(self.root, n, path)
        state = ns.load_state(self.root)
        report = self.serial.skeleton(self.root, state, text, record, self.a)
        ev = {"chapter": n, "sha256": ns.digest(text), "quote": text}
        report.update(decision="release", read_full_text=True, blocking_issues=[],
                      reader_reason_to_continue="仅测试结构", consequence="仅测试后果字段", ending_runway="仅测试收束字段")
        for check in report["checks"].values():
            check.update(decision="pass", conclusion="合成证据测试，不评价文学质量", evidence=[dict(ev)])
        for item in report["comparison"]:
            body = ns.inside(self.root, state["chapters"][str(item["chapter"])]["text_path"]).read_text(encoding="utf-8")
            item.update(quote=body[:120], difference="只测试比较证据格式")
        for item in report["future_window"]:
            item.update(goal="测试目标", change="测试变化", ending_question="测试待解")
        if n == 1:
            for cue in report["opening"].values():
                cue.update(quote=text.split("。")[0]+"。", why="只测试引文位置")
        if "checkpoint" in report:
            report["checkpoint"].update(read_mode="full_text_batches", decision="continue", **{k: "合成覆盖机制测试" for k in self.serial.CONCLUSIONS})
        quality = report["narrative_review"]
        quality["actual_scenes"] = [{"event": "合成事件", "choice": "合成选择", "change": "合成变化", "evidence": [dict(ev)]}]
        quality["plan_comparison"] = "合成测试：只验证字段和来源，未判断情节是否好看。"
        quality["reader"].update(mode="same_context_approximation", limitation="测试没有独立读者，不能验证阅读效果。",
                                  understanding="合成理解结论", information_load="合成信息结论", promise_delivery="合成兑现结论", evidence=[dict(ev)])
        for check in quality["character_causality"].values():
            check.update(status="reviewed", conclusion="合成判断，不验证文学效果", evidence=[dict(ev)])
        quality["history"]["no_match_reason"] = "合成压力测试不作真实语义比较，不能用于作品审稿。"
        quality["reader_updates"] = [{"kind": "observed", "statement": "此处只回顾已经出现在合成正文中的交接。", "evidence": [dict(ev)]}]
        quality["reader_update_note"] = "合成读者回顾，不包含作者未来计划。"
        return path, recpath, record, report

    def gate(self, path, recpath, report):
        out = Path(self.temp.name) / "release.json"; ns.atomic_json(out, report)
        return self.serial.check(self.root, path, recpath, out, self.a)

    def release(self, n, text=TEXT, record=None):
        path, recpath, _, report = self.prepare(n, text, record)
        self.gate(path, recpath, report)
        return ns.adopt(self.root, path, recpath)


class NarrativeQualityTests(QualityFixture):
    def test_new_release_cannot_skip_brief_or_pending_review(self):
        record = self.record(1, TEXT); path = Path(self.temp.name) / "draft.txt"; path.write_text(TEXT, encoding="utf-8")
        ns.candidate(self.root, 1, path)
        with self.assertRaises(ns.WorkspaceError):
            self.serial.skeleton(self.root, ns.load_state(self.root), TEXT, record, self.a)
        self.register_brief()
        report = self.serial.skeleton(self.root, ns.load_state(self.root), TEXT, record, self.a)
        self.assertEqual(report["narrative_review"]["reader"]["mode"], "pending")
        with self.assertRaises(ns.WorkspaceError):
            self.q.validate(self.root, ns.load_state(self.root), TEXT, record, report["narrative_review"], self.a)

    def test_pending_cross_book_and_wrong_budget_briefs_rejected(self):
        path, brief = self.brief(); brief["decision"] = "pending"; ns.atomic_json(path, brief)
        with self.assertRaises(ns.WorkspaceError): self.q.check_brief(self.root, path, self.a)
        path, brief = self.brief(); brief["book_id"] = "another-book"; ns.atomic_json(path, brief)
        with self.assertRaises(ns.WorkspaceError): self.q.check_brief(self.root, path, self.a)
        state = ns.load_state(self.root); state["config"]["strict_length"] = True; ns.atomic_json(self.root / "state.json", state)
        path, _ = self.brief({"scene_plan": [{"purpose": "有效场景", "target_han": 100}]})
        with self.assertRaises(ns.WorkspaceError): self.q.check_brief(self.root, path, self.a)

    def test_writer_packet_uses_clean_brief_without_control_or_future(self):
        self.register_brief()
        author = ns.context(self.root)
        writer = ns.context(self.root, profile="writer")
        self.assertIn("CANON_SECRET", author)
        self.assertIn("钥匙只有一把", writer)
        for marker in ("CANON_SECRET", "ROADMAP_SECRET", "book_id", "base_revision", "text_sha256"):
            self.assertNotIn(marker, writer)

    def test_reader_packet_never_reads_raw_summary_or_author_inputs(self):
        rec = self.record(1, TEXT); rec["summary"] = "SUMMARY_SECRET：章后记录中的未来答案。"
        self.release(1, record=rec)
        draft = Path(self.temp.name) / "next.txt"; draft.write_text("乙把门推开。", encoding="utf-8")
        packet = ns.context(self.root, profile="reader", text_path=draft)
        self.assertIn(TEXT, packet)
        for marker in ("CANON_SECRET", "ROADMAP_SECRET", "SUMMARY_SECRET"):
            self.assertNotIn(marker, packet)

    def test_changed_brief_invalidates_gate_without_resetting_repairs(self):
        path, recpath, _, report = self.prepare(1); self.gate(path, recpath, report)
        state = ns.load_state(self.root); task = copy.deepcopy(state["tasks"]["1"])
        self.register_brief({"reader_promise": "另一份测试体验，须重新检查"})
        self.assertEqual(ns.load_state(self.root)["tasks"]["1"], task)
        with self.assertRaises(ns.WorkspaceError): ns.adopt(self.root, path, recpath)

    def test_new_brief_does_not_reset_a_repair_task(self):
        path, _, _, _ = self.prepare(1)
        path.write_text("甲留下钥匙。", encoding="utf-8")
        ns.candidate(self.root, 1, path, request="合成局部修订", repairing=True)
        before = copy.deepcopy(ns.load_state(self.root)["tasks"]["1"])
        self.register_brief()
        after = ns.load_state(self.root)["tasks"]["1"]
        self.assertEqual(before, after)
        self.assertEqual(after["repairs"], 1)

    def test_route_change_invalidates_brief_before_writing(self):
        self.register_brief()
        path = Path(self.temp.name) / "new-plan.md"; path.write_text("新的未来计划。", encoding="utf-8")
        ns.set_input(self.root, "roadmap", path, "合成路线调整", ns.load_state(self.root)["revision"])
        with self.assertRaises(ns.WorkspaceError): ns.context(self.root, profile="writer")

    def test_reverse_outline_requires_actual_current_prose_evidence(self):
        path, recpath, _, report = self.prepare(1)
        report["narrative_review"]["actual_scenes"][0]["evidence"][0]["quote"] = "只在计划中发生的事件"
        with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, report)

    def test_reader_modes_and_unresolved_understanding_fail_closed(self):
        path, recpath, _, report = self.prepare(1)
        bad = copy.deepcopy(report); bad["narrative_review"]["reader"]["mode"] = "real_readers_verified"
        with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, bad)
        for severity in ("must_fix", "verify"):
            bad = copy.deepcopy(report)
            bad["narrative_review"]["reader"]["issues"] = [{"severity": severity, "status": "open", "reason": "合成理解缺口", "evidence": {"chapter": 1, "sha256": ns.digest(TEXT), "quote": TEXT}}]
            with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, bad)

    def test_optional_dialogue_and_style_suggestion_do_not_force_rewrite(self):
        path, recpath, _, report = self.prepare(1)
        report["narrative_review"]["character_causality"]["dialogue"] = {"status": "not_applicable", "conclusion": "本合成场景没有对白，不强行插入。", "evidence": []}
        report["narrative_review"]["reader"]["issues"] = [{"severity": "suggestion", "status": "open", "reason": "可选表达偏好", "evidence": {"chapter": 1, "sha256": ns.digest(TEXT), "quote": TEXT}}]
        self.gate(path, recpath, report); ns.adopt(self.root, path, recpath)
        self.assertEqual(ns.status(self.root)["frozen_chapters"], 1)
        self.assertEqual(ns.status(self.root)["published_chapters"], 0)

    def test_history_search_reaches_beyond_recent_three(self):
        rec = self.record(1, TEXT); rec["summary"] = "旧桥段：当众借据逼退对手。"
        self.release(1, record=rec)
        for n in range(2, 7): self.release(n)
        state = ns.load_state(self.root)
        result = self.q.search_history(self.root, state, "借据 逼退", 5, 4, self.a)
        self.assertEqual(result["indexed_records"], 6)
        self.assertEqual(result["scanned_records"], 3)
        self.assertEqual([x["chapter"] for x in result["candidates"]], [1])
        self.assertIn("不是语义去重", result["note"])

    def test_stale_history_and_fabricated_comparison_rejected(self):
        self.release(1)
        path, recpath, _, report = self.prepare(2)
        bad = copy.deepcopy(report); bad["narrative_review"]["history"]["index_sha256"] = "stale"
        with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, bad)
        state = ns.load_state(self.root)
        report["narrative_review"]["history"]["comparisons"] = [{"similarity": "合成相似", "difference": "合成差异",
            "source": {"chapter": 1, "sha256": state["chapters"]["1"]["text_sha256"], "quote": "伪造旧章引文"},
            "current_evidence": {"chapter": 2, "sha256": ns.digest(TEXT), "quote": TEXT}}]
        with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, report)

    def test_reader_claim_stays_a_claim_in_older_recap(self):
        path, recpath, _, report = self.prepare(1)
        report["narrative_review"]["reader_updates"][0].update(kind="claim", statement="人物说法，不等于世界真相。")
        self.gate(path, recpath, report); ns.adopt(self.root, path, recpath)
        for n in range(2, 5): self.release(n)
        body, coverage = self.q.reader_packet(self.root, ns.load_state(self.root), "下一章合成候选。", self.a)
        self.assertEqual(coverage["1"]["mode"], "reader_recap")
        self.assertIn('"kind": "claim"', body)
        self.assertNotIn("CANON_SECRET", body)

    def test_reader_recap_rejects_invented_or_future_evidence(self):
        path, recpath, _, report = self.prepare(1)
        report["narrative_review"]["reader_updates"][0]["evidence"][0]["chapter"] = 2
        with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, report)

    def test_production_phrases_and_annotations_cannot_be_silently_deleted(self):
        text = "她知道第十五章完成的是退款核查。【钩】"
        path, recpath, _, report = self.prepare(1, text)
        self.assertEqual(len(report["narrative_review"]["surface_findings"]), 2)
        with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, report)
        report["narrative_review"]["surface_findings"] = []
        with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, report)

    def test_legitimate_ids_are_not_blanket_banned_and_story_context_is_explicit(self):
        self.assertEqual(self.q.surface_scan("她知道老道士把P11号零件交给R03，章鱼还在水里。"), [])
        text = "屏幕显示text_sha256字段。"
        path, recpath, _, report = self.prepare(1, text)
        self.assertEqual(len(report["narrative_review"]["surface_findings"]), 1)
        for finding in report["narrative_review"]["surface_findings"]:
            finding.update(decision="story_context", reason="合成技术小说中的屏幕字段，属于人物实际看到的内容。")
        self.gate(path, recpath, report)

    def test_chinese_adjacent_control_fields_are_detected_without_english_word_boundaries(self):
        findings = self.q.surface_scan("她看到state_revision增加，text_sha256仍未登记。")
        self.assertEqual([x["quote"] for x in findings], ["state_revision", "text_sha256"])

    def test_budget_overflow_and_partial_reader_do_not_claim_full_history(self):
        self.release(1); self.register_brief()
        draft = Path(self.temp.name) / "next.txt"; draft.write_text(TEXT, encoding="utf-8")
        with self.assertRaises(ns.WorkspaceError): ns.context(self.root, budget=10, profile="writer")
        with self.assertRaises(ns.WorkspaceError): ns.context(self.root, budget=10, profile="reader", text_path=draft)
        packet = ns.context(self.root, profile="reader", text_path=draft, history_from=1, history_to=1)
        self.assertIn("其他前文尚未在本包覆盖", packet)

    def test_context_output_cannot_overwrite_frozen_prose(self):
        self.release(1)
        item = ns.load_state(self.root)["chapters"]["1"]
        target = ns.inside(self.root, item["text_path"])
        draft = Path(self.temp.name) / "next.txt"; draft.write_text(TEXT, encoding="utf-8")
        run = subprocess.run([sys.executable, str(SOURCE / "tools/novel_state.py"), "--root", str(self.root), "context", "--profile", "reader", "--text", str(draft), "--out", str(target)], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), TEXT)

    def test_snapshot_contains_new_runtime_and_retains_freeze(self):
        self.release(1); archive = Path(self.temp.name) / "snapshot.zip"
        ns.snapshot(self.root, archive)
        restored = Path(self.temp.name) / "restored"
        with zipfile.ZipFile(archive) as z:
            self.assertIn("SYSTEM/tools/narrative_quality.py", z.namelist())
            self.assertIn("SYSTEM/docs/写作与叙事检查.md", z.namelist())
            z.extractall(restored)
        run = subprocess.run([sys.executable, str(restored / "SYSTEM/tools/novel_state.py"), "--root", str(restored), "status"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)["narrative_review_required"])
        with self.assertRaises(ns.WorkspaceError): ns.candidate(restored, 1, restored / ns.load_state(restored)["chapters"]["1"]["text_path"], "edit", "试图修改冻结章")

    def test_100_chapter_new_profile_stage_and_reader_state_flow(self):
        # 相同短文本只验证100章状态、阶段、回顾增长；不验证小说质量或90万字文学稳定性。
        for n in range(1, 101): self.release(n)
        state = ns.load_state(self.root)
        self.assertEqual(ns.status(self.root)["frozen_chapters"], 100)
        self.assertEqual(ns.status(self.root)["published_chapters"], 0)
        self.assertEqual(ns.status(self.root)["reviewed_until"], 100)
        self.assertEqual(len(state["writing_briefs"]), 100)
        self.assertTrue(all(x["used"] for x in state["serialization"]["gates"].values()))
        with self.assertRaises(ns.WorkspaceError): self.register_brief()

    def test_profile_configuration_rejects_silent_nonserial_or_string_flags(self):
        for cfg in ({"serial_mode": False, "narrative_review_required": True}, {"serial_mode": True, "narrative_review_required": "true"}):
            with self.assertRaises(ns.WorkspaceError): ns.init(Path(self.temp.name) / "bad", "错误配置测试", cfg)

    def test_empty_older_reader_recap_falls_back_to_actual_prose(self):
        old_text = "甲把唯一的铜钥匙交给乙，自己留在无门的院外。"
        path, recpath, _, report = self.prepare(1, old_text)
        report["narrative_review"]["reader_updates"] = []
        report["narrative_review"]["reader_update_note"] = "合成用例故意不生成回顾，后续须保留正文。"
        self.gate(path, recpath, report); ns.adopt(self.root, path, recpath)
        for n in range(2, 5): self.release(n)
        body, coverage = self.q.reader_packet(self.root, ns.load_state(self.root), "新的合成候选。", self.a)
        self.assertIn(old_text, body)
        self.assertEqual(coverage["1"]["mode"], "full_text")

    def test_context_rejects_changes_during_initial_file_verification(self):
        self.register_brief()
        draft = Path(self.temp.name) / "next.txt"; draft.write_text(TEXT, encoding="utf-8")
        initial = copy.deepcopy(ns.load_state(self.root))
        verify = ns.verify_files
        for profile in ("author", "writer", "reader"):
            for field in ("revision", "title"):
                with self.subTest(profile=profile, changed_field=field):
                    ns.atomic_json(self.root / "state.json", initial)
                    def change_after_loading(root, state):
                        verify(root, state)
                        current = ns.load_state(root)
                        current[field] = current[field] + 1 if field == "revision" else "另一个合成标题"
                        ns.atomic_json(Path(root) / "state.json", current)
                    with patch.object(ns, "verify_files", side_effect=change_after_loading):
                        with self.assertRaises(ns.WorkspaceError):
                            ns.context(self.root, profile=profile, text_path=draft if profile == "reader" else None)

    def test_reader_context_rejects_draft_change_while_building_packet(self):
        draft = Path(self.temp.name) / "next.txt"; draft.write_text(TEXT, encoding="utf-8")
        packet = self.q.reader_packet
        def change_after_reading(*args, **kwargs):
            result = packet(*args, **kwargs)
            draft.write_text(TEXT + "有人在门外敲了三下。", encoding="utf-8")
            return result
        with patch.object(self.q, "reader_packet", side_effect=change_after_reading):
            with self.assertRaises(ns.WorkspaceError): ns.context(self.root, profile="reader", text_path=draft)

    def test_reader_output_cannot_overwrite_its_draft_input(self):
        draft = Path(self.temp.name) / "draft.txt"; draft.write_text(TEXT, encoding="utf-8")
        run = subprocess.run([sys.executable, str(SOURCE / "tools/novel_state.py"), "--root", str(self.root), "context", "--profile", "reader", "--text", str(draft), "--out", str(draft)], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(draft.read_text(encoding="utf-8"), TEXT)

    def test_punctuation_only_queries_do_not_count_as_history_search(self):
        with self.subTest(stage="brief"):
            path, _ = self.brief({"history_queries": ["，; ；"]})
            with self.assertRaises(ns.WorkspaceError): self.q.check_brief(self.root, path, self.a)
        self.release(1)
        with self.subTest(stage="search"):
            with self.assertRaises(ns.WorkspaceError): self.q.search_history(self.root, ns.load_state(self.root), "，; ；", 5, None, self.a)
        path, recpath, _, report = self.prepare(2)
        report["narrative_review"]["history"]["queries"] = ["，; ；"]
        with self.subTest(stage="release"):
            with self.assertRaises(ns.WorkspaceError): self.gate(path, recpath, report)
