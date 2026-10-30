#!/usr/bin/env python3
"""固定的日更工具执行器；不调用模型、不生成审稿结论、不自动投稿。"""
from __future__ import annotations

import argparse
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import daily_update as daily
import novel_state as ns
import online_state as online
import operator_recovery

PROTOCOL = "novel-task-executor-v1"
ID = re.compile(r"[A-Za-z0-9_-]{8,100}")
TOOLS = {"brief-request", "brief-check", "history-search", "context", "candidate",
         "repair", "check-record", "release-request", "release-check", "set-input", "incident"}
PATH_FLAGS = {"--text", "--record", "--report", "--file", "--out"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require(ok, message):
    ns.require(ok, message)


def safe_path(project, value):
    require(isinstance(value, str) and value and not Path(value).is_absolute() and
            ".." not in Path(value).parts and "\\" not in value, "请求文件路径必须留在本仓库。")
    return ns.inside(project, value)


def read_active(project):
    p = Path(project) / "book/daily/active.json"
    return ns.read_json(p) if p.exists() else None


def owner_equal(a, b):
    return (isinstance(a, dict) and isinstance(b, dict) and a.get("kind") == b.get("kind") == "automation"
            and all(a.get(k) == b.get(k) and a.get(k) for k in ("automation_id", "session_id"))
            and a.get("platform_run_id") == b.get("platform_run_id"))


def validate_request(project, request):
    require(isinstance(request, dict) and request.get("schema_version") == 1, "执行请求格式无效。")
    require(isinstance(request.get("request_id"), str) and bool(ID.fullmatch(request["request_id"])), "request_id须为8—100位独立请求编号。")
    require(isinstance(request.get("base_sha"), str) and bool(re.fullmatch(r"[0-9a-f]{40}", request["base_sha"])), "请求必须绑定实际基础提交。")
    require(request.get("phase") in ("preflight", "recover", "begin", "command", "finalize", "block"), "执行阶段无效。")
    owner = request.get("controller", {})
    require(isinstance(owner, dict), "缺少执行控制者。")
    if request["phase"] in ("preflight", "recover") and owner.get("kind") == "maintenance":
        require(bool(ID.fullmatch(owner.get("session_id", ""))), "维护预检须有独立会话编号。")
    else:
        require(owner.get("kind") == "automation" and
                all(isinstance(owner.get(k), str) and ID.fullmatch(owner[k]) for k in ("automation_id", "session_id")),
                "写作请求必须记录实际自动化及本轮独立会话。")
        platform = owner.get("platform_run_id")
        require(platform is None or isinstance(platform, str) and ID.fullmatch(platform), "平台运行编号无效；不可伪造。")
    state_path = Path(project) / "book/state.json"
    if not state_path.exists():
        require(request["phase"] == "preflight" and request.get("book_id") is None, "空母版只能预检，不能自动开书。")
        return None
    state = ns.load_state(Path(project) / "book")
    require(request.get("book_id") == state["book_id"], "请求与本书身份不一致。")
    config_path = Path(project) / ".automation/config.json"
    if request["phase"] == "recover":
        require(owner.get("kind") == "maintenance", "撤销旧执行只接受作者授权的维护请求。")
        operator_recovery.read_grant(project, request.get("recovery_grant"))
    elif request["phase"] != "preflight":
        require(config_path.is_file(), "先登记本书实际唯一任务绑定，不在运行时猜测。")
        cfg = ns.read_json(config_path)
        require(cfg.get("book_id") == state["book_id"] and
                cfg.get("automation_id") == owner.get("automation_id"), "请求控制者与已登记的唯一任务不符。")
    return state


def assert_owner(project, request):
    active = read_active(project)
    require(active and active.get("run_id") == request.get("run_id") and
            active.get("status") in ("running", "blocked") and
            owner_equal(active.get("controller"), request["controller"]),
            "旧执行或控制者不匹配；停止写入，不能抢占。")
    return active


def stopped_proof(active, proof):
    old = active.get("controller", {})
    # This is an attestation from a real connector lookup, not an independent
    # GitHub-to-ChatGPT status API. No timeout is accepted as a stopped proof.
    return (isinstance(proof, dict) and bool(old.get("platform_run_id")) and
            proof.get("source") == "automation_run_lookup" and
            proof.get("automation_id") == old.get("automation_id") and
            proof.get("platform_run_id") == old.get("platform_run_id") and
            proof.get("run_id") == active["run_id"] and
            proof.get("status") in ("completed", "failed", "no_update") and
            proof.get("all_executor_jobs_terminal") is True and
            isinstance(proof.get("observed_at"), str) and bool(proof["observed_at"]))


def begin_owned(project, request):
    claimed = operator_recovery.claim_ready(project, request["controller"])
    if claimed is not None:
        return claimed
    result = daily.begin(project)
    if result["action"] == "verify_in_progress":
        if owner_equal(result.get("controller"), request["controller"]):
            if result["status"] == "blocked":
                active = read_active(project)
                active.update(status="running", reason="", continued_at=now())
                ns.atomic_json(Path(project) / "book/daily/active.json", active)
            return dict(result, action="continue_owned")
        if not stopped_proof(result, request.get("stopped_evidence")):
            return dict(result, action="recovery_required", note="核实原控制者终态；无归属的旧记录不得自动接管。")
        old_controller = result.get("controller")
        result = daily.begin(project, resume_stopped=True)
        active = read_active(project)
        active.setdefault("controller_history", []).append({"controller": old_controller, "stopped_evidence": request["stopped_evidence"]})
        ns.atomic_json(Path(project) / "book/daily/active.json", active)
    if result["action"] in ("started", "resumed"):
        active = read_active(project)
        active["controller"] = copy.deepcopy(request["controller"])
        active["executor_checkpoint"] = {"request_id": request["request_id"], "at": now(), "github_run_id": os.environ.get("GITHUB_RUN_ID")}
        ns.atomic_json(Path(project) / "book/daily/active.json", active)
        result.update(controller=active["controller"])
    return result


def command_spec(project, command):
    require(isinstance(command, dict), "工具命令必须为结构化对象。")
    script, args = command.get("script"), command.get("args")
    require(isinstance(args, list) and 3 <= len(args) <= 50 and
            all(isinstance(x, str) and len(x) <= 4000 for x in args), "工具参数无效。")
    if script == "novel_state.py":
        require(args[:2] == ["--root", "book"] and args[2] in TOOLS, "本阶段不允许该小说工具命令。")
        if args[2] == "set-input":
            i = args.index("--kind") if "--kind" in args else len(args)
            require(i + 1 < len(args) and args[i + 1] == "roadmap", "日更只调整未来路线，不改canon。")
    elif script == "online_state.py":
        require(args[:2] == ["--project", "."] and args[2] in ("task", "build-index", "validate-index"), "工作流工具命令无效。")
    else:
        raise ns.WorkspaceError("仅执行仓库既有小说/索引工具，不接受任意脚本或shell。")
    for i, value in enumerate(args):
        if value in PATH_FLAGS:
            require(i + 1 < len(args), "路径参数缺少值。")
            safe_path(project, args[i + 1])
            if value == "--out":
                require(args[i + 1].startswith(("drafts/", ".automation/work/")), "输出只放drafts或本轮工作资料目录。")
    return [sys.executable, "tools/" + script, *args]


def protected_state(project):
    p = Path(project) / "book/state.json"
    if not p.exists():
        return None
    state = ns.load_state(Path(project) / "book")
    ns.verify_files(Path(project) / "book", state)
    return {"state": state, "files": {item[key]: (Path(project) / "book" / item[key]).read_bytes()
                                     for item in state["chapters"].values() for key in ("text_path", "record_path")}}


def guard_after(project, before, phase):
    if before is None:
        require(not (Path(project) / "book/state.json").exists(), "预检不能生成小说身份。")
        return
    old = before["state"]; state = ns.load_state(Path(project) / "book")
    ns.verify_files(Path(project) / "book", state)
    require(state["book_id"] == old["book_id"] and state["config"] == old["config"], "执行器不能改身份、关闭冻结或降低门槛。")
    for n, item in old["chapters"].items():
        require(state["chapters"].get(n) == item and state.get("serialization", {}).get("frozen", {}).get(n) == old.get("serialization", {}).get("frozen", {}).get(n), "旧采用章及冻结记录必须完全不变。")
    for path, data in before["files"].items():
        require((Path(project) / "book" / path).read_bytes() == data, "不能改写既有正文或事实文件。")
    delta = len(state["chapters"]) - len(old["chapters"])
    require(delta == (1 if phase == "finalize" else 0), "每轮只允许finalize采用原目标的一章。")
    for n, task in old["tasks"].items():
        if task["phase"] == "candidate":
            current = state["tasks"].get(n, {})
            require(current.get("task_id") == task["task_id"] and current.get("repairs", -1) >= task["repairs"], "不能清零候选或修订历史。")


def sync_index(project):
    if (Path(project) / "book/state.json").exists():
        online.build_index(project)
        online.validate_index(project)


def _run(project, request, result):
    phase = request["phase"]
    if not (Path(project) / "book/state.json").exists():
        result["business_status"] = "not_initialized"
        return
    root = Path(project) / "book"
    ns.verify_files(root, ns.load_state(root))
    if phase == "preflight":
        result["business_status"] = "preflight_passed"
        result["active_status"] = (read_active(project) or {}).get("status")
    elif phase == "recover":
        result.update(operator_recovery.prepare(project, request.get("recovery_grant")))
    elif phase == "begin":
        action = begin_owned(project, request)
        result.update(business_status=action["action"], daily_action=action["action"],
                      run_id=action.get("run_id"), chapter=action.get("chapter"))
        if action.get("recovery_mode"):
            result.update(recovery_mode=action["recovery_mode"], revoked_run_id=action["revoked_run_id"])
    elif phase == "command":
        assert_owner(project, request)
        commands = request.get("commands")
        require(isinstance(commands, list) and 1 <= len(commands) <= 6, "每批工具命令须为1—6条。")
        for i, command in enumerate(commands):
            cmd = command_spec(project, command)
            done = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=120)
            directory = Path(project) / ".automation/work" / request["request_id"]
            directory.mkdir(parents=True, exist_ok=True)
            outputs = {}
            for channel, body in (("stdout", done.stdout), ("stderr", done.stderr)):
                p = directory / f"tool-{i + 1:02d}.{channel}.txt"
                p.write_text(body, encoding="utf-8")
                outputs[channel] = {"path": p.relative_to(project).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
            result.setdefault("tools", []).append({"script": command["script"], "args": command["args"], "exit_code": done.returncode, "outputs": outputs})
            require(done.returncode == 0, f"工具第{i + 1}步失败；完整输出保存在本轮work目录。")
        result.update(business_status="tools_completed", run_id=request["run_id"])
    elif phase == "finalize":
        active = assert_owner(project, request)
        paths = [safe_path(project, request.get(key)) for key in ("text", "record", "report")]
        ns.serial_module().check(root, *paths, ns.serial_api())
        ns.adopt(root, paths[0], paths[1])
        receipt = daily.finish(project, request["run_id"])
        workflow = online.load_workflow(project)
        online.write_workflow(project, workflow, phase="WAITING_NEXT",
                              detail=f"第{active['chapter']}章已采用并冻结；平台发布另凭真实回执登记。",
                              next_action="读取正式状态后，由下一次日更处理下一章。")
        workflow = online.load_workflow(project); workflow["chapter"] = active["chapter"] + 1
        ns.atomic_json(Path(project) / "book/workflow.json", workflow)
        result.update(business_status="chapter_completed", run_id=receipt["run_id"], chapter=receipt["chapter"],
                      body_sha256=receipt["body_sha256"], receipt_path="book/daily/" + receipt["date"] + ".json")
    else:
        assert_owner(project, request)
        daily.block(project, request["run_id"], request.get("reason", ""))
        result.update(business_status="blocked", run_id=request["run_id"])
    sync_index(project)
    active = read_active(project)
    if phase != "preflight" and active and owner_equal(active.get("controller"), request["controller"]):
        active["executor_checkpoint"] = {"request_id": request["request_id"], "phase": phase,
                                         "at": now(), "github_run_id": os.environ.get("GITHUB_RUN_ID")}
        ns.atomic_json(root / "daily/active.json", active)


def tracked_outputs(project):
    project = Path(project)
    paths = set()
    for directory in ("book", "drafts", ".automation/work"):
        base = project / directory
        if base.exists():
            for path in base.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    require(not path.is_symlink() and path.resolve().is_relative_to(project.resolve()), "产物不能是外部符号链接。")
                    if path.name != ".writer-lock" and not path.name.startswith(".pending-"):
                        paths.add(path.relative_to(project).as_posix())
    if (project / "online/index.json").is_file():
        paths.add("online/index.json")
    return {p: (project / p).read_bytes() for p in paths}


def apply_request(project, request, source_sha):
    """Execute in an isolated copy; publish only a valid complete state transition."""
    project = Path(project).resolve()
    validate_request(project, request)
    output = project / ".automation/results" / (request["request_id"] + ".json")
    require(not output.exists(), "请求编号已使用；不能重放或覆盖已有结果。")
    before = protected_state(project); original = tracked_outputs(project)
    result = {"protocol": PROTOCOL, "request_id": request["request_id"], "request_sha256": ns.digest(json.dumps(request, ensure_ascii=False, sort_keys=True)),
              "source_sha": source_sha, "base_sha": request["base_sha"], "book_id": request.get("book_id"), "controller": request["controller"],
              "phase": request["phase"], "executed_at": now(), "executor_status": "ok"}
    result["github_run_id"] = os.environ.get("GITHUB_RUN_ID")
    with tempfile.TemporaryDirectory(prefix="novel-tool-batch-") as tmp:
        work = Path(tmp) / "project"
        shutil.copytree(project, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                _run(work, request, result)
            guard_after(work, before, request["phase"])
        except (ns.WorkspaceError, ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
            error = re.sub(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+", "[凭证已隐去]", str(exc))[:2000]
            # A failed finalize must never save an adopted chapter without its receipt.
            preserve = request["phase"] == "command"
            if preserve:
                try: guard_after(work, before, "command")
                except (ns.WorkspaceError, OSError, KeyError): preserve = False
            if not preserve:
                shutil.rmtree(work)
                shutil.copytree(project, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            result.update(executor_status="error", business_status="blocked", error=error)
            active = read_active(work)
            if active and active.get("run_id") == request.get("run_id") and owner_equal(active.get("controller"), request["controller"]) and active.get("status") != "completed":
                daily.block(work, active["run_id"], error)
                result["run_id"] = active["run_id"]
            sync_index(work)
            guard_after(work, before, "command")
        changed = tracked_outputs(work)
        require(set(original).issubset(changed), "执行器不能删除已有正文、草稿或工作记录。")
        for path, body in changed.items():
            if original.get(path) != body:
                target = project / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(body)
        result["changed_paths"] = sorted(p for p, body in changed.items() if original.get(p) != body)
    ns.atomic_json(output, result)
    return result


def git(project, *args):
    return subprocess.check_output(["git", *args], cwd=project, text=True, stderr=subprocess.PIPE).strip()


def check_source(project, request, event_sha, branch):
    require(git(project, "rev-parse", "HEAD") == event_sha, "工作目录与触发提交不符。")
    require(len(git(project, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 2, "请求提交必须只有一个父提交。")
    require(git(project, "rev-parse", "HEAD^") == request["base_sha"], "请求基础提交不是触发提交的单一父版本。")
    changes = git(project, "diff", "--name-only", request["base_sha"], event_sha).splitlines()
    require(all(p == ".automation/request.json" or p.startswith(("drafts/", "editorial/")) for p in changes),
            "请求提交只能包含请求和待审资料，不能直接改正式状态、正文或系统代码。")
    subprocess.run(["git", "fetch", "--quiet", "origin", branch], cwd=project, check=True, timeout=60)
    remote = git(project, "rev-parse", "FETCH_HEAD")
    if remote != event_sha:
        path = ".automation/results/" + request["request_id"] + ".json"
        try:
            recorded = json.loads(git(project, "show", remote + ":" + path))
            if recorded.get("source_sha") == event_sha and recorded.get("request_sha256") == ns.digest(json.dumps(request, ensure_ascii=False, sort_keys=True)):
                return recorded
        except (subprocess.CalledProcessError, ValueError):
            pass
        raise ns.WorkspaceError("远端已有更新；本请求停止，不重放、不覆盖。")
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--request", default=".automation/request.json")
    parser.add_argument("--event-sha", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args(); project = Path(args.project).resolve()
    try:
        request = ns.read_json(safe_path(project, args.request))
        validate_request(project, request)
        recorded = check_source(project, request, args.event_sha, args.branch)
        if recorded:
            print(json.dumps({"already_recorded": True, "request_id": request["request_id"]})); return
        result = apply_request(project, request, args.event_sha)
        print(json.dumps({k: result[k] for k in ("request_id", "executor_status", "business_status")}, ensure_ascii=False))
    except (ns.WorkspaceError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(2, "执行器未发布：" + str(exc) + "\n")


if __name__ == "__main__":
    main()
