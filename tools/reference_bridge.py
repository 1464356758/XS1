#!/usr/bin/env python3
"""从实际检出的参考库准备教材；不生成正文，也不生成文学通过结论。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import novel_library as library
import novel_state as workspace


def checkout_origin(root):
    try:
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE).decode().strip()
        return {"repository_url": git("config", "--get", "remote.origin.url").removesuffix(".git").rstrip("/"),
                "commit": git("rev-parse", "HEAD")}
    except (subprocess.CalledProcessError, OSError) as error:
        raise workspace.WorkspaceError("参考库须为可核实HEAD及origin的实际Git检出。") from error


def binding(project, library_root):
    config = workspace.read_json(Path(project) / "project_config.json")
    bound = config.get("reference_library", {})
    origin = checkout_origin(library_root)
    workspace.require(bound.get("repository_url", "").rstrip("/") == origin["repository_url"],
                      "本书绑定的参考库与实际检出不符。")
    catalog = library.load(library_root)
    if bound.get("library_id"):
        workspace.require(catalog["library_id"] == bound["library_id"], "参考库身份与本书绑定不符。")
    library.verify_export_commit(library_root, origin["repository_url"], origin["commit"], catalog, [])
    return bound, origin, catalog


def prepare(project, library_root, query, out, studies=None, platform="", genre="", limit=2):
    workspace.require(type(limit) is int and 1 <= limit <= 30, "教材数量须为1—30。")
    bound, origin, catalog = binding(project, library_root)
    state_path = Path(project) / "book/state.json"
    state = workspace.load_state(state_path.parent) if state_path.is_file() else {}
    opening = state.get("config", {}).get("opening_five_required") is True and not state.get("chapters")
    found = library.search(library_root, query, platform=platform, genre=genre, limit=30 if opening else limit)
    chosen = list(dict.fromkeys(studies or [item["study_id"] for item in found["results"]]))
    if opening and not studies:
        chosen, families = [], set()
        for item in found["results"]:
            value = item["study"]; source = value["source"]
            entry = catalog["books"][source["book_id"]]
            family = entry.get("family_id", source["book_id"])
            if value.get("level") not in ("arc", "book") or source["from_chapter"] != 1 or family in families:
                continue
            manifest, lines = library.book_data(library_root, catalog, source["book_id"])
            body = "".join(lines[:manifest["chapters"][source["to_chapter"] - 1]["end_line"]])
            if workspace.han_count(body) < state["config"].get("opening_benchmark_min_han", 10000):
                continue
            chosen.append(item["study_id"]); families.add(family)
            if len(chosen) >= max(2, limit):
                break
        workspace.require(len(families) >= 2, "开篇教材不足：先实读两部独立同类开篇各至少一万汉字，保存并提交阶段教材，再准备首章摘要。")
    workspace.require(chosen, "未找到已读教材。先阅读候选原文并保存本轮拆书记录，再提交参考库后准备摘要。")
    checked = []
    for record_id in chosen:
        value = library.record(library_root, catalog, "studies", record_id)
        source = value["source"]
        library.check_source(library_root, catalog, source)
        library.evidence_check(library_root, catalog, source, value["evidence"])
        entry = catalog["books"][source["book_id"]]
        if bound.get("require_source_locations"):
            workspace.require(entry.get("origin"), "所选教材缺少Git原文定位，请在参考库同步并补核。")
        checked.append({"study_id": record_id, "book_id": source["book_id"], "title": entry["title"],
                        "declared_read_scope": {"from_unit": source["from_chapter"], "to_unit": source["to_chapter"]},
                        "platform": entry.get("platform") or "待核", "genre": entry.get("genre") or "待核"})
    result = library.export_packet(library_root, chosen, [], query, out, **{
        "repository_url": origin["repository_url"], "commit": origin["commit"]})
    return dict(result, selected=checked, source=origin,
                next_step="实际回读所选范围；用brief-request --references登记本书用法与原创安排。程序校验不等于实际审读。")


def profile(project, library_root, out):
    _, origin, catalog = binding(project, library_root)
    entries = list(catalog["books"].values())
    studies = []
    scope = {}
    for record_id in catalog["studies"]:
        value = library.record(library_root, catalog, "studies", record_id)
        source = value["source"]
        entry = catalog["books"][source["book_id"]]
        scope.setdefault(source["book_id"], set()).update(range(source["from_chapter"], source["to_chapter"] + 1))
        studies.append({"id": record_id, "sha256": catalog["studies"][record_id]["sha256"],
                        "path": catalog["studies"][record_id]["path"], "title": entry["title"], "source": source,
                        "question": value["question"], "technique": value["technique"],
                        "applicability": value["applicability"], "failure_conditions": value["failure_conditions"],
                        "terms": value["terms"], "feedback_origin": "model"})
    value = {"format": "xs-ku-reference-profile-v1", "library_id": catalog["library_id"],
             "origin": origin, "catalog_sha256": workspace.digest((Path(library_root) / "catalog.json").read_text()),
             "library_revision": catalog["revision"], "is_delivery_snapshot": True,
             "refresh_rule": "每次查库读取实际默认分支的最新catalog；本文件不限制新增原文。",
             "indexed": {"source_files": len(entries), "title_author_families": len({x.get("family_id") for x in entries}),
                         "reading_units": sum(x["chapter_count"] for x in entries),
                         "source_bytes": sum(x.get("origin", {}).get("size_bytes", 0) for x in entries),
                         "extensionless_files": sum(not Path(x.get("origin", {}).get("path", "")).suffix for x in entries)},
             "declared_study_scope": {"books": len(scope), "reading_units": sum(map(len, scope.values())),
                                      "studies": len(studies), "practices": len(catalog["practices"]),
                                      "reviews": len(catalog["reviews"]), "full_library_read": False},
             "signing_status": "作者提供时声明为签约参考小说；具体平台与送审版本未逐本核实。",
             "lessons": studies,
             "books": [{"id": key, "title": item["title"], "author": item["author"],
                        "family_id": item.get("family_id", key), "platform": item.get("platform", ""),
                        "genre": item.get("genre", ""), "genre_hints": item.get("genre_hints", []),
                        "genre_hints_basis": "filename_inference", "origin": item.get("origin"),
                        "reading_units": item["chapter_count"], "manifest_path": item["manifest_path"],
                        "manifest_sha256": item["manifest_sha256"]} for key, item in catalog["books"].items()]}
    workspace.atomic_json(Path(out), value)
    return {"path": str(Path(out).resolve()), "indexed": value["indexed"],
            "declared_study_scope": value["declared_study_scope"], "origin": origin}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--library", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--query", required=True); p.add_argument("--out", required=True)
    p.add_argument("--study", action="append"); p.add_argument("--platform", default="")
    p.add_argument("--genre", default=""); p.add_argument("--limit", type=int, default=2)
    p = commands.add_parser("profile"); p.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        if args.command == "profile":
            result = profile(args.project, args.library, args.out)
        else:
            result = prepare(args.project, args.library, args.query, args.out, args.study, args.platform, args.genre, args.limit)
    except workspace.WorkspaceError as error:
        parser.exit(2, "未完成：" + str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
