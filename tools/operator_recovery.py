"""作者授权的执行撤销与接续；不推断旧聊天已停止，不创作或采用章节。"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import urllib.request
import uuid

import daily_update as daily
import novel_state as ns


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text_hash(path):
    return ns.digest(Path(path).read_text(encoding="utf-8"))


def read_grant(project, value):
    ns.require(isinstance(value, str) and re.fullmatch(r"\.automation/recoveries/[A-Za-z0-9_-]{8,100}\.json", value),
               "恢复授权必须是单独提交的.automation/recoveries文件，不能来自草稿。")
    grant = ns.read_json(ns.inside(project, value))
    ns.require(grant.get("schema_version") == 1 and grant.get("type") == "novel-operator-recovery-v1" and
               grant.get("operation") == "revoke_and_resume_same_chapter" and
               grant.get("authorization_basis") == "explicit_author_repair_request" and
               isinstance(grant.get("author_instruction"), str) and bool(grant["author_instruction"].strip()),
               "缺少作者明确要求修复的维护授权；定时任务不能自行制作授权。")
    ns.require(grant.get("old_runtime_status") == "unverified" and
               re.fullmatch(r"[0-9a-f]{40}", grant.get("reviewed_head", "")), "必须保留原运行状态未知的真实说明及检查版本。")
    cfg = ns.read_json(Path(project) / ".automation/config.json")
    ns.require(grant.get("book_id") == cfg.get("book_id") and grant.get("automation_id") == cfg.get("automation_id"),
               "维护授权与本书或唯一任务不一致。")
    ns.require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", grant.get("repository", "")), "维护仓库标识无效。")
    proof = grant.get("executor_evidence", {})
    ns.require(proof.get("source") == "github_actions_api" and proof.get("all_jobs_terminal") is True and
               isinstance(proof.get("runs"), list) and bool(proof["runs"]) and
               all(isinstance(r.get("id"), int) and r.get("status") == "completed" for r in proof["runs"]),
               "先实际核对相关执行器作业均已结束。")
    return grant


def verify_jobs_quiescent(grant):
    """CI内独立复查正在运行/等待的作业；本地验证不冒充远端实查。"""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return {"fresh_github_check": False, "mode": "local_validation", "at": stamp()}
    repo, current = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    ns.require(repo == grant["repository"] and current and os.environ.get("GITHUB_TOKEN"), "恢复作业缺少本仓库真实GitHub运行环境。")
    ignored = []
    for status in ("in_progress", "queued", "requested", "waiting", "pending"):
        url = f"https://api.github.com/repos/{repo}/actions/runs?status={status}&per_page=100"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                                                  "Accept": "application/vnd.github+json", "User-Agent": "novel-operator-recovery"})
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                data = json.load(response)
        except Exception as exc:
            raise ns.WorkspaceError("无法独立复查GitHub作业，未撤销旧执行。") from None
        ns.require(data.get("total_count", 0) <= 100, "待核对作业过多，停止维护而非省略检查。")
        for run in data.get("workflow_runs", []):
            if str(run["id"]) == current:
                continue
            # This repository's validation workflow runs tests only; it cannot
            # write production book state. All other pending writers block repair.
            if run.get("path", "").split("@", 1)[0] == ".github/workflows/validate.yml":
                ignored.append(run["id"])
                continue
            raise ns.WorkspaceError("仍有未终结的执行器作业，旧执行未撤销：" + str(run["id"]))
    return {"fresh_github_check": True, "github_run_id": current, "ignored_readonly_validation": ignored, "at": stamp()}


def validate_target(root, state, active, grant):
    daily.validate_active(state, active)
    ns.require(active["run_id"] == grant.get("old_run_id") and active["chapter"] == grant.get("chapter") and
               active["baseline_count"] == grant.get("baseline_count") and
               active["baseline_fingerprint"] == grant.get("baseline_fingerprint"), "旧执行目标与维护授权不一致。")
    ns.require(active["status"] in ("running", "blocked") and str(active["chapter"]) not in state["chapters"] and
               active["chapter"] == len(state["chapters"]) + 1 and
               daily.prefix_fingerprint(state, active["baseline_count"]) == active["baseline_fingerprint"],
               "只能恢复当前未采用目标，不能跳章或改写旧章。")
    ns.require(text_hash(root / "state.json") == grant.get("expected_state_sha256"), "维护检查后写作状态已变化，重新核对而非覆盖。")


def prepare(project, grant_path):
    project = Path(project)
    grant = read_grant(project, grant_path)
    fresh = verify_jobs_quiescent(grant)
    root, _ = daily.load(project)
    with ns.writer_lock(root):
        _, state = daily.load(project)
        active_path = root / "daily/active.json"
        old_text = active_path.read_text(encoding="utf-8")
        ns.require(ns.digest(old_text) == grant.get("expected_active_sha256"), "旧锁已改变或授权已使用，停止重复撤销。")
        old = json.loads(old_text)
        validate_target(root, state, old, grant)
        archive_path = "daily/recoveries/" + Path(grant_path).stem + ".json"
        audit = {"type": "novel-execution-revocation-v1", "grant": grant, "grant_path": grant_path,
                 "grant_sha256": text_hash(project / grant_path), "old_active_text": old_text,
                 "old_runtime_status": "unverified", "revoked_at": stamp(), "executor_check": fresh}
        ns.immutable_text(root / archive_path, json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
        active = copy.deepcopy(old)
        active.update(run_id=uuid.uuid4().hex, status="blocked", reason="作者授权撤销旧执行；已准备接续同一目标，等待既有每日任务。")
        active.pop("controller", None)
        active.pop("executor_checkpoint", None)
        active.setdefault("attempts", []).append({"run_id": old["run_id"], "status": "authorization_revoked",
                                                 "authorization_revoked_at": audit["revoked_at"], "audit_path": archive_path})
        active["operator_recovery"] = {"status": "ready", "grant_path": grant_path, "grant_sha256": audit["grant_sha256"],
                                       "audit_path": archive_path, "audit_sha256": text_hash(root / archive_path),
                                       "old_run_id": old["run_id"], "ready_run_id": active["run_id"],
                                       "expected_state_sha256": grant["expected_state_sha256"]}
        ns.atomic_json(active_path, active)
    return {"business_status": "recovery_ready", "chapter": active["chapter"], "run_id": active["run_id"],
            "revoked_run_id": old["run_id"], "audit_path": "book/" + archive_path, "executor_check": fresh}


def claim_ready(project, controller):
    """接回同一目标；没有运行终止证明时，不生成stopped_confirmed记录。"""
    project = Path(project)
    root, _ = daily.load(project)
    with ns.writer_lock(root):
        _, state = daily.load(project)
        active = daily.active_record(root)
        marker = (active or {}).get("operator_recovery", {})
        if marker.get("status") != "ready":
            return None
        ns.require(active["run_id"] == marker.get("ready_run_id") and active["status"] == "blocked" and not active.get("controller"),
                   "维护检查点已经被使用或改变。")
        grant = read_grant(project, marker["grant_path"])
        ns.require(controller.get("kind") == "automation" and controller.get("automation_id") == grant["automation_id"], "恢复只交给本书既有每日任务。")
        ns.require(text_hash(project / marker["grant_path"]) == marker["grant_sha256"] and
                   text_hash(root / marker["audit_path"]) == marker["audit_sha256"], "维护授权或审计记录发生改变。")
        audit = ns.read_json(root / marker["audit_path"])
        ns.require(ns.digest(audit["old_active_text"]) == grant["expected_active_sha256"] and
                   marker["expected_state_sha256"] == grant["expected_state_sha256"], "旧执行归档不匹配。")
        old = json.loads(audit["old_active_text"])
        validate_target(root, state, old, grant)
        ns.require(all(active[k] == old[k] for k in ("book_id", "work_id", "chapter", "baseline_count", "baseline_fingerprint", "start_date", "started_at")),
                   "恢复检查点的原目标或基线已改变。")
        active.setdefault("attempts", []).append({"run_id": active["run_id"], "status": "recovery_ready", "claimed_at": stamp()})
        active.update(run_id=uuid.uuid4().hex, status="running", controller=copy.deepcopy(controller), reason="", resumed_at=stamp())
        marker.update(status="claimed", claimed_at=stamp(), claimed_by=copy.deepcopy(controller))
        ns.atomic_json(root / "daily/active.json", active)
    return dict(active, action="resumed", recovery_mode="operator_revocation", revoked_run_id=old["run_id"])
