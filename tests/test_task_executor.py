"""临时合成项目验证所有权、故障恢复及Git竞争；不生成或提交真实小说。"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_serial_release as serial_fixtures
from test_novel_state import WorkspaceFixture, ns

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import task_executor as executor
import online_state


class ExecutorTests(WorkspaceFixture):
    prepare = serial_fixtures.SerialTests.prepare
    gate = serial_fixtures.SerialTests.gate
    release = serial_fixtures.SerialTests.release

    def setUp(self):
        super().setUp()
        self.project = self.root.parent
        self.serial = ns.serial_module(); self.a = ns.serial_api()
        self.serial.enable(self.root, "合成执行器测试", ns.load_state(self.root)["revision"], self.a)
        ns.atomic_json(self.project / "project_config.json", {"authority": {"repository_url": "https://github.com/example-user/synthetic-book", "branch": "main"}})
        ns.atomic_json(self.root / "workflow.json", {"schema_version": 1, "revision": 0, "book_id": ns.load_state(self.root)["book_id"],
                       "phase": "WRITING", "platform": "synthetic", "selected_topic": {"id": "SYNTHETIC"}, "research_path": None, "topics_path": None,
                       "chapter": 1, "history": [], "updated_at": "2026-01-01T00:00:00+00:00"})
        for name in ("novel_state.py", "serial_release.py", "narrative_quality.py", "daily_update.py", "online_state.py", "operator_recovery.py"):
            target = self.project / "tools" / name; target.parent.mkdir(exist_ok=True)
            shutil.copyfile(Path(executor.__file__).parent / name, target)
        self.owner = {"kind": "automation", "automation_id": "synthetic_automation_001", "session_id": "synthetic_session_001", "platform_run_id": "synthetic_platform_run_001"}
        ns.atomic_json(self.project / ".automation/config.json", {"schema_version": 1, "book_id": ns.load_state(self.root)["book_id"], "automation_id": self.owner["automation_id"]})
        online_state.build_index(self.project)
        self.counter = 0

    def request(self, phase, **fields):
        self.counter += 1
        return {"schema_version": 1, "request_id": f"synthetic_request_{self.counter:03d}", "base_sha": "a" * 40,
                "book_id": ns.load_state(self.root)["book_id"], "controller": copy.deepcopy(self.owner), "phase": phase, **fields}

    def execute(self, phase, **fields):
        return executor.apply_request(self.project, self.request(phase, **fields), "b" * 40)

    def begin(self):
        return self.execute("begin")

    def test_empty_template_preflight_does_not_initialize_a_book(self):
        empty = self.project / "empty"; empty.mkdir()
        req = self.request("preflight"); req["book_id"] = None
        req["controller"] = {"kind": "maintenance", "session_id": "synthetic_maintenance_001"}
        result = executor.apply_request(empty, req, "b" * 40)
        self.assertEqual(result["business_status"], "not_initialized")
        self.assertFalse((empty / "book/state.json").exists())

    def test_preflight_repairs_derived_index_without_touching_state_or_lock(self):
        self.release(1); self.begin()
        old_state = (self.root / "state.json").read_bytes(); old_lock = (self.root / "daily/active.json").read_bytes()
        index = ns.read_json(self.project / "online/index.json"); index["source"]["state_sha256"] = "0" * 64
        ns.atomic_json(self.project / "online/index.json", index)
        result = self.execute("preflight")
        self.assertEqual(result["business_status"], "preflight_passed")
        self.assertEqual(old_state, (self.root / "state.json").read_bytes())
        self.assertEqual(old_lock, (self.root / "daily/active.json").read_bytes())
        self.assertTrue(online_state.validate_index(self.project)["valid"])

    def test_begin_records_controller_and_repeated_same_owner_keeps_the_target(self):
        self.release(1)
        first = self.begin(); again = self.begin()
        active = executor.read_active(self.project)
        self.assertEqual(first["business_status"], "started")
        self.assertEqual(again["business_status"], "continue_owned")
        self.assertEqual(first["run_id"], again["run_id"])
        self.assertEqual(active["controller"], self.owner)
        self.assertEqual(active["chapter"], 2)
        self.assertEqual(len(ns.load_state(self.root)["chapters"]), 1)

    def test_foreign_session_cannot_run_commands_or_block_the_owner(self):
        started = self.begin(); original = (self.root / "daily/active.json").read_bytes()
        self.owner["session_id"] = "another_synthetic_session"
        result = self.execute("command", run_id=started["run_id"], commands=[{"script": "novel_state.py", "args": ["--root", "book", "history-search", "--query", "测试"]}])
        self.assertEqual(result["executor_status"], "error")
        self.assertEqual(original, (self.root / "daily/active.json").read_bytes())

    def test_legacy_running_record_requires_evidence_even_if_very_old(self):
        import daily_update
        daily_update.begin(self.project)
        original = (self.root / "daily/active.json").read_bytes()
        result = self.execute("begin", stopped_evidence={"source": "timeout", "status": "completed"})
        self.assertEqual(result["business_status"], "recovery_required")
        self.assertEqual(original, (self.root / "daily/active.json").read_bytes())

    def operator_grant(self):
        active = executor.read_active(self.project)
        grant = {"schema_version": 1, "type": "novel-operator-recovery-v1",
                 "operation": "revoke_and_resume_same_chapter", "authorization_basis": "explicit_author_repair_request",
                 "author_instruction": "合成测试：请修复旧任务并沿原章接续。", "old_runtime_status": "unverified",
                 "repository": "example-user/synthetic-book", "reviewed_head": "a" * 40,
                 "book_id": active["book_id"], "automation_id": self.owner["automation_id"],
                 "old_run_id": active["run_id"], "chapter": active["chapter"], "baseline_count": active["baseline_count"],
                 "baseline_fingerprint": active["baseline_fingerprint"],
                 "expected_state_sha256": executor.operator_recovery.text_hash(self.root / "state.json"),
                 "expected_active_sha256": executor.operator_recovery.text_hash(self.root / "daily/active.json"),
                 "executor_evidence": {"source": "github_actions_api", "all_jobs_terminal": True,
                                       "runs": [{"id": 123, "status": "completed"}]}}
        path = ".automation/recoveries/synthetic_author_repair_001.json"
        ns.atomic_json(self.project / path, grant)
        return path, grant

    def recover(self, path):
        req = self.request("recover", recovery_grant=path)
        req["controller"] = {"kind": "maintenance", "session_id": "synthetic_maintenance_001"}
        with patch.object(executor.operator_recovery, "verify_jobs_quiescent", return_value={"fresh_github_check": False, "mode": "synthetic_test"}):
            return executor.apply_request(self.project, req, "b" * 40)

    def test_author_repair_archives_old_run_and_next_task_claims_same_chapter(self):
        import daily_update
        self.release(1); daily_update.begin(self.project)
        path, _, _, _ = self.prepare(2)
        path.write_text("乙取走钥匙，支付铜钱，承担后果。", encoding="utf-8")
        ns.candidate(self.root, 2, path, request="合成返修", repairing=True)
        old_active = (self.root / "daily/active.json").read_text(); old_state = (self.root / "state.json").read_bytes()
        path, grant = self.operator_grant(); result = self.recover(path)
        self.assertEqual(result["business_status"], "recovery_ready")
        ready = executor.read_active(self.project)
        self.assertNotEqual(ready["run_id"], grant["old_run_id"])
        self.assertEqual(ready["status"], "blocked"); self.assertNotIn("controller", ready)
        audit = ns.read_json(self.project / result["audit_path"])
        self.assertEqual(audit["old_active_text"], old_active)
        self.assertEqual(audit["old_runtime_status"], "unverified")
        self.assertEqual((self.root / "state.json").read_bytes(), old_state)
        self.assertNotIn("stopped_confirmed", json.dumps(ready))
        resumed = self.begin(); self.assertEqual(resumed["business_status"], "resumed")
        self.assertEqual(resumed["recovery_mode"], "operator_revocation")
        self.assertNotEqual(resumed["run_id"], ready["run_id"])
        self.assertEqual(resumed["chapter"], 2)
        self.assertEqual(executor.read_active(self.project)["controller"], self.owner)
        self.assertEqual((self.root / "state.json").read_bytes(), old_state)
        self.assertEqual(ns.load_state(self.root)["tasks"]["2"]["repairs"], 1)
        self.assertEqual(self.begin()["business_status"], "continue_owned")
        self.assertEqual(self.recover(path)["executor_status"], "error")

    def test_operator_recovery_needs_author_instruction_and_exact_lock(self):
        import daily_update
        daily_update.begin(self.project); original = (self.root / "daily/active.json").read_bytes()
        path, grant = self.operator_grant(); grant["author_instruction"] = ""
        ns.atomic_json(self.project / path, grant)
        with self.assertRaises(executor.ns.WorkspaceError): self.recover(path)
        self.assertEqual((self.root / "daily/active.json").read_bytes(), original)
        grant["author_instruction"] = "合成作者要求修复"; grant["expected_active_sha256"] = "0" * 64
        ns.atomic_json(self.project / path, grant)
        self.assertEqual(self.recover(path)["executor_status"], "error")
        self.assertEqual((self.root / "daily/active.json").read_bytes(), original)

    def test_operator_recovery_rejects_changed_state_and_wrong_book_binding(self):
        import daily_update
        daily_update.begin(self.project); original = (self.root / "daily/active.json").read_bytes()
        path, grant = self.operator_grant(); grant["book_id"] = "another-book"
        ns.atomic_json(self.project / path, grant)
        with self.assertRaises(executor.ns.WorkspaceError): self.recover(path)
        path, grant = self.operator_grant(); grant["expected_state_sha256"] = "0" * 64
        ns.atomic_json(self.project / path, grant)
        self.assertEqual(self.recover(path)["executor_status"], "error")
        self.assertEqual((self.root / "daily/active.json").read_bytes(), original)

    def test_revoked_owner_cannot_write_and_changed_audit_cannot_be_claimed(self):
        import daily_update
        old = daily_update.begin(self.project); path, _ = self.operator_grant()
        result = self.recover(path); ready = (self.root / "daily/active.json").read_bytes()
        blocked = self.execute("block", run_id=old["run_id"], reason="合成旧控制者")
        self.assertEqual(blocked["executor_status"], "error")
        self.assertEqual((self.root / "daily/active.json").read_bytes(), ready)
        archive = self.project / result["audit_path"]; archive.write_text(archive.read_text()+" ")
        self.assertEqual(self.begin()["executor_status"], "error")
        self.assertEqual((self.root / "daily/active.json").read_bytes(), ready)

    def test_recovery_ready_cannot_be_claimed_with_a_changed_target(self):
        import daily_update
        daily_update.begin(self.project); path, _ = self.operator_grant(); self.recover(path)
        active = executor.read_active(self.project); active["chapter"] += 1
        ns.atomic_json(self.root / "daily/active.json", active)
        self.assertEqual(self.begin()["executor_status"], "error")
        self.assertNotIn("controller", executor.read_active(self.project))

    def test_remote_recovery_refuses_another_live_writer(self):
        import io
        self.begin(); _, grant = self.operator_grant()
        env = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": grant["repository"], "GITHUB_RUN_ID": "100", "GITHUB_TOKEN": "synthetic_token"}
        response = {"total_count": 1, "workflow_runs": [{"id": 101, "path": ".github/workflows/novel-executor.yml", "status": "in_progress"}]}
        with patch.dict(executor.os.environ, env), patch.object(executor.operator_recovery.urllib.request, "urlopen", return_value=io.StringIO(json.dumps(response))):
            with self.assertRaisesRegex(executor.ns.WorkspaceError, "仍有未终结"):
                executor.operator_recovery.verify_jobs_quiescent(grant)

    def test_bound_terminal_owner_can_resume_without_resetting_candidate_repairs(self):
        first = self.begin()
        path, _, _, _ = self.prepare(1)
        path.write_text("乙拿走钥匙后付出代价。", encoding="utf-8")
        ns.candidate(self.root, 1, path, request="合成测试返修", repairing=True)
        task = copy.deepcopy(ns.load_state(self.root)["tasks"]["1"])
        old = copy.deepcopy(self.owner); self.owner["session_id"] = "synthetic_session_002"; self.owner["platform_run_id"] = "synthetic_platform_run_002"
        proof = {"source": "automation_run_lookup", "automation_id": old["automation_id"], "platform_run_id": old["platform_run_id"],
                 "run_id": first["run_id"], "status": "completed", "all_executor_jobs_terminal": True, "observed_at": "2026-01-01T00:00:00+00:00"}
        result = self.execute("begin", stopped_evidence=proof)
        active = executor.read_active(self.project)
        self.assertEqual(result["business_status"], "resumed")
        self.assertNotEqual(active["run_id"], first["run_id"])
        self.assertEqual(active["chapter"], 1)
        self.assertEqual(ns.load_state(self.root)["tasks"]["1"], task)
        self.assertEqual(active["controller_history"][0]["controller"], old)

    def test_terminal_proof_for_a_different_platform_run_cannot_resume(self):
        first = self.begin(); self.owner["session_id"] = "synthetic_session_002"
        result = self.execute("begin", stopped_evidence={"source": "automation_run_lookup", "automation_id": self.owner["automation_id"],
                              "platform_run_id": "wrong_synthetic_platform_run", "run_id": first["run_id"], "status": "completed",
                              "all_executor_jobs_terminal": True, "observed_at": "2026-01-01T00:00:00+00:00"})
        self.assertEqual(result["business_status"], "recovery_required")
        self.assertEqual(executor.read_active(self.project)["run_id"], first["run_id"])

    def test_tool_failure_preserves_repair_budget_and_records_block_with_valid_index(self):
        first = self.begin(); self.prepare(1)
        draft = self.project / "drafts/repair.txt"; draft.parent.mkdir(); draft.write_text("乙拿走钥匙并承担后果。", encoding="utf-8")
        result = self.execute("command", run_id=first["run_id"], commands=[
            {"script": "novel_state.py", "args": ["--root", "book", "repair", "--chapter", "1", "--text", "drafts/repair.txt", "--reason", "合成测试"]},
            {"script": "novel_state.py", "args": ["--root", "book", "brief-check", "--file", "drafts/does-not-exist.json"]}])
        self.assertEqual(result["executor_status"], "error")
        self.assertEqual(ns.load_state(self.root)["tasks"]["1"]["repairs"], 1)
        self.assertEqual(executor.read_active(self.project)["status"], "blocked")
        self.assertTrue(online_state.validate_index(self.project)["valid"])

    def finalize_inputs(self, chapter):
        path, record, _, report = self.prepare(chapter)
        directory = self.project / "drafts"; directory.mkdir(exist_ok=True)
        shutil.copyfile(path, directory / "draft.txt"); shutil.copyfile(record, directory / "record.json")
        ns.atomic_json(directory / "release.json", report)
        return {"text": "drafts/draft.txt", "record": "drafts/record.json", "report": "drafts/release.json"}

    def test_finalize_adopts_exactly_one_chapter_with_receipt_and_keeps_old_prose(self):
        self.release(1); first = self.begin(); inputs = self.finalize_inputs(2)
        old = copy.deepcopy(ns.load_state(self.root)["chapters"]["1"])
        result = self.execute("finalize", run_id=first["run_id"], **inputs)
        state = ns.load_state(self.root)
        self.assertEqual(result["business_status"], "chapter_completed")
        self.assertEqual(state["chapters"]["1"], old)
        self.assertEqual(len(state["chapters"]), 2)
        self.assertEqual(executor.read_active(self.project)["status"], "completed")
        self.assertTrue((self.project / result["receipt_path"]).is_file())
        self.assertTrue(online_state.validate_index(self.project)["valid"])

    def test_failed_finish_rolls_back_new_adoption_and_keeps_owned_run_blocked(self):
        self.release(1); first = self.begin(); inputs = self.finalize_inputs(2)
        old = copy.deepcopy(ns.load_state(self.root))
        with patch.object(executor.daily, "finish", side_effect=executor.ns.WorkspaceError("合成回执失败")):
            result = self.execute("finalize", run_id=first["run_id"], **inputs)
        self.assertEqual(result["executor_status"], "error")
        self.assertEqual(ns.load_state(self.root), old)
        self.assertEqual(executor.read_active(self.project)["status"], "blocked")
        self.assertFalse(any(p.name.startswith("CH002_") for p in (self.root / "chapters").glob("*")))
        self.assertTrue(online_state.validate_index(self.project)["valid"])

    def test_duplicate_request_id_is_not_replayed(self):
        req = self.request("preflight")
        executor.apply_request(self.project, req, "b" * 40)
        with self.assertRaisesRegex(executor.ns.WorkspaceError, "请求编号已使用"):
            executor.apply_request(self.project, req, "b" * 40)

    def test_arbitrary_scripts_path_escape_and_publication_are_rejected(self):
        for command in ({"script": "other.py", "args": ["--root", "book", "status"]},
                        {"script": "novel_state.py", "args": ["--root", "book", "publish"]},
                        {"script": "novel_state.py", "args": ["--root", "book", "context", "--out", "../outside.txt"]}):
            with self.subTest(command=command), self.assertRaises(executor.ns.WorkspaceError):
                executor.command_spec(self.project, command)


class GitLeaseTests(unittest.TestCase):
    def test_remote_advance_blocks_old_request_and_exact_recorded_result_can_be_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); project = root / "work"; project.mkdir()
            def run(*args):
                return subprocess.check_output(["git", *args], cwd=project, text=True, stderr=subprocess.DEVNULL).strip()
            run("init", "-b", "main"); run("config", "user.name", "Synthetic"); run("config", "user.email", "synthetic@local.invalid")
            (project / "README.md").write_text("synthetic git race test")
            run("add", "."); run("commit", "-m", "base"); base = run("rev-parse", "HEAD")
            remote = root / "remote.git"; run("clone", "--bare", str(project), str(remote)); run("remote", "add", "origin", str(remote))
            req = {"base_sha": base, "request_id": "synthetic_request_git_001"}
            ns.atomic_json(project / ".automation/request.json", req)
            run("add", "."); run("commit", "-m", "request"); event = run("rev-parse", "HEAD"); run("push", "origin", "main")
            self.assertIsNone(executor.check_source(project, req, event, "main"))
            (project / "README.md").write_text("new competing change")
            run("add", "."); run("commit", "-m", "competing update"); advance = run("rev-parse", "HEAD"); run("push", "origin", "main")
            run("checkout", "--detach", event)
            with self.assertRaisesRegex(executor.ns.WorkspaceError, "远端已有更新"):
                executor.check_source(project, req, event, "main")
            run("checkout", "--detach", advance)
            recorded = {"source_sha": event, "request_sha256": executor.ns.digest(json.dumps(req, ensure_ascii=False, sort_keys=True))}
            ns.atomic_json(project / ".automation/results/synthetic_request_git_001.json", recorded)
            run("add", "."); run("commit", "-m", "record result"); run("push", "origin", "HEAD:main"); run("checkout", "--detach", event)
            self.assertEqual(executor.check_source(project, req, event, "main"), recorded)
