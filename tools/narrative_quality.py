#!/usr/bin/env python3
"""V4.3写作资料与证据检查。只校验文件，不生成文学通过结论。"""
from __future__ import annotations

import json
from pathlib import Path
import re


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def query_terms(value):
    if not nonempty(value):
        return []
    return list(dict.fromkeys(term.lower() for term in re.split(r"[\s,，;；]+", value.strip())
                              if any(char.isalnum() for char in term)))


def enabled(state):
    return state["config"].get("narrative_review_required", False) is True


def evidence(root, state, text, chapter, item, a, current_only=False):
    a.require(isinstance(item, dict), "叙事证据须含章号、正文版本与引文。")
    n = item.get("chapter")
    a.require(type(n) is int and 1 <= n <= chapter and (not current_only or n == chapter), "叙事证据章号无效。")
    a.require(n == chapter or str(n) in state["chapters"], "叙事证据不是本书已采用章节。")
    body = text if n == chapter else a.inside(root, state["chapters"][str(n)]["text_path"]).read_text(encoding="utf-8")
    a.require(item.get("sha256") == a.digest(body) and a.quote_exists(body, item.get("quote")), "叙事证据已过期或引文不在正文。")


def evidence_list(root, state, text, chapter, values, a, current_only=True):
    a.require(isinstance(values, list) and values, "缺少定位到正文的叙事证据。")
    for item in values:
        evidence(root, state, text, chapter, item, a, current_only)


def history_index(root, state, a):
    entries = [{"chapter": n, "title": state["chapters"][str(n)]["title"],
                "text_sha256": state["chapters"][str(n)]["text_sha256"],
                "record_sha256": state["chapters"][str(n)]["record_sha256"],
                "summary": rec["summary"], "progression": rec["progression"]}
               for n, rec in a.records(root, state)]
    return {"index_sha256": a.digest(encoded(entries)), "record_count": len(entries), "entries": entries}


def search_history(root, state, query, limit, before, a):
    a.require(nonempty(query), "提供人物、目标、办法、物品或关系关键词；空检索不算反重复检查。")
    a.require(type(limit) is int and 1 <= limit <= 50, "历史候选数量须为1—50。")
    end = len(state["chapters"]) + 1 if before is None else before
    a.require(type(end) is int and 1 <= end <= len(state["chapters"]) + 1, "历史检索上界无效。")
    index = history_index(root, state, a)
    terms = query_terms(query)
    a.require(terms, "检索词只有分隔符或标点，不能算有效历史检索。")
    matches = []
    for entry in index["entries"]:
        if entry["chapter"] >= end:
            continue
        haystack = encoded({k: entry[k] for k in ("title", "summary", "progression")}).lower()
        hits = [term for term in terms if term in haystack]
        if hits:
            matches.append(dict(entry, matched_terms=hits, keyword_hits=len(hits)))
    matches.sort(key=lambda x: (x["keyword_hits"], x["chapter"]), reverse=True)
    return {"index_sha256": index["index_sha256"], "indexed_records": index["record_count"],
            "scanned_records": sum(entry["chapter"] < end for entry in index["entries"]),
            "before_chapter": end, "matching_records": len(matches), "candidates": matches[:limit],
            "note": "只检索全书摘要与实际推进；不是语义去重或全文已读证明。未命中须换别名、办法、关系查询并回查原文。"}


def brief_bindings(state, a):
    n = len(state["chapters"]) + 1
    a.require(set(state["inputs"]) == {"canon", "roadmap"}, "先登记设定与路线再准备写作任务书。")
    a.require(not state["needs_revalidation"] and state["completion"] is None, "先处理旧任务或完稿状态。")
    a.require(n <= state["config"]["target_chapters"], "已到全书目标；不能再创建下一章任务书。")
    return {"schema_version": 1, "book_id": state["book_id"], "chapter": n,
            "base_revision": state["revision"], "canon_sha256": state["inputs"]["canon"]["sha256"],
            "roadmap_sha256": state["inputs"]["roadmap"]["sha256"]}


def surface_scan(text):
    """高特异性提醒，不按普通编号、词频、句长判断AI或文学质量。"""
    rules = {
        "production_phrase": r"(?:本章|第[零〇一二三四五六七八九十百千两0-9]{1,8}章)(?:完成的是|的故事进程|的写作目标|的审核结果)",
        "control_field": r"(?<![A-Za-z0-9_])(?:state_revision|text_sha256|record_sha256|MEANINGFUL_STATE_DELTA|DELETE TEST|ANTI-LOOP|PASS_WITH_RISK)(?![A-Za-z0-9_])",
        "inline_annotation": r"【(?:钩|爽|伏|高潮|慢)】",
    }
    findings = []
    for rule, pattern in rules.items():
        for match in re.finditer(pattern, text):
            findings.append({"id": f"{rule}:{match.start()}", "rule": rule,
                             "start": match.start(), "end": match.end(), "quote": match.group()})
    return sorted(findings, key=lambda x: (x["start"], x["rule"]))


def brief_skeleton(state, a):
    return dict(brief_bindings(state, a), decision="pending", writer_brief="",
                hard_boundaries=[""], reader_promise="", history_queries=[""],
                scene_plan=[{"purpose": "", "target_han": state["config"]["chapter_han_min"]}])


def validate_brief(state, brief, a):
    a.require(isinstance(brief, dict), "写作任务书须为对象。")
    a.require(all(brief.get(k) == v for k, v in brief_bindings(state, a).items()), "写作任务书基于旧书、旧进度或旧设定路线。")
    a.require(brief.get("decision") == "ready" and nonempty(brief.get("writer_brief")) and nonempty(brief.get("reader_promise")), "写作任务书尚未完成。")
    boundaries = brief.get("hard_boundaries")
    a.require(isinstance(boundaries, list) and boundaries and all(nonempty(x) for x in boundaries), "任务书须保留本章相关硬边界。")
    scenes = brief.get("scene_plan")
    a.require(isinstance(scenes, list) and scenes, "先安排有作用的场景，再写长章。")
    for scene in scenes:
        a.require(isinstance(scene, dict) and nonempty(scene.get("purpose")) and type(scene.get("target_han")) is int and scene["target_han"] > 0, "场景须有具体作用与正整数汉字预算。")
    if state["config"]["strict_length"]:
        total = sum(x["target_han"] for x in scenes)
        a.require(state["config"]["chapter_han_min"] <= total <= state["config"]["chapter_han_max"], "场景预算合计与本书章长不符。预算不等于正文实测字数。")
    queries = brief.get("history_queries")
    a.require(isinstance(queries, list) and (not state["chapters"] or queries) and all(query_terms(x) for x in queries), "非首章须准备有效历史检索词，不能只填标点；首章可留空列表。")
    prose = "\n".join([brief["writer_brief"], brief["reader_promise"], *boundaries, *[x["purpose"] for x in scenes]])
    a.require(not surface_scan(prose), "干净任务书含制作字段、审稿标签或制作句；控制信息留在任务书元数据。")
    return brief


def request_brief(root, out, a):
    state = a.load_state(root); a.verify_files(root, state)
    target = Path(out).resolve()
    a.require(not target.exists() and not target.is_relative_to(Path(root).resolve()), "任务书草稿用作品目录外的新路径，不能覆盖已有资料。")
    a.atomic_json(target, brief_skeleton(state, a))
    return {"path": str(target), "decision": "pending", "note": "GPT读真实来源后填写；模板不算完成。"}


def check_brief(root, path, a):
    with a.writer_lock(root):
        state = a.load_state(root); a.verify_files(root, state)
        brief = validate_brief(state, a.read_json(path), a)
        body = json.dumps(brief, ensure_ascii=False, indent=2) + "\n"; sha = a.digest(body)
        relative = f"briefs/CH{brief['chapter']:03d}_{sha}.json"
        a.immutable_text(a.inside(root, relative), body)
        state.setdefault("writing_briefs", {})[str(brief["chapter"])] = {"path": relative, "sha256": sha}
        a.atomic_json(Path(root) / "state.json", state)
    return {"path": relative, "sha256": sha, "valid_mechanically": True,
            "note": "不改变候选、修订次数或冻结事实；不证明任务书已完整提取语义约束。"}


def current_brief(root, state, a):
    pin = state.get("writing_briefs", {}).get(str(len(state["chapters"]) + 1))
    a.require(isinstance(pin, dict), "先brief-request、实际填写并brief-check，再生成写作资料或发布前检查。")
    body = a.inside(root, pin["path"]).read_text(encoding="utf-8")
    a.require(a.digest(body) == pin["sha256"], "已登记写作任务书被改写。")
    return validate_brief(state, json.loads(body), a), pin["sha256"]


def writer_packet(root, state, a):
    brief, _ = current_brief(root, state, a)
    parts = ["# 本章写作任务", "书名：" + state["title"], brief["writer_brief"], "## 必须保留的故事边界", *brief["hard_boundaries"],
             "## 本章读者体验", brief["reader_promise"], "## 场景安排"]
    for i, scene in enumerate(brief["scene_plan"], 1):
        parts.append(f"{i}. {scene['purpose']}（约{scene['target_han']}汉字，按叙事需要调整）")
    if state["chapters"]:
        item = state["chapters"][str(len(state["chapters"]))]
        parts += ["## 上一章正式正文", a.inside(root, item["text_path"]).read_text(encoding="utf-8")]
    parts.append("请只写人物在故事中的行动、语言和体验；任务说明不属于正文。")
    return "\n\n".join(parts)


def reader_packet(root, state, text, a, history_from=None, history_to=None):
    """只用已采用正文、带原文证据的读者回顾及当前候选；绝不注入canon/roadmap/原始章后摘要。"""
    count = len(state["chapters"])
    partial = history_from is not None or history_to is not None
    start = 1 if history_from is None else history_from
    end = count if history_to is None else history_to
    a.require(type(start) is int and type(end) is int and 1 <= start <= end + 1 and 0 <= end <= count, "读者资料分批范围无效。")
    if count:
        a.require(start <= count and start <= end, "读者资料分批范围为空。")
    parts = ["# 限信息阅读资料", "书名：" + state["title"], "这里只含已写内容。采用不等于平台发布；没有真实读者或独立模型的效果证明。"]
    coverage = {}
    if partial:
        parts.append(f"分批资料：仅覆盖此前第{start}—{end}章与当前候选，其他前文尚未在本包覆盖。")
    for n in range(start, end + 1):
        item = state["chapters"][str(n)]
        gate = state.get("serialization", {}).get("gates", {}).get(str(n))
        review = None
        if not partial and n <= count - 3 and gate:
            body = a.inside(root, gate["path"]).read_text(encoding="utf-8")
            a.require(a.digest(body) == gate["sha256"], "历史读者回顾的检查文件已改变。")
            report = json.loads(body)
            a.require(report.get("text_sha256") == item["text_sha256"] and report.get("record_sha256") == item["record_sha256"], "历史读者回顾与冻结正文或记录不符。")
            review = report.get("narrative_review")
        if isinstance(review, dict) and isinstance(review.get("reader_updates"), list) and review["reader_updates"]:
            updates = review["reader_updates"]
            for update in updates:
                a.require(isinstance(update, dict) and update.get("kind") in ("observed", "claim", "uncertain") and nonempty(update.get("statement")), "历史读者回顾格式损坏。")
                evidence_list(root, state, "", count + 1, update.get("evidence"), a, current_only=False)
            parts.append(f"## 第{n}章读者回顾（陈述与疑点分开，不保证理解无偏差）\n" + json.dumps(updates, ensure_ascii=False, indent=2))
            coverage[str(n)] = {"text_sha256": item["text_sha256"], "mode": "reader_recap", "release_sha256": gate["sha256"]}
        else:
            parts.append(f"## 第{n}章正式正文\n" + a.inside(root, item["text_path"]).read_text(encoding="utf-8"))
            coverage[str(n)] = {"text_sha256": item["text_sha256"], "mode": "full_text"}
    parts.append("## 当前候选正文\n" + text)
    coverage[str(count + 1)] = {"text_sha256": a.digest(text), "mode": "full_text"}
    return "\n\n".join(parts), coverage


def skeleton(root, state, text, record, a):
    brief, _ = current_brief(root, state, a)
    _, coverage = reader_packet(root, state, text, a)
    ev = {"chapter": record["chapter"], "sha256": a.digest(text), "quote": ""}
    return {"schema_version": 1,
            "actual_scenes": [{"event": "", "choice": "", "change": "", "evidence": [dict(ev)]}],
            "plan_comparison": "",
            "reader": {"mode": "pending", "limitation": "", "coverage": coverage,
                       "understanding": "", "information_load": "", "promise_delivery": "", "evidence": [dict(ev)], "issues": []},
            "character_causality": {key: {"status": "pending", "conclusion": "", "evidence": [dict(ev)]}
                                    for key in ("opposition", "dialogue", "aftermath")},
            "history": {"index_sha256": history_index(root, state, a)["index_sha256"],
                        "queries": list(brief["history_queries"]), "comparisons": [], "no_match_reason": ""},
            "reader_updates": [], "reader_update_note": "",
            "surface_findings": [dict(item, decision="pending", reason="") for item in surface_scan(text)]}


def validate(root, state, text, record, review, a):
    a.require(isinstance(review, dict) and review.get("schema_version") == 1, "缺少V4.3叙事检查。")
    n = record["chapter"]
    scenes = review.get("actual_scenes")
    a.require(isinstance(scenes, list) and scenes and nonempty(review.get("plan_comparison")), "先从正文提取实际场景，再说明与任务书的差异。")
    for scene in scenes:
        a.require(isinstance(scene, dict) and all(nonempty(scene.get(k)) for k in ("event", "choice", "change")), "实际场景缺少事件、选择或实际变化。未改变也应如实解释。")
        evidence_list(root, state, text, n, scene.get("evidence"), a)
    reader = review.get("reader", {})
    a.require(isinstance(reader, dict) and reader.get("mode") in ("same_context_approximation", "isolated_input"), "读者审读须如实声明同上下文近似或独立输入，不冒充真实读者。")
    a.require(all(nonempty(reader.get(k)) for k in ("limitation", "understanding", "information_load", "promise_delivery")), "限信息审读缺少理解、信息负担、承诺兑现或局限说明。")
    _, coverage = reader_packet(root, state, text, a)
    a.require(reader.get("coverage") == coverage, "读者审读没有绑定当前候选及前情的实际来源版本。")
    evidence_list(root, state, text, n, reader.get("evidence"), a)
    issues = reader.get("issues")
    a.require(isinstance(issues, list), "读者问题清单须如实保留。")
    for issue in issues:
        a.require(isinstance(issue, dict) and issue.get("severity") in ("must_fix", "verify", "suggestion") and issue.get("status") in ("open", "resolved", "not_issue") and nonempty(issue.get("reason")), "读者问题须分级、给出处置状态与理由。")
        evidence(root, state, text, n, issue.get("evidence"), a)
        a.require(not (issue["status"] == "open" and issue["severity"] in ("must_fix", "verify")), "读者理解问题仍须修复或查证，不能先冻结。")
    checks = review.get("character_causality", {})
    for key in ("opposition", "dialogue", "aftermath"):
        check = checks.get(key, {}) if isinstance(checks, dict) else {}
        allowed = ("reviewed", "not_applicable", "offstage") if key == "opposition" else ("reviewed", "not_applicable")
        a.require(isinstance(check, dict) and check.get("status") in allowed and nonempty(check.get("conclusion")), f"缺少{key}具体因果检查；无适用场景须解释，不强塞冲突或对白。")
        if check["status"] == "reviewed":
            evidence_list(root, state, text, n, check.get("evidence"), a)
        else:
            a.require(isinstance(check.get("evidence"), list), "不适用检查的证据须为列表，可为空。")
            for ev in check["evidence"]:
                evidence(root, state, text, n, ev, a)
    history = review.get("history", {})
    a.require(isinstance(history, dict) and history.get("index_sha256") == history_index(root, state, a)["index_sha256"], "全书历史检索索引已过期。")
    queries = history.get("queries")
    a.require(isinstance(queries, list) and (not state["chapters"] or queries) and all(query_terms(x) for x in queries), "反重复检索须使用有效人物、办法或关系词，不能只填标点。")
    comparisons = history.get("comparisons")
    a.require(isinstance(comparisons, list), "缺少全书相似桥段比较清单。")
    a.require(comparisons or nonempty(history.get("no_match_reason")), "未找到可比旧桥段时，说明范围、检索方式与局限。")
    seen = set()
    for item in comparisons:
        a.require(isinstance(item, dict) and nonempty(item.get("similarity")) and nonempty(item.get("difference")), "相似桥段须比较解决方式、选择及后果。")
        source = item.get("source", {})
        a.require(isinstance(source, dict) and source.get("chapter") != n and source.get("chapter") not in seen, "历史比较来源不能是当前章或重复项。")
        evidence(root, state, text, n, source, a)
        seen.add(source["chapter"])
        evidence(root, state, text, n, item.get("current_evidence"), a, current_only=True)
    updates = review.get("reader_updates")
    a.require(isinstance(updates, list) and nonempty(review.get("reader_update_note")), "读者回顾须说明本章实际揭示；没有新增也要如实解释。")
    for update in updates:
        a.require(isinstance(update, dict) and update.get("kind") in ("observed", "claim", "uncertain") and nonempty(update.get("statement")), "读者回顾须区分观察、人物声称与疑点。")
        evidence_list(root, state, text, n, update.get("evidence"), a)
    expected = surface_scan(text)
    found = review.get("surface_findings")
    a.require(isinstance(found, list) and len(found) == len(expected), "制作语言扫描结果不能删除或漏掉。")
    for actual, item in zip(found, expected):
        a.require(isinstance(actual, dict) and all(actual.get(k) == v for k, v in item.items()), "制作语言扫描位置或文本不符。")
        a.require(actual.get("decision") == "story_context" and nonempty(actual.get("reason")), "疑似制作语言仍未处理：修正文后重查；确为故事内容时说明语境。")
    return review
