#!/usr/bin/env python3
"""逐次写作的目标、恢复与完成证据；不调用模型、不提交远端、不判定文学质量。"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import uuid

import novel_state as ns

SH = timezone(timedelta(hours=8))


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def date_of(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    ns.require(d.tzinfo is not None, "时间必须带时区。")
    return d.astimezone(SH).date().isoformat()


def prefix_fingerprint(state, count):
    values = [{"chapter": n, "text_sha256": state["chapters"][str(n)]["text_sha256"],
               "record_sha256": state["chapters"][str(n)]["record_sha256"]} for n in range(1, count + 1)]
    return ns.digest(json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def author_binding(root, state, value):
    """核对显式手动加更的原始作者指令；默认日更不使用这个入口。"""
    path = value.get("author_request_path")
    ns.require(isinstance(path, str) and path.startswith("author_requests/") and
               len(Path(path).parts) == 2, "手动加更须绑定本书author_requests中的作者指令。")
    text = ns.inside(root, path).read_text(encoding="utf-8")
    request = json.loads(text)
    ns.require(ns.digest(text) == value.get("author_request_sha256") and
               request.get("book_id") == state["book_id"] and
               request.get("source") == "current_user_message" and
               request.get("request", "").strip() in ("下一章", "继续下一章", "开始下一章") and
               request.get("chapter") == value["chapter"] and
               request.get("baseline_count") == value["baseline_count"] and
               request.get("baseline_fingerprint") == value["baseline_fingerprint"],
               "手动加更的作者指令、目标章或前文基线不匹配。")
    received = datetime.fromisoformat(request["received_at"])
    ns.require(received.tzinfo is not None and received <= datetime.fromisoformat(value["started_at"]),
               "作者指令时间晚于执行开始。")
    return request


def extra_receipt_path(value, day):
    return f"daily/extra/{day}_CH{value['chapter']:03d}_{value['run_id']}.json"


def validate_trigger(value):
    ns.require(isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{8,256}", value)),
               "写作请求编号须为8—256位稳定标识；同次重试复用，新指令使用新编号。")
    return value


def trigger_path(value):
    return "daily/requests/" + ns.digest(validate_trigger(value)) + ".json"


def triggers(value):
    primary = value.get("trigger_id")
    if primary is None:
        ns.require(not value.get("trigger_ids"), "写作请求绑定缺少主编号。")
        return []
    validate_trigger(primary)
    values = value.get("trigger_ids", [primary])
    ns.require(isinstance(values, list) and 1 <= len(values) <= 32 and
               all(isinstance(x, str) for x in values) and len(set(values)) == len(values) and values[0] == primary,
               "写作请求绑定无效或重复。")
    for item in values:
        validate_trigger(item)
    return values


def bind_trigger(value, trigger_id):
    values = list(triggers(value))
    if trigger_id not in values:
        values.append(validate_trigger(trigger_id))
    ns.require(len(values) <= 32, "同一目标恢复过多，请核实历史请求，不清空绑定。")
    value.update(trigger_id=values[0], trigger_ids=values)
    return value


def allowed_receipt_paths(value, day):
    paths = ["daily/" + day + ".json", extra_receipt_path(value, day)]
    paths.extend(trigger_path(x) for x in triggers(value))
    return paths


def load(project):
    root = Path(project).resolve() / "book"
    ns.require((root / "state.json").is_file(), "尚未初始化小说；先完成平台、选题和规划，不创建空的每日任务。")
    ns.require(not (root / "private_storage.json").exists(), "旧加密作品请先按正文直接读取说明处理，不能伪造完成证据。")
    state = ns.load_state(root)
    ns.verify_files(root, state)
    return root, state


def formal_evidence(root, state, n):
    ns.require(state.get("serialization", {}).get("enabled"), "完成证据要求本书已启用连载冻结；不要自动追认旧章。")
    item = state["chapters"].get(str(n))
    serial = state["serialization"]
    pin, gate = serial["frozen"].get(str(n)), serial["gates"].get(str(n))
    ns.require(item and pin and gate and gate["used"] and n not in state["needs_revalidation"], "目标章尚未通过检查并冻结采用。")
    ns.require(pin["text_sha256"] == item["text_sha256"] and pin["record_sha256"] == item["record_sha256"], "冻结版本不一致。")
    report_text = ns.inside(root, gate["path"]).read_text(encoding="utf-8")
    ns.require(ns.digest(report_text) == gate["sha256"], "检查报告被改变。")
    report = json.loads(report_text)
    ns.require(report.get("book_id") == state["book_id"] and report.get("chapter") == n and
               report.get("text_sha256") == item["text_sha256"] and report.get("record_sha256") == item["record_sha256"] and
               report.get("decision") == "release" and report.get("read_full_text") is True and report.get("blocking_issues") == [],
               "检查报告未通过或没有绑定当前正文。")
    return item, gate


def verify_receipt(root, state, receipt):
    ns.require(receipt.get("type") == "novel-daily-completion-v1" and receipt.get("status") == "completed" and
               receipt.get("book_id") == state["book_id"], "每日完成记录身份无效。")
    n = receipt["chapter"]
    item, gate = formal_evidence(root, state, n)
    ns.require(receipt["baseline_count"] + 1 == n and prefix_fingerprint(state, receipt["baseline_count"]) == receipt["baseline_fingerprint"], "目标章或前文基线改变。")
    ns.require(receipt.get("body_sha256") == item["text_sha256"] and receipt.get("record_sha256") == item["record_sha256"] and
               receipt.get("release_sha256") == gate["sha256"] and receipt.get("completed_at") == item.get("adopted_at") and
               receipt.get("date") == date_of(receipt["completed_at"]), "完成证据与实际采用版本、日期不匹配。")
    ns.require(receipt.get("body_path") == item["text_path"] and receipt.get("record_path") == item["record_path"] and
               receipt.get("release_path") == gate["path"] and receipt.get("work_id") == state["book_id"] + ":" + receipt["start_date"] + ":" + str(n) and
               receipt["start_date"] == date_of(receipt["started_at"]) and datetime.fromisoformat(receipt["started_at"]) <= datetime.fromisoformat(receipt["completed_at"]),
               "每日完成记录的目标、来源或开始时间无效。")
    if receipt.get("execution_kind") == "author_requested_extra":
        author_binding(root, state, receipt)
    triggers(receipt)
    return receipt


def active_record(root):
    path = root / "daily/active.json"
    return ns.read_json(path) if path.exists() else None


def validate_active(state, active):
    ns.require(isinstance(active, dict) and active.get("book_id") == state["book_id"] and
               active.get("type") == "novel-daily-task-v1" and
               active.get("status") in ("running", "blocked", "completed"), "执行记录与小说身份不符或状态无效。")
    n, baseline = active.get("chapter"), active.get("baseline_count")
    ns.require(type(n) is int and type(baseline) is int and baseline >= 0 and n == baseline + 1 and
               isinstance(active.get("run_id"), str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{8,100}", active["run_id"])),
               "执行编号或目标章无效。")
    ns.require(active.get("start_date") == date_of(active["started_at"]) and
               active.get("work_id") == state["book_id"] + ":" + active["start_date"] + ":" + str(n),
               "执行记录的开始日期或任务绑定无效。")
    triggers(active)
    return active


def finish_locked(root, state, active):
    validate_active(state, active)
    if active.get("execution_kind") == "author_requested_extra":
        author_binding(root, state, active)
    n = active["chapter"]
    ns.require(len(state["chapters"]) == n, "只能为刚完成的目标章出具回执；存在额外章节需人工核实。")
    item, gate = formal_evidence(root, state, n)
    adopted = item.get("adopted_at")
    ns.require(adopted, "本章没有工具记录的实际采用时间，不能把旧章补记为今天完成。")
    ns.require(datetime.fromisoformat(adopted) >= datetime.fromisoformat(active["started_at"]), "目标章在本次任务开始前已采用，不能重复计为新更新。")
    ns.require(prefix_fingerprint(state, active["baseline_count"]) == active["baseline_fingerprint"], "任务开始后前文发生变化，停止生成完成回执。")
    receipt = {"schema_version": 1, "type": "novel-daily-completion-v1", "status": "completed",
               "book_id": state["book_id"], "run_id": active["run_id"], "work_id": active["work_id"],
               "start_date": active["start_date"], "date": date_of(adopted), "started_at": active["started_at"],
               "completed_at": adopted, "verified_at": stamp(), "chapter": n,
               "baseline_count": active["baseline_count"], "baseline_fingerprint": active["baseline_fingerprint"],
               "body_path": item["text_path"], "body_sha256": item["text_sha256"],
               "record_path": item["record_path"], "record_sha256": item["record_sha256"],
               "release_path": gate["path"], "release_sha256": gate["sha256"], "state_revision": state["revision"]}
    if active.get("execution_kind") == "author_requested_extra":
        receipt.update({key: active[key] for key in ("execution_kind", "author_request_path", "author_request_sha256")})
    if triggers(active):
        receipt.update(trigger_id=active["trigger_id"], trigger_ids=triggers(active))
    verify_receipt(root, state, receipt)
    day_path = root / "daily" / (receipt["date"] + ".json")
    path = ns.inside(root, trigger_path(active["trigger_id"])) if triggers(active) else day_path
    if not triggers(active) and day_path.exists():
        old = verify_receipt(root, state, ns.read_json(day_path))
        if old["run_id"] != receipt["run_id"]:
            path = ns.inside(root, extra_receipt_path(active, receipt["date"]))
    candidates = [path] + [ns.inside(root, trigger_path(x)) for x in triggers(receipt)] + [day_path]
    for target in candidates:
        if target.exists():
            old = verify_receipt(root, state, ns.read_json(target))
            if target == day_path and old["run_id"] != receipt["run_id"]:
                continue
            ns.require(old["run_id"] == receipt["run_id"] and old["body_sha256"] == receipt["body_sha256"] and
                       triggers(old) == triggers(receipt), "本次请求已有不同完成记录，停止覆盖。")
            receipt = old
            break
    body = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    # The immutable first completion of a date remains for legacy readers.
    # It is no longer a limit: each writing request has its own receipt.
    paths = {path, *(ns.inside(root, trigger_path(x)) for x in triggers(receipt))}
    if not day_path.exists():
        paths.add(day_path)
    else:
        verify_receipt(root, state, ns.read_json(day_path))
    for target in sorted(paths):
        if target.exists():
            old = verify_receipt(root, state, ns.read_json(target))
            ns.require(old == receipt, "完成回执已存在且绑定不同，停止覆盖。")
        else:
            ns.immutable_text(target, body)
    ns.atomic_json(root / "daily/active.json", dict(active, status="completed", completed_at=adopted, receipt_path=path.relative_to(root).as_posix()))
    return dict(receipt, action="completed", receipt_path=path.relative_to(root).as_posix(), remote_sync_required=True)


def begin(project, resume_stopped=False, author_request=None, trigger_id=None):
    root, _ = load(project)
    with ns.writer_lock(root):
        _, state = load(project)
        today = date_of(stamp())
        if trigger_id is None:
            trigger_id = "author_" + ns.digest(ns.inside(root, author_request).read_text(encoding="utf-8")) if author_request else uuid.uuid4().hex
        validate_trigger(trigger_id)
        existing = root / "daily" / (today + ".json")
        if existing.exists():
            verify_receipt(root, state, ns.read_json(existing))
        active = active_record(root)
        previous = ns.inside(root, trigger_path(trigger_id))
        if previous.exists():
            receipt = verify_receipt(root, state, ns.read_json(previous))
            ns.require(trigger_id in triggers(receipt), "本次写作请求与已有完成回执不匹配。")
            if active and active.get("run_id") == receipt["run_id"] and active.get("status") != "completed":
                result = finish_locked(root, state, active)
                result["action"] = "recovered_completion"
                return result
            return dict(receipt, action="already_completed", receipt_path=previous.relative_to(root).as_posix())
        if active:
            validate_active(state, active)
            if active.get("execution_kind") == "author_requested_extra":
                author_binding(root, state, active)
            completed_missing_receipt = False
            if active["status"] == "completed":
                receipt_path = active.get("receipt_path")
                allowed = allowed_receipt_paths(active, date_of(active["completed_at"]))
                ns.require(receipt_path in allowed, "完成执行的回执路径无效。")
                completed_missing_receipt = not (root / receipt_path).exists()
                if not completed_missing_receipt:
                    old = verify_receipt(root, state, ns.read_json(root / receipt_path))
                    ns.require(old["run_id"] == active["run_id"] and old["chapter"] == active["chapter"], "完成执行和回执不是同一个任务。")
            if active["status"] in ("running", "blocked") or completed_missing_receipt:
                # 回执丢失时依据 adopt 实际时间恢复，不能把昨日采用改记为今天。
                if str(active["chapter"]) in state["chapters"]:
                    result = finish_locked(root, state, active)
                    result["action"] = "recovered_completion"
                    return result
                ns.require(active["status"] != "completed", "执行标为完成但目标章不存在，停止重复开写。")
                if not resume_stopped:
                    return dict(active, action="verify_in_progress", note="先确认旧执行是否停止；不得因为超时自动抢占。")
                ns.require(active["chapter"] == len(state["chapters"]) + 1 and prefix_fingerprint(state, active["baseline_count"]) == active["baseline_fingerprint"], "恢复目标与当前正式状态不匹配。")
                history = active.get("attempts", []) + [{"run_id": active["run_id"], "status": active["status"], "reason": active.get("reason", ""), "stopped_confirmed_at": stamp()}]
                active = dict(active, run_id=uuid.uuid4().hex, status="running", resumed_at=stamp(), attempts=history[-30:], reason="")
                bind_trigger(active, trigger_id)
                ns.atomic_json(root / "daily/active.json", active)
                return dict(active, action="resumed", remote_sync_required=True)
        ns.require(state["completion"] is None and len(state["chapters"]) < state["config"]["target_chapters"], "小说已达到目标，先处理完稿流程。")
        ns.require(set(state["inputs"]) == {"canon", "roadmap"}, "尚未完成作者设定和路线，不能自动开写。")
        ns.require(state.get("serialization", {}).get("enabled"), "每日更新要求连载冻结；旧书须按真实情况升级，不自动启用或改写旧章。")
        n = len(state["chapters"]) + 1
        active = {"schema_version": 1, "type": "novel-daily-task-v1", "book_id": state["book_id"],
                  "run_id": uuid.uuid4().hex, "work_id": state["book_id"] + ":" + today + ":" + str(n),
                  "start_date": today, "started_at": stamp(), "chapter": n, "status": "running",
                  "baseline_count": n - 1, "baseline_fingerprint": prefix_fingerprint(state, n - 1), "attempts": []}
        bind_trigger(active, trigger_id)
        if author_request:
            text = ns.inside(root, author_request).read_text(encoding="utf-8")
            active.update(execution_kind="author_requested_extra", author_request_path=author_request,
                          author_request_sha256=ns.digest(text))
            request = author_binding(root, state, active)
            ns.require(request.get("base_revision") == state["revision"], "作者加更指令基于旧进度，先重新核对当前章。")
        ns.atomic_json(root / "daily/active.json", active)
        return dict(active, action="started", remote_sync_required=True,
                    note="先原子同步本执行记录并回读确认；并发写入失败时重新读取，不能继续并行写作。")


def finish(project, run_id):
    root, _ = load(project)
    with ns.writer_lock(root):
        _, state = load(project)
        active = active_record(root)
        ns.require(active and active.get("run_id") == run_id and active.get("book_id") == state["book_id"], "执行编号已变化，停止旧执行写回。")
        return finish_locked(root, state, active)


def block(project, run_id, reason):
    root, _ = load(project)
    with ns.writer_lock(root):
        _, state = load(project)
        active = active_record(root)
        if active:
            validate_active(state, active)
        ns.require(active and active.get("run_id") == run_id and active.get("status") != "completed", "执行编号已变化或已经完成。")
        reason = re.sub(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]+", "[凭证已隐去]", reason.strip())[:2000]
        ns.require(reason, "记录真实的中断原因。")
        active.update(status="blocked", reason=reason, blocked_at=stamp())
        ns.atomic_json(root / "daily/active.json", active)
        return dict(active, remote_sync_required=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", default=".")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("begin"); s.add_argument("--resume-stopped", action="store_true", help="仅在旧执行实际停止后使用，不自动抢占")
    s.add_argument("--author-request", help="兼容既有作者指令记录，新指令无需额外登记")
    s.add_argument("--trigger-id", help="本次独立写作请求的稳定编号；重试复用，新指令新编号")
    for name in ("finish", "block"):
        s = sub.add_parser(name); s.add_argument("--run-id", required=True)
        if name == "block": s.add_argument("--reason", required=True)
    sub.add_parser("status")
    args = p.parse_args()
    try:
        if args.command == "begin": result = begin(args.project, args.resume_stopped, args.author_request, args.trigger_id)
        elif args.command == "finish": result = finish(args.project, args.run_id)
        elif args.command == "block": result = block(args.project, args.run_id, args.reason)
        else:
            root, state = load(args.project)
            result = {"book_id": state["book_id"], "active": active_record(root), "adopted_chapters": len(state["chapters"])}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ns.WorkspaceError, ValueError, KeyError, OSError) as e:
        print(json.dumps({"error": str(e), "completed": False}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
