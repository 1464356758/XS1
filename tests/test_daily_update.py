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

    def test_completed_day_is_idempotent_and_does_not_start_next_chapter(self):
        task = daily.begin(self.project)
        self.release(1)
        receipt = daily.finish(self.project, task["run_id"])
        again = daily.begin(self.project)
        self.assertEqual(again["action"], "already_completed")
        self.assertEqual(again["chapter"], 1)
        self.assertEqual(receipt["completed_at"], ns.load_state(self.root)["chapters"]["1"]["adopted_at"])
        self.assertEqual(daily.finish(self.project, task["run_id"])["body_sha256"], receipt["body_sha256"])

    def test_missing_receipt_is_recovered_from_adoption_time(self):
        daily.begin(self.project)
        self.release(1)
        recovered = daily.begin(self.project)
        self.assertEqual(recovered["action"], "recovered_completion")
        self.assertEqual(recovered["chapter"], 1)

    def test_completed_active_with_lost_receipt_recovers_instead_of_starting_next(self):
        task = daily.begin(self.project)
        self.release(1)
        receipt = daily.finish(self.project, task["run_id"])
        (self.root / "daily" / (receipt["date"] + ".json")).unlink()
        recovered = daily.begin(self.project)
        self.assertEqual(recovered["action"], "recovered_completion")
        self.assertEqual(recovered["chapter"], 1)
        self.assertEqual(recovered["run_id"], task["run_id"])
        self.assertEqual(recovered["completed_at"], receipt["completed_at"])
        self.assertEqual(daily.begin(self.project)["action"], "already_completed")

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
        (self.root / "daily" / (receipt["date"] + ".json")).unlink()
        recovered = daily.begin(self.project)
        self.assertEqual(recovered["action"], "recovered_completion")
        self.assertEqual(recovered["date"], receipt["date"])
        self.assertEqual(daily.active_record(self.root)["chapter"], 1)

    def test_completed_receipt_path_cannot_escape_its_actual_day(self):
        task = daily.begin(self.project)
        self.release(1)
        receipt = daily.finish(self.project, task["run_id"])
        (self.root / "daily" / (receipt["date"] + ".json")).unlink()
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
        task = daily.begin(self.project)
        self.release(1)
        receipt = daily.finish(self.project, task["run_id"])
        state = ns.load_state(self.root)
        state_text = (self.root / "state.json").read_text()
        item = state["chapters"]["1"]
        repo = "https://github.com/example/synthetic-cross-language-test"
        manifest = {"schema_version": 1, "initialized": True, "book": {"id": state["book_id"], "title": "跨语言合成测试"},
                    "source": {"repository_url": repo, "state_sha256": ns.digest(state_text)},
                    "progress": {"adopted_chapters": 1, "actual_han": item["han_count"], "target_chapters": 100, "target_han": 900000},
                    "task": {}, "chapters": [{"number": 1, "title": item["title"], "han_count": item["han_count"], "sha256": item["text_sha256"], "text_path": "book/" + item["text_path"]}]}
        files = {"online/index.json": {"text": json.dumps(manifest)}, "book/state.json": {"text": state_text},
                 "book/daily/" + receipt["date"] + ".json": {"text": json.dumps(receipt)}}
        for relative in (receipt["body_path"], receipt["record_path"], receipt["release_path"]):
            files["book/" + relative] = {"text": ns.inside(self.root, relative).read_text()}
        entry = {"id": "synthetic_cross_language", "book_id": state["book_id"], "title": "合成测试", "repository_url": repo, "branch": "main", "enabled": True,
                 "expected_time": "00:00", "grace_minutes": 0, "effective_from": receipt["date"]}
        payload = {"entry": entry, "source": {"repository_url": repo, "branch": "main", "commit": "a" * 40, "committed_at": daily.stamp(), "files": files}}
        code = """import {SnapshotClient} from './tools/check_updates.mjs';import {inspectBook} from './web/dist/hub-core.mjs';let text='';for await(const chunk of process.stdin)text+=chunk;const x=JSON.parse(text);console.log(JSON.stringify(await inspectBook(x.entry,{client:new SnapshotClient(x.entry,x.source)})));"""
        result = subprocess.run(["node", "--input-type=module", "-e", code], input=json.dumps(payload), text=True, capture_output=True, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "updated", result.stdout)
