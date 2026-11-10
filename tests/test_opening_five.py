"""合成数据验证6000字边界及前五章流程；不评价签约概率。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from test_narrative_quality import QualityFixture, TEXT, ns


class FirstFiveFixture(QualityFixture):
    def setUp(self):
        super().setUp()
        state = ns.load_state(self.root)
        state["config"].update(opening_five_required=True, target_chapters=150)
        ns.atomic_json(self.root / "state.json", state)

    def packet(self):
        lessons = []
        for key in ("a", "b"):
            lessons.append({"kind": "study", "id": "synthetic-" + key, "sha256": key * 64,
                            "lesson": "合成教材：行动改变选择空间。", "applicability": "合成角色能承担后果。",
                            "failure_conditions": "仅用于版本和证据测试。", "book_id": key * 24,
                            "source_sha256": key * 64, "feedback_origin": "model",
                            "source_origin": {"repository_url": "https://github.com/example/synthetic-library", "commit": key * 40,
                                              "path": key + ".txt", "blob_sha": key * 40, "size_bytes": 40000},
                            "evidence_sources": [{"chapter": 1, "start_line": 1, "end_line": 2,
                                                  "sha256": key * 64, "quote_sha256": key * 64}],
                            "source_scope": {"from_unit": 1, "to_unit": 5, "han_count": 12000, "level": "arc",
                                             "family_id": key * 24, "reading_basis": "reviewer_declared"}})
        return {"format": "novel-reference-packet-v1", "library_id": "synthetic-library", "library_revision": 1,
                "origin": {"repository_url": "https://github.com/example/synthetic-library", "commit": "c" * 40},
                "question": "合成前五章测试", "lessons": lessons}

    def opening_brief(self):
        path, brief = self.brief()
        packet = self.packet()
        brief["references"] = {"packet": packet, "packet_sha256": ns.digest(self.q.encoded(packet)),
                               "application": "合成角色交接钥匙，改变守门条件。", "originality": "合成事件只用于校验，不借用原作情节。"}
        if brief["chapter"] == 1:
            plan = brief["opening_five_plan"]
            for key in ("target_reader", "distinctive_premise", "reader_promise", "sustaining_conflict"):
                plan[key] = "合成输入，不代表真实选题评估。"
            for item in plan["chapters"]:
                for key in ("goal", "choice", "visible_result", "cost_or_reaction", "next_question"):
                    item[key] = f"第{item['chapter']}章合成计划字段。"
            for index, item in enumerate(plan["benchmarks"]):
                item.update(lesson_id=packet["lessons"][index]["id"], observation="合成观察", our_adaptation="合成用法", our_difference="合成差异")
        else:
            for key in ("goal", "choice", "visible_result", "cost_or_reaction", "next_question", "adaptation_to_actual"):
                brief["opening_focus"][key] = "合成当前章选择和后果，不作文学判断。"
        return path, brief

    def register_brief(self, changes=None):
        path, brief = self.opening_brief(); brief.update(changes or {})
        ns.atomic_json(path, brief)
        return self.q.check_brief(self.root, path, self.a), brief

    def prepare(self, n, text=TEXT, record=None):
        path, rec, value, report = super().prepare(n, text, record)
        quality = report["narrative_review"]
        ev = {"chapter": n, "sha256": ns.digest(text), "quote": text}
        quality["reference_use"].update(outcome="adapted", application_observed="合成用法", originality_review="合成原创检查", evidence=[dict(ev)])
        if n <= 5:
            opening = quality["opening_five"]
            opening.update(read_full_scope=True, previous_question_answered="合成已答问题", next_pressure="合成下一步压力")
            for check in opening["checks"].values():
                check.update(decision="pass", conclusion="只验证合成字段与证据绑定。", evidence=[dict(ev)])
            if n in (3, 5):
                sample = opening["sample_review"]
                sample["decision"] = "internal_ready_for_submission" if n == 5 else "continue"
                for key in ("platform_fit", "mainline", "first_arc_payoff", "character_relationships", "long_form_engine", "commercial_pitch", "remaining_weaknesses"):
                    sample[key] = "合成测试说明，不代表真实读者或平台反馈。"
                for item in sample["evidence"]:
                    item["quote"] = text if item["chapter"] == n else ns.inside(self.root, ns.load_state(self.root)["chapters"][str(item["chapter"])]["text_path"]).read_text()
        return path, rec, value, report


class FirstFiveTests(FirstFiveFixture):
    def test_uniform_6000_range_applies_to_first_five_and_later_chapters(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = json.loads((Path(__file__).parents[1] / "system_config.json").read_text())
            state = ns.init(Path(tmp) / "book", "合成新默认", config)
            self.assertEqual(state["config"]["target_chapters"], 150)
            self.assertEqual(state["config"]["target_han"], 900000)
            for n in (1, 2, 3, 4, 5, 6, 150):
                self.assertEqual(ns.chapter_han_range(state, n), (5500, 6500))

    def test_hard_length_boundaries_and_budget_are_not_just_documentation(self):
        state = ns.load_state(self.root); state["config"]["strict_length"] = True
        ns.atomic_json(self.root / "state.json", state)
        self.assertEqual(self.q.brief_skeleton(state, self.a)["scene_plan"][0]["target_han"], 6000)
        for count in (5499, 5500, 6000, 6500, 6501):
            text = TEXT + "测" * (count - ns.han_count(TEXT)); record = self.record(1, text)
            with self.subTest(count=count):
                if 5500 <= count <= 6500:
                    self.assertEqual(ns.validate_record(self.root, state, text, record), count)
                else:
                    with self.assertRaises(ns.WorkspaceError): ns.validate_record(self.root, state, text, record)

    def test_missing_five_chapter_plan_is_rejected_before_writing(self):
        _, brief = self.opening_brief(); brief.pop("opening_five_plan")
        with self.assertRaises(ns.WorkspaceError): self.q.validate_brief(ns.load_state(self.root), brief, self.a)

    def test_short_scope_scene_and_duplicate_book_versions_are_not_opening_benchmarks(self):
        for change in ("short", "scene", "same_family", "missing_scope"):
            _, brief = self.opening_brief(); packet = brief["references"]["packet"]
            if change == "short": packet["lessons"][0]["source_scope"]["han_count"] = 9999
            elif change == "scene": packet["lessons"][0]["source_scope"]["level"] = "scene"
            elif change == "same_family": packet["lessons"][1]["source_scope"]["family_id"] = packet["lessons"][0]["source_scope"]["family_id"]
            else: packet["lessons"][0].pop("source_scope")
            brief["references"]["packet_sha256"] = ns.digest(self.q.encoded(packet))
            with self.subTest(change=change), self.assertRaises(ns.WorkspaceError):
                self.q.validate_brief(ns.load_state(self.root), brief, self.a)

    def test_pending_cumulative_review_cannot_freeze_even_with_other_checks_filled(self):
        draft, rec, _, report = self.prepare(1)
        report["narrative_review"]["opening_five"]["read_full_scope"] = False
        with self.assertRaises(ns.WorkspaceError): self.gate(draft, rec, report)
        self.assertEqual(len(ns.load_state(self.root)["chapters"]), 0)

    def test_fifth_chapter_has_every_first_chapter_in_full_and_freezes_one_at_a_time(self):
        for n in range(1, 5): self.release(n)
        draft, rec, _, report = self.prepare(5)
        state = ns.load_state(self.root)
        _, coverage = self.q.reader_packet(self.root, state, TEXT, self.a)
        self.assertEqual(set(coverage), {str(n) for n in range(1, 6)})
        self.assertTrue(all(item["mode"] == "full_text" for item in coverage.values()))
        bad = copy.deepcopy(report); bad["narrative_review"]["opening_five"]["sample_review"]["decision"] = "platform_signed"
        with self.assertRaises(ns.WorkspaceError): self.gate(draft, rec, bad)
        bad = copy.deepcopy(report); bad["narrative_review"]["opening_five"]["sample_review"]["evidence"].pop(0)
        with self.assertRaises(ns.WorkspaceError): self.gate(draft, rec, bad)
        self.gate(draft, rec, report); ns.adopt(self.root, draft, rec)
        state = ns.load_state(self.root); self.assertEqual(len(state["serialization"]["frozen"]), 5)
        pin = state["opening_five_plan"]; ns.inside(self.root, pin["path"]).write_text("篡改合成方案")
        with self.assertRaises(ns.WorkspaceError): ns.verify_files(self.root, state)

    def test_next_focus_cannot_point_to_a_different_opening_plan(self):
        self.release(1); _, brief = self.opening_brief(); brief["opening_focus"]["plan_sha256"] = "0" * 64
        with self.assertRaises(ns.WorkspaceError): self.q.validate_brief(ns.load_state(self.root), brief, self.a)

    def test_legacy_book_length_rules_are_preserved_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = ns.init(Path(tmp) / "book", "合成旧书", {"target_chapters": 100, "chapter_han_min": 8000, "chapter_han_max": 10000})
            self.assertEqual(ns.chapter_han_range(state, 1), (8000, 10000))
            self.assertFalse(state["config"]["opening_five_required"])


if __name__ == "__main__": unittest.main()
