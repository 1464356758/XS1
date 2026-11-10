"""前五章的写前设计与累计正文审读；程序不替代编辑决定。"""
import json
from pathlib import Path

PLAN_FIELDS = ("target_reader", "distinctive_premise", "reader_promise", "sustaining_conflict")
CHAIN_FIELDS = ("goal", "choice", "visible_result", "cost_or_reaction", "next_question")
CHECKS = ("promise_delivery", "protagonist_choice", "opposition_or_obstacle", "causal_momentum",
          "character_and_emotion", "originality", "prose_and_density", "next_chapter_pull")
SAMPLE_FIELDS = ("platform_fit", "mainline", "first_arc_payoff", "character_relationships",
                 "long_form_engine", "commercial_pitch", "remaining_weaknesses")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def enabled(state):
    return state["config"].get("opening_five_required") is True and len(state["chapters"]) < 5


def add_brief_fields(state, brief):
    if not enabled(state):
        return
    if brief["chapter"] == 1:
        brief["opening_five_plan"] = {**{key: "" for key in PLAN_FIELDS},
                                      "chapters": [{"chapter": n, **{key: "" for key in CHAIN_FIELDS}} for n in range(1, 6)],
                                      "benchmarks": [{"lesson_id": "", "observation": "", "our_adaptation": "", "our_difference": ""} for _ in range(2)]}
    else:
        brief["opening_focus"] = {"plan_sha256": state.get("opening_five_plan", {}).get("sha256", ""),
                                  **{key: "" for key in CHAIN_FIELDS}, "adaptation_to_actual": ""}


def validate_brief(state, brief, a):
    if not enabled(state):
        return
    if brief["chapter"] != 1:
        focus = brief.get("opening_focus", {})
        expected_sha = state.get("opening_five_plan", {}).get("sha256")
        a.require(nonempty(expected_sha) and isinstance(focus, dict) and focus.get("plan_sha256") == expected_sha
                  and all(nonempty(focus.get(key)) for key in (*CHAIN_FIELDS, "adaptation_to_actual")),
                  "前五章须绑定首章开篇方案，写明本章选择、结果、代价与基于已发生事实的调整。")
        return
    plan = brief.get("opening_five_plan", {})
    a.require(isinstance(plan, dict) and all(nonempty(plan.get(key)) for key in PLAN_FIELDS), "先设计前五章的目标读者、差异卖点、读者承诺和持续冲突。")
    chapters = plan.get("chapters")
    a.require(isinstance(chapters, list) and [item.get("chapter") for item in chapters if isinstance(item, dict)] == list(range(1, 6)),
              "开篇方案须完整覆盖前五章，不能只设计首章。")
    for item in chapters:
        a.require(all(nonempty(item.get(key)) for key in CHAIN_FIELDS), "前五章每章须有主动选择、可见结果、代价或反应及下一问。")
    packet = brief.get("references", {}).get("packet", {})
    lessons = {item["id"]: item for item in packet.get("lessons", [])}
    benchmarks = plan.get("benchmarks")
    a.require(isinstance(benchmarks, list) and len(benchmarks) >= 2, "开篇至少比较两部独立参考作品。")
    families, used = set(), set()
    for item in benchmarks:
        a.require(isinstance(item, dict) and all(nonempty(item.get(key)) for key in ("lesson_id", "observation", "our_adaptation", "our_difference")),
                  "开篇对照须写明来源、有效之处、本书用法与原创差异。")
        lesson = lessons.get(item["lesson_id"], {})
        scope = lesson.get("source_scope", {})
        a.require(lesson.get("kind") == "study" and scope.get("level") in ("arc", "book") and scope.get("from_unit") == 1
                  and scope.get("han_count", 0) >= state["config"].get("opening_benchmark_min_han", 10000),
                  "开篇对照须来自已登记的开篇阶段教材：每部从首单元起实读至少一万汉字，少量场景教材不能冒充。")
        a.require(item["lesson_id"] not in used, "不能把同一教材重复充作两个开篇样本。")
        used.add(item["lesson_id"]); families.add(scope.get("family_id"))
    a.require(len(families) >= 2, "同书的不同版本不能当成两部独立开篇样本。")


def register_plan(root, state, brief, a):
    if not enabled(state) or brief["chapter"] != 1:
        return
    body = encoded(brief["opening_five_plan"]); sha = a.digest(body)
    path = f"opening_plans/{sha}.json"
    a.immutable_text(a.inside(root, path), body)
    state["opening_five_plan"] = {"path": path, "sha256": sha}


def verify_plan(root, state, a):
    if not enabled(state):
        return
    pin = state.get("opening_five_plan", {})
    a.require(isinstance(pin, dict) and isinstance(pin.get("path"), str) and isinstance(pin.get("sha256"), str), "缺少前五章方案的不可变来源。")
    path = a.inside(root, pin["path"])
    a.require(path.is_file() and a.digest(path.read_text(encoding="utf-8")) == pin["sha256"], "前五章方案缺失或已被改写。")


def writer_focus(state, brief):
    if not enabled(state):
        return []
    if brief["chapter"] == 1:
        plan = brief["opening_five_plan"]
        focus = plan["chapters"][0]
        return ["## 本章开篇体验", plan["reader_promise"], *[focus[key] for key in CHAIN_FIELDS]]
    focus = brief["opening_focus"]
    return ["## 本章开篇体验", *[focus[key] for key in CHAIN_FIELDS], focus["adaptation_to_actual"]]


def coverage(state, text, chapter, a):
    return {str(n): a.digest(text) if n == chapter else state["chapters"][str(n)]["text_sha256"] for n in range(1, chapter + 1)}


def add_review_fields(root, state, text, record, brief, review, a):
    if not enabled(state):
        return
    ev = {"chapter": record["chapter"], "sha256": a.digest(text), "quote": ""}
    value = {"plan_sha256": state["opening_five_plan"]["sha256"], "read_full_scope": False,
             "coverage": coverage(state, text, record["chapter"], a),
             "checks": {key: {"decision": "pending", "conclusion": "", "evidence": [dict(ev)]} for key in CHECKS},
             "previous_question_answered": "", "next_pressure": ""}
    if record["chapter"] in (3, 5):
        value["sample_review"] = {"decision": "pending", "assessment_source": "model_editorial_review",
                                  **{key: "" for key in SAMPLE_FIELDS},
                                  "evidence": [{"chapter": n, "sha256": sha, "quote": ""} for n, sha in ((int(k), v) for k, v in value["coverage"].items())]}
    review["opening_five"] = value


def validate_review(root, state, text, record, brief, review, a, evidence_list):
    if not enabled(state):
        return
    verify_plan(root, state, a)
    n = record["chapter"]; value = review.get("opening_five", {})
    a.require(isinstance(value, dict) and value.get("plan_sha256") == state["opening_five_plan"]["sha256"], "前五章审读没有绑定当前开篇方案。")
    a.require(value.get("read_full_scope") is True and value.get("coverage") == coverage(state, text, n, a), "前五章每次采用前须累计回读第一章至当前候选的准确版本。")
    for key in CHECKS:
        check = value.get("checks", {}).get(key, {})
        a.require(check.get("decision") == "pass" and nonempty(check.get("conclusion")), "前五章仍有未完成的开篇质量检查：" + key)
        evidence_list(root, state, text, n, check.get("evidence"), a)
    a.require(nonempty(value.get("previous_question_answered")) and nonempty(value.get("next_pressure")), "写明本章回答了什么、下一章为何必须继续；首章说明当前问题。")
    if n in (3, 5):
        sample = value.get("sample_review", {})
        expected = "internal_ready_for_submission" if n == 5 else "continue"
        a.require(isinstance(sample, dict) and sample.get("decision") == expected and sample.get("assessment_source") == "model_editorial_review",
                  "开篇样稿尚未完成内部投稿审读；该结论不能冒充平台签约结果。")
        a.require(all(nonempty(sample.get(key)) for key in SAMPLE_FIELDS), "开篇样稿须审主线、首轮兑现、人物关系、长期动力、卖点表达和剩余短板。")
        values = sample.get("evidence", [])
        a.require(isinstance(values, list) and {item.get("chapter") for item in values if isinstance(item, dict)} == set(range(1, n + 1)), "开篇样稿审读须逐章提供实际正文证据。")
        evidence_list(root, state, text, n, values, a, current_only=False)
