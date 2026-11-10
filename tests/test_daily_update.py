"""所有正文均在临时目录中合成，只验证每日任务和跨语言证据边界。"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from test_novel_state import WorkspaceFixture, ns
import test_serial_release as serial_fixtures

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import daily_update as daily


class DailyTests(WorkspaceFixture):
    prepare = serial_fixtures.SerialTests.prepare
    gate = serial_fixtures.SerialTests.gate
    release = serial_fixtures.SerialTests.release

    def setUp(self):
        super().setUp()
        self.project = self.root.parent
        self.serial = ns.serial_module()
        self.a = ns.serial_api()
        self.serial.enable(self.root, "合成测试启用", ns.load_state(self.root)["revision"], self.a)

    def test_begin_does_not_change_official_state_or_repair_count(self):
        old = ns.load_state(self.root)
        task = daily.begin(self.project)
        self.assertEqual(task["action"], "started")
        self.assertEqual(task["chapter"], 1)
        self.assertEqual(old, ns.load_state(self.root))

    def test_running_target_is_not_automatically_stolen(self):
        first = daily.begin(self.project)
        again = daily.begin(self.project)
        self.assertEqual(again["action"], "verify_in_progress")
        self.assertEqual(again["run_id"], first["run_id"])

    def test_explicit_resume_keeps_target_baseline_and_old_attempt(self):
        first = daily.begin(self.project)
        daily.block(self.project, first["run_id"], "合成测试中断")
        resumed = daily.begin(self.project, resume_stopped=True)
        self.assertEqual(resumed["action"], "resumed")
        self.assertEqual(resumed["chapter"], first["chapter"])
        self.assertEqual(resumed["baseline_fingerprint"], first["baseline_fingerprint"])
        self.assertNotEqual(resumed["run_id"], first["run_id"])
        self.assertEqual(resumed["attempts"][0]["run_id"], first["run_id"])

    def test_stale_run_cannot_finish_or_block_after_resume(self):
        first = daily.begin(self.project)
        daily.begin(self.project, resume_stopped=True)
        with self.assertRaises(daily.ns.WorkspaceError):
            daily.block(self.project, first["run_id"], "旧执行")
        with self.assertRaises(daily.ns.WorkspaceError):
            daily.finish(self.project, first["run_id"])

    def test_resume_stops_when_old_chapter_freeze_state_is_disabled(self):
        self.release(1)
        task = daily.begin(self.project)
        state = ns.load_state(self.root)
        state["serialization"]["enabled"] = False
        ns.atomic_json(self.root / "state.json", state)
        before = (self.root / "daily/active.json").read_bytes()
        for operation in (lambda: daily.begin(self.project, resume_stopped=True),
                          lambda: daily.finish(self.project, task["run_id"])):
            with self.assertRaisesRegex(daily.ns.WorkspaceError, "冻结状态缺失或已关闭"):
                operation()
            self.assertEqual((self.root / "daily/active.json").read_bytes(), before)
        self.assertEqual(daily.active_record(self.root)["chapter"], 2)
        self.assertEqual(len(ns.load_state(self.root)["chapters"]), 1)

    def test_no_receipt_before_real_adoption(self):
        task = daily.begin(self.project)
        with self.assertRaises(daily.ns.WorkspaceError):
            daily.finish(self.project, task["run_id"])
        self.assertFalse((self.root / "daily" / (daily.date_of(daily.stamp()) + ".json")).exists())

    def test_completed_request_is_idempotent_and_new_request_can_continue_same_day(self):
        task = daily.begin(self.project, trigger_id="synthetic_request_001")
        self.release(1)
        receipt = daily.finish(self.project, task["run_id"])
        again = daily.begin(self.project, trigger_id="synthetic_request_001")
        self.assertEqual(again["action"], "already_completed")
        self.assertEqual(again["chapter"], 1)
        self.assertEqual(receipt["completed_at"], ns.load_state(self.root)["chapters"]["1"]["adopted_at"])
        self.assertEqual(daily.finish(self.project, task["run_id"])["body_sha256"], receipt["body_sha256"])
        self.assertEqual(daily.begin(self.project, trigger_id="synthetic_request_002")["chapter"], 2)

    def test_missing_receipt_is_recovered_from_adoption_time(self):
        daily.begin(self.project)
        self.release(1)
        recovered = daily.begin(self.project)
        self.assertEqual(recovered["action"], "recovered_completion")
        self.assertEqual(recovered["chapter"], 1)

    def test_three_chapters_same_day_preserve_all_receipts_and_old_retry(self):
        receipts = []
        for chapter in range(1, 4):
            task = daily.begin(self.project, trigger_id=f"synthetic_trigger_{chapter:03d}")
            self.assertEqual(task["chapter"], chapter)
            self.release(chapter)
            result = daily.finish(self.project, task["run_id"])
            receipts.append(result)
            self.assertEqual(result["date"], receipts[0]["date"])
        self.assertEqual(len({x["receipt_path"] for x in receipts}), 3)
        legacy = ns.read_json(self.root / "daily" / (receipts[0]["date"] + ".json"))
        self.assertEqual(legacy["chapter"], 1)
        active_bytes = (self.root / "daily/active.json").read_bytes()
        for chapter, receipt in enumerate(receipts, 1):
            self.assertEqual(ns.read_json(self.root / receipt["receipt_path"])["chapter"], chapter)
            retried = daily.begin(self.project, trigger_id=f"synthetic_trigger_{chapter:03d}")
            self.assertEqual(retried["action"], "already_completed")
            self.assertEqual(retried["chapter"], chapter)
        self.assertEqual((self.root / "daily/active.json").read_bytes(), active_bytes)

    def test_default_manual_begin_can_start_second_chapter_without_extra_author_file(self):
        task = daily.begin(self.project)
        self.release(1)
        daily.finish(self.project, task["run_id"])
        self.assertEqual(daily.begin(self.project)["chapter"], 2)

    def test_recovered_target_deduplicates_both_original_and_recovery_triggers(self):
        first = daily.begin(self.project, trigger_id="synthetic_original")
        resumed = daily.begin(self.project, resume_stopped=True, trigger_id="synthetic_recovery")
        self.release(1)
        daily.finish(self.project, resumed["run_id"])
        daily.begin(self.project, trigger_id="synthetic_later_new")
        for trigger in ("synthetic_original", "synthetic_recovery"):
            result = daily.begin(self.project, trigger_id=trigger)
            self.assertEqual(result["action"], "already_completed")
            self.assertEqual(result["chapter"], 1)
        self.assertNotEqual(first["run_id"], resumed["run_id"])
        self.assertEqual(daily.active_record(self.root)["chapter"], 2)

    def test_legacy_completed_day_does_not_block_a_new_request(self):
        task = daily.begin(self.project)
        self.release(1)
        daily.finish(self.project, task["run_id"])
        legacy = daily.active_record(self.root)
        legacy.pop("trigger_id"); legacy.pop("trigger_ids")
        legacy["receipt_path"] = "daily/" + daily.date_of(legacy["completed_at"]) + ".json"
        ns.atomic_json(self.root / "daily/active.json", legacy)
        self.assertEqual(daily.begin(self.project)["chapter"], 2)

    def test_live_legacy_author_extra_target_keeps_its_lock_and_can_finish(self):
        first = daily.begin(self.project); self.release(1)
        daily.finish(self.project, first["run_id"])
        current = daily.begin(self.project)
        current.pop("trigger_id"); current.pop("trigger_ids")
        request_path = "author_requests/synthetic_next.json"
        state = ns.load_state(self.root)
        request = {"book_id":state["book_id"],"source":"current_user_message","request":"下一章",
                   "chapter":2,"baseline_count":1,"baseline_fingerprint":current["baseline_fingerprint"],
                   "received_at":current["started_at"],"base_revision":state["revision"]}
        ns.atomic_json(self.root / request_path, request)
        current.update(execution_kind="author_requested_extra",author_request_path=request_path,
                       author_request_sha256=ns.digest((self.root / request_path).read_text()))
        ns.atomic_json(self.root / "daily/active.json", current)
        before=(self.root / "daily/active.json").read_bytes()
        self.assertEqual(daily.begin(self.project)["action"],"verify_in_progress")
        self.assertEqual((self.root / "daily/active.json").read_bytes(),before)
        self.release(2)
        receipt=daily.finish(self.project,current["run_id"])
        self.assertTrue(receipt["receipt_path"].startswith("daily/extra/"))
        self.assertEqual(daily.begin(self.project)["chapter"],3)

    def test_invalid_trigger_cannot_change_existing_execution(self):
        daily.begin(self.project)
        before = (self.root / "daily/active.json").read_bytes()
        for trigger in ("../escape", "tiny", "x" * 257, 7):
            with self.assertRaises(daily.ns.WorkspaceError):
                daily.begin(self.project, trigger_id=trigger)
        self.assertEqual((self.root / "daily/active.json").read_bytes(), before)

    def test_completed_active_with_lost_receipt_recovers_instead_of_starting_next(self):
        task = daily.begin(self.project)
        self.release(1)
        receipt = daily.finish(self.project, task["run_id"])
        (self.root / receipt["receipt_path"]).unlink()
        recovered = daily.begin(self.project)
        self.assertEqual(recovered["action"], "recovered_completion")
        self.assertEqual(recovered["chapter"], 1)
        self.assertEqual(recovered["run_id"], task["run_id"])
        self.assertEqual(recovered["completed_at"], receipt["completed_at"])
        self.assertEqual(daily.begin(self.project, trigger_id=task["trigger_id"])["action"], "already_completed")

    def test_receipt_saved_before_active_update_recovers_and_allows_the_next_day(self):
        task = daily.begin(self.project)
        self.release(1)
        receipt = daily.finish(self.project, task["run_id"])
        active = daily.active_record(self.root)
        active["status"] = "running"
        active.pop("completed_at")
        active.pop("receipt_path")
        ns.atomic_json(self.root / "daily/active.json", active)
        recovered = daily.begin(self.project)
        self.assertEqual(recovered["action"], "recovered_completion")
        self.assertEqual(recovered["chapter"], 1)
        self.assertEqual(daily.active_record(self.root)["status"], "completed")
        tomorrow = (datetime.fromisoformat(receipt["completed_at"]) + timedelta(days=1)).isoformat()
        with patch.object(daily, "stamp", return_value=tomorrow):
            self.assertEqual(daily.begin(self.project)["chapter"], 2)

    def test_lost_yesterday_receipt_does_not_open_a_second_target_during_recovery(self):
        task = daily.begin(self.project)
        self.release(1)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        state = ns.load_state(self.root)
        state["chapters"]["1"]["adopted_at"] = past.isoformat(timespec="seconds")
        ns.atomic_json(self.root / "state.json", state)
        active = daily.active_record(self.root)
        active["started_at"] = (past - timedelta(minutes=1)).isoformat(timespec="seconds")
        active["start_date"] = daily.date_of(active["started_at"])
        active["work_id"] = state["book_id"] + ":" + active["start_date"] + ":1"
        ns.atomic_json(self.root / "daily/active.json", active)
        receipt = daily.finish(self.project, task["run_id"])
        (self.root / receipt["receipt_path"]).unlink()
        recovered = daily.begin(self.project)
        self.assertEqual(recovered["action"], "recovered_completion")
        self.assertEqual(recovered["date"], receipt["date"])
        self.assertEqual(daily.active_record(self.root)["chapter"], 1)

    def test_completed_receipt_path_cannot_escape_its_actual_day(self):
        task = daily.begin(self.project)
        self.release(1)
        receipt = daily.finish(self.project, task["run_id"])
        (self.root / receipt["receipt_path"]).unlink()
        active = daily.active_record(self.root)
        active["receipt_path"] = "../state.json"
        ns.atomic_json(self.root / "daily/active.json", active)
        with self.assertRaises(daily.ns.WorkspaceError):
            daily.begin(self.project)

    def test_invalid_active_identity_and_status_cannot_resume_or_block(self):
        task = daily.begin(self.project)
        original = daily.active_record(self.root)
        for patch in ({"status": "made_up"}, {"book_id": "another_book"},
                      {"chapter": 2}, {"work_id": "another_binding"}):
            ns.atomic_json(self.root / "daily/active.json", dict(original, **patch))
            with self.assertRaises(daily.ns.WorkspaceError):
                daily.begin(self.project, resume_stopped=True)
            with self.assertRaises(daily.ns.WorkspaceError):
                daily.block(self.project, task["run_id"], "合成测试")
        self.assertEqual(len(ns.load_state(self.root)["chapters"]), 0)

    def test_yesterday_adoption_cannot_be_reclassified_as_today(self):
        task = daily.begin(self.project)
        self.release(1)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        state = ns.load_state(self.root)
        state["chapters"]["1"]["adopted_at"] = past.isoformat(timespec="seconds")
        ns.atomic_json(self.root / "state.json", state)
        active = daily.active_record(self.root)
        active["started_at"] = (past - timedelta(minutes=1)).isoformat(timespec="seconds")
        active["start_date"] = daily.date_of(active["started_at"])
        active["work_id"] = state["book_id"] + ":" + active["start_date"] + ":1"
        ns.atomic_json(self.root / "daily/active.json", active)
        receipt = daily.finish(self.project, task["run_id"])
        self.assertEqual(receipt["date"], daily.date_of(state["chapters"]["1"]["adopted_at"]))
        self.assertNotEqual(receipt["date"], daily.date_of(daily.stamp()))
        self.assertEqual(daily.begin(self.project)["chapter"], 2)

    def test_legacy_adopted_chapter_without_time_is_not_claimed_today(self):
        task = daily.begin(self.project)
        self.release(1)
        state = ns.load_state(self.root)
        state["chapters"]["1"].pop("adopted_at")
        ns.atomic_json(self.root / "state.json", state)
        with self.assertRaises(daily.ns.WorkspaceError):
            daily.finish(self.project, task["run_id"])

    def test_no_initialization_when_only_empty_master_exists(self):
        empty = self.project / "empty-template"
        empty.mkdir()
        with self.assertRaises(daily.ns.WorkspaceError):
            daily.begin(empty)
        self.assertFalse((empty / "book").exists())

    def test_credentials_in_block_reason_are_redacted(self):
        task = daily.begin(self.project)
        daily.block(self.project, task["run_id"], "测试 ghp_FAKE_TEST_ONLY 凭证")
        self.assertNotIn("ghp_", daily.active_record(self.root)["reason"])

    def test_python_receipt_passes_the_same_javascript_verifier(self):
        if not shutil.which("node"):
            self.skipTest("Node is required for the cross-language contract check")
        for chapter in (1, 2):
            task = daily.begin(self.project)
            self.release(chapter)
            receipt = daily.finish(self.project, task["run_id"])
        state = ns.load_state(self.root)
        state_text = (self.root / "state.json").read_text()
        item = state["chapters"]["2"]
        repo = "https://github.com/example/synthetic-cross-language-test"
        manifest = {"schema_version": 1, "initialized": True, "book": {"id": state["book_id"], "title": "跨语言合成测试"},
                    "source": {"repository_url": repo, "state_sha256": ns.digest(state_text)},
                    "progress": {"adopted_chapters": 2, "actual_han": sum(c["han_count"] for c in state["chapters"].values()), "target_chapters": 100, "target_han": 900000},
                    "task": {}, "chapters": [{"number": n, "title": c["title"], "han_count": c["han_count"], "sha256": c["text_sha256"], "text_path": "book/" + c["text_path"]} for n, c in ((n, state["chapters"][str(n)]) for n in (1, 2))]}
        files = {"online/index.json": {"text": json.dumps(manifest)}, "book/state.json": {"text": state_text}}
        for path in self.root.rglob("*"):
            if path.is_file() and path.suffix in (".json", ".txt"):
                files["book/" + path.relative_to(self.root).as_posix()] = {"text": path.read_text()}
        entry = {"id": "synthetic_cross_language", "book_id": state["book_id"], "title": "合成测试", "repository_url": repo, "branch": "main", "enabled": True,
                 "expected_time": "00:00", "grace_minutes": 0, "effective_from": receipt["date"]}
        payload = {"entry": entry, "source": {"repository_url": repo, "branch": "main", "commit": "a" * 40, "committed_at": daily.stamp(), "files": files}}
        code = """import {SnapshotClient} from './tools/check_updates.mjs';import {inspectBook,inspectExecution} from './web/dist/hub-core.mjs';let text='';for await(const chunk of process.stdin)text+=chunk;const x=JSON.parse(text);console.log(JSON.stringify({day:await inspectBook(x.entry,{client:new SnapshotClient(x.entry,x.source)}),execution:await inspectExecution(x.entry,{client:new SnapshotClient(x.entry,x.source)})}));"""
        result = subprocess.run(["node", "--input-type=module", "-e", code], input=json.dumps(payload), text=True, capture_output=True, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)
        verified = json.loads(result.stdout)
        self.assertEqual(verified["day"]["status"], "updated", result.stdout)
        self.assertEqual(verified["execution"]["status"], "completed", result.stdout)
        self.assertEqual(verified["execution"]["chapter"], 2)
        self.assertEqual(verified["day"]["evidence"]["chapter"], 2)
