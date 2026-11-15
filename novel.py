#!/usr/bin/env python3
"""V6 file journal. No model calls, daily quota, daemon, or literary score."""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

VERSION = "6.3.0"
SCHEMA = "novel-v6"
PACKAGE_FILES = {"AGENTS.md", "WORKFLOW.md", "CRAFT.md", "README.md", "THIRD_PARTY_NOTICES.md", "novel.py", "templates/plan.md", "tools/prose_check.py", "启动新书.txt"}


class Problem(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Problem(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def document(raw, name):
    value = json.loads(raw)
    require(isinstance(value, dict), name + "应为JSON对象，请恢复正确文件；未自动重置")
    return value


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def han(text):
    return sum(0x3400 <= ord(c) <= 0x4DBF or 0x4E00 <= ord(c) <= 0x9FFF
               or 0x20000 <= ord(c) <= 0x323AF for c in text)


def repo_url(value):
    require(isinstance(value, str), "仓库链接无效")
    value = value.strip().rstrip("/")
    value = value[:-4] if value.lower().endswith(".git") else value
    require(bool(re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value)), "仓库链接应为GitHub仓库首页")
    require(all(x not in {".", ".."} for x in value.split("/")[-2:]), "仓库链接无效")
    require(value.lower().rstrip("/").split("/")[-1] not in {"xiaoshuov5", "xs-ku", "xs-gl", "xiaishuo-zuozong"}, "系统、参考库与管理仓库不能作为新书目标")
    return value


def branch_name(value):
    require(isinstance(value, str) and 0 < len(value) <= 200
            and bool(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", value))
            and value != "HEAD" and ".." not in value and "//" not in value and not value.endswith(("/", "."))
            and all(not p.startswith(".") and not p.endswith(".lock") for p in value.split("/")), "分支名称无效，请使用仓库实际默认分支")
    return value


def validate_materials(files):
    try:
        texts = {key: data.decode("utf-8") for key, data in files.items()}
    except UnicodeDecodeError as e:
        raise Problem("正文、编辑意见、记忆和计划必须为有效UTF-8") from e
    require(all(text.replace("\ufeff", "").strip() for text in texts.values()), "正文、编辑意见、章后记忆和计划都应有真实内容")
    require(len(texts["review"]) <= 3000, "编辑意见过长：只保留具体问题、修改和遗留风险")
    n = han(texts["text"])
    require(5500 <= n <= 6500, f"正文{n}汉字，目标5500—6500")
    return n


class Book:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def path(self, name):
        require(isinstance(name, str) and not Path(name).is_absolute()
                and all(p and p not in {"..", "."} for p in name.split("/"))
                and "\\" not in name, "非法文件路径")
        p = self.root / name
        require(p.resolve().is_relative_to(self.root), "文件不能越过小说目录")
        return p

    def read(self, name):
        return self.path(name).read_bytes()

    def json(self, name):
        return document(self.read(name), name)

    def atomic(self, name, data):
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".novel-", dir=p.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
            directory = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def immutable(self, name, data):
        p = self.path(name)
        if p.exists():
            require(p.read_bytes() == data, "冻结文件内容冲突：" + name)
        else:
            self.atomic(name, data)

    @contextlib.contextmanager
    def lock(self):
        # OS lock exists only while the process executes. A crash releases it.
        import fcntl
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / ".novel.lock").open("a") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Problem("另一个保存操作正在执行，请稍后重试")
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def snapshot(self):
        raw = self.read("book/state.json")
        s = document(raw, "book/state.json")
        require(s.get("schema") == SCHEMA, "这是旧版或其他作品，不能用V6覆盖初始化")
        require(type(s.get("revision")) is int and 0 <= s["revision"] <= 2000 and isinstance(s.get("chapters"), dict)
                and set(s["chapters"]) == {str(n) for n in range(1, s["revision"] + 1)}, "状态版本与章序不符")
        require(type(s.get("target_chapters")) is int and 1 <= s["target_chapters"] <= 2000
                and s["revision"] <= s["target_chapters"] and s.get("chapter_han") == [5500, 6500], "目标配置无效")
        require(isinstance(s.get("book_id"), str) and bool(re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", s["book_id"])), "作品身份无效")
        require(isinstance(s.get("title"), str) and len(s["title"]) <= 300
                and isinstance(s.get("platform"), str) and len(s["platform"]) <= 80, "书名或平台配置无效")
        repo_url(s.get("repository_url"))
        branch_name(s.get("branch"))
        return s, digest(raw)

    def state(self):
        return self.snapshot()[0]

    def state_hash(self):
        return digest(self.read("book/state.json"))

    def init(self, repository, branch="main", title="", platform=""):
        repository, branch = repo_url(repository), branch_name(branch)
        require(isinstance(title, str) and len(title) <= 300 and isinstance(platform, str) and len(platform) <= 80, "书名或平台配置无效")
        with self.lock():
            require(not any(self.path(p).exists() for p in ["book/state.json", "project_config.json", "vault"]), "已有作品或旧系统，请接续原书；不要覆盖初始化")
            require(not any(p.is_file() for p in self.root.glob("book/**/*")), "检测到书稿、草稿或计划，不能建立另一部作品身份")
            s = {"schema": SCHEMA, "version": VERSION, "book_id": str(uuid.uuid4()),
                 "repository_url": repository, "branch": branch, "title": title.strip(),
                 "platform": platform.strip(), "target_chapters": 150, "chapter_han": [5500, 6500],
                 "revision": 0, "chapters": {}, "updated_at": utc()}
            self.atomic("book/state.json", encoded(s))
            self.atomic(".gitignore", b".novel.lock\n__pycache__/\n*.pyc\n") if not (self.root / ".gitignore").exists() else None
            self._index()
            return s

    def configure(self, title, platform):
        require(isinstance(title, str) and 0 < len(title.strip()) <= 300
                and isinstance(platform, str) and 0 < len(platform.strip()) <= 80, "请先选定有效平台与书名")
        with self.lock():
            s = self.state()
            require(not s["chapters"], "已有冻结章的身份不再用configure修改")
            require(not self.pending(s), "已有开写草稿，先核对当前选题，不在configure中改作品身份")
            require(title.strip() and platform.strip(), "请先选定平台与书名")
            s.update(title=title.strip(), platform=platform.strip(), updated_at=utc())
            self.atomic("book/state.json", encoded(s))
            self._index()
            return s

    def work_path(self, number):
        return f"book/work/CH{number:03}"

    def pending(self, s):
        name = self.work_path(s["revision"] + 1) + "/task.json"
        if not self.path(name).exists():
            return None
        task = self.json(name)
        require(task.get("book_id") == s["book_id"] and task.get("number") == s["revision"] + 1
                and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{8,180}", task.get("request_id", ""))), "草稿任务身份、目标章或请求编号不符")
        return task

    def begin(self, request_id):
        require(bool(re.fullmatch(r"[A-Za-z0-9_.:-]{8,180}", request_id)), "请求编号应为本次真实生成的稳定编号")
        with self.lock():
            s, baseline = self.snapshot()
            self.verify(s)
            for c in s["chapters"].values():
                if c["request_id"] == request_id:
                    self._index()
                    return {"status": "already_frozen", "chapter": c["number"], "request_id": request_id}
            require(s["title"] and s["platform"], "先完成选题与平台选择")
            require(s["revision"] < s["target_chapters"], "已达计划章数；先由作者调整全书目标")
            old = self.pending(s)
            if old:
                require(old["base_state_sha256"] == baseline, "未完成稿与正式状态不匹配，请核对变更；未自动丢弃草稿")
                return {"status": "resume", **old}
            number = s["revision"] + 1
            require(not any(p.is_file() for p in self.path(self.work_path(number)).glob("**/*")), "发现没有匹配任务的草稿文件，请先核对并恢复原任务；未给旧稿绑定新请求")
            task = {"book_id": s["book_id"], "number": number, "request_id": request_id,
                    "base_state_sha256": baseline, "created_at": utc()}
            self.atomic(self.work_path(number) + "/task.json", encoded(task))
            self._index()
            return {"status": "new", **task}

    def current(self, expected):
        s, baseline = self.snapshot()
        require(baseline == expected, "正式状态已变，必须读取新状态；不能覆盖其他执行结果")
        task = self.pending(s)
        require(task and task["book_id"] == s["book_id"] and task["base_state_sha256"] == expected, "缺少匹配的草稿任务")
        return s, task, self.work_path(task["number"])

    def assess(self, expected, decision):
        with self.lock():
            require(decision in {"ready", "revise"}, "编辑结论无效")
            s, task, work = self.current(expected)
            files = self.materials(work)
            review = {"schema": "novel-v6-assessment", "chapter": task["number"],
                      "decision": decision, "reviewer": "same-context-model",
                      "note": "编辑判断不等于平台签约或独立读者评价",
                      "hashes": {k: digest(v) for k, v in files.items()}, "assessed_at": utc()}
            self.atomic(work + "/assessment.json", encoded(review))
            return review

    def materials(self, work):
        files = {key: self.read(name) for key, name in {
            "text": work + "/draft.txt", "review": work + "/editorial.md",
            "memory": work + "/memory.md", "plan": "book/plan.md"}.items()}
        validate_materials(files)
        return files

    def object(self, data, suffix):
        name = f"book/objects/{digest(data)}.{suffix}"
        self.immutable(name, data)
        return name

    def freeze(self, expected, request_id, title):
        with self.lock():
            s = self.state()
            # A retry may arrive after the successful atomic state write.
            for c in s["chapters"].values():
                if c["request_id"] == request_id:
                    self.verify()
                    self._index()
                    return {"status": "already_frozen", **c}
            s, task, work = self.current(expected)
            self.verify()
            require(task["request_id"] == request_id, "请求与本章任务不符")
            require(title.strip() and len(title) <= 120, "章节标题无效")
            assessment = self.json(work + "/assessment.json")
            require(assessment.get("schema") == "novel-v6-assessment" and assessment.get("reviewer") == "same-context-model"
                    and assessment["decision"] == "ready" and assessment["chapter"] == task["number"], "编辑记录无效或尚未建议定稿")
            files = self.materials(work)
            require(assessment["hashes"] == {k: digest(v) for k, v in files.items()}, "审稿后正文、计划或记忆有变，请重新审读再定稿")
            number, now = task["number"], utc()
            body_hash = digest(files["text"])
            body = f"book/chapters/CH{number:03}_{body_hash}.txt"
            self.immutable(body, files["text"])
            attachments = {k: self.object(v, "md") for k, v in files.items() if k != "text"}
            review_path = self.object(encoded(assessment), "json")
            record = {"schema": "novel-v6-chapter", "book_id": s["book_id"], "number": number,
                      "title": title.strip(), "request_id": request_id, "text_path": body,
                      "text_sha256": body_hash, "han_count": han(files["text"].decode()),
                      "assessment_path": review_path, "assessment_sha256": digest(encoded(assessment)),
                      "attachments": attachments, "hashes": assessment["hashes"],
                      "previous_record_sha256": s["chapters"].get(str(number - 1), {}).get("record_sha256"),
                      "frozen_at": now}
            record_path = self.object(encoded(record), "json")
            item = {"number": number, "title": title.strip(), "request_id": request_id,
                    "text_path": body.removeprefix("book/"), "text_sha256": body_hash,
                    "record_path": record_path.removeprefix("book/"), "record_sha256": digest(encoded(record)),
                    "han_count": record["han_count"], "frozen_at": now}
            s["chapters"][str(number)] = item
            s.update(revision=number, updated_at=now)
            # This is the sole adoption point. Orphan objects before it are never chapters.
            self.atomic("book/state.json", encoded(s))
            self._index()
            return {"status": "frozen", **item}

    def verify(self, state=None):
        s = self.state() if state is None else state
        previous = None
        requests = set()
        for n in range(1, s["revision"] + 1):
            c = s["chapters"][str(n)]
            require(c["number"] == n and c["request_id"] not in requests, "章序或请求重复")
            require(c["record_path"] == f"objects/{c['record_sha256']}.json"
                    and c["text_path"] == f"chapters/CH{n:03}_{c['text_sha256']}.txt", "冻结文件路径与版本不符")
            requests.add(c["request_id"])
            body = self.read("book/" + c["text_path"])
            raw = self.read("book/" + c["record_path"])
            require(digest(body) == c["text_sha256"] and digest(raw) == c["record_sha256"], f"第{n}章冻结正文或记录被改动")
            r = document(raw, f"第{n}章冻结记录")
            require(r["schema"] == "novel-v6-chapter" and r["book_id"] == s["book_id"]
                    and r["number"] == n and r["request_id"] == c["request_id"]
                    and r["text_path"] == "book/" + c["text_path"]
                    and r["text_sha256"] == c["text_sha256"]
                    and r["title"] == c["title"] and r["han_count"] == c["han_count"]
                    and r["frozen_at"] == c["frozen_at"]
                    and r["previous_record_sha256"] == previous, f"第{n}章冻结绑定或历史链不符")
            require(r["assessment_path"] == f"book/objects/{r['assessment_sha256']}.json", "审读依据必须引用不可变快照")
            a_raw = self.read(r["assessment_path"])
            require(digest(a_raw) == r["assessment_sha256"], "审读记录被改动")
            a = document(a_raw, f"第{n}章审读记录")
            require(a["schema"] == "novel-v6-assessment" and a.get("reviewer") == "same-context-model"
                    and a["decision"] == "ready" and a["chapter"] == n and a["hashes"] == r["hashes"]
                    and r["hashes"]["text"] == digest(body), "正文与实际审读版本不符")
            require(set(r["attachments"]) == {"review", "memory", "plan"}
                    and set(r["hashes"]) == {"text", "review", "memory", "plan"}, "冻结记录缺少正文、编辑意见、记忆或计划绑定")
            files = {"text": body}
            for key, name in r["attachments"].items():
                data = self.read(name)
                require(name == f"book/objects/{r['hashes'][key]}.md" and digest(data) == r["hashes"][key], "章后记忆或计划快照被改动")
                files[key] = data
            require(validate_materials(files) == c["han_count"], "冻结字数与实际正文不符")
            previous = c["record_sha256"]
        return {"status": "integrity_ok", "chapters": s["revision"], "book_id": s["book_id"],
                "scope": "文件完整性；文学质量由editorial.md说明"}

    def index(self):
        with self.lock():
            return self._index()

    def _index(self):
        s, baseline = self.snapshot()
        self.verify(s)
        pending = self.pending(s)
        phase = "WRITING" if pending else "WAITING_NEXT" if s["chapters"] else "PLANNING"
        if not s["platform"]:
            phase = "WAITING_PLATFORM"
        elif not s["title"]:
            phase = "WAITING_TOPIC"
        if s["revision"] >= s["target_chapters"]:
            phase = "COMPLETE"
        chapters = [{"number": c["number"], "title": c["title"], "han_count": c["han_count"],
                     "sha256": c["text_sha256"], "text_path": "book/" + c["text_path"],
                     "publication_status": "unconfirmed"} for c in s["chapters"].values()]
        chapters.sort(key=lambda c: c["number"])
        result = {"schema_version": 1, "engine": SCHEMA, "initialized": True,
                  "book": {"id": s["book_id"], "title": s["title"] or "待选题新书", "platform": s["platform"]},
                  "progress": {"adopted_chapters": s["revision"], "actual_han": sum(c["han_count"] for c in chapters),
                               "target_chapters": s["target_chapters"], "target_han": 6000 * s["target_chapters"]},
                  "task": {"phase": phase, "label": "接续草稿" if pending else "等待作者指令", "next_action": "读取WORKFLOW.md并按当前作品继续"},
                  "source": {"repository_url": s["repository_url"], "branch": s["branch"], "state_sha256": baseline},
                  "chapters": chapters, "generated_at": s["updated_at"]}
        self.atomic("online/index.json", encoded(result))
        return result

    def context(self):
        s, baseline = self.snapshot()
        self.verify(s)
        paths = ["book/plan.md"]
        if s["revision"]:
            c = s["chapters"][str(s["revision"])]
            r = self.json("book/" + c["record_path"])
            paths.extend([r["attachments"]["memory"], "book/" + c["text_path"]])
        pending = self.pending(s)
        return {"book_id": s["book_id"], "state_sha256": baseline, "chapter": s["revision"] + 1,
                "read_paths": paths, "work": pending,
                "note": "另读本章涉及的旧章原文；前五章和每五章定稿前累计全文审读"}

    def package_check(self):
        m = self.json("INIT_MANIFEST.json")
        require(m["version"] == VERSION and m.get("engine") == SCHEMA, "初始化包版本不匹配")
        require(set(m["files"]) == PACKAGE_FILES, "初始化包清单不完整")
        for name, sha in m["files"].items():
            require(digest(self.read(name)) == sha, "初始化包文件缺失或被改动：" + name)
        return {"version": VERSION, "status": "package_ok", "files": len(m["files"])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("--repository", required=True)
    init.add_argument("--branch", default="main")
    init.add_argument("--title", default="")
    init.add_argument("--platform", default="")
    config = sub.add_parser("configure")
    config.add_argument("--title", required=True)
    config.add_argument("--platform", required=True)
    begin = sub.add_parser("begin")
    begin.add_argument("--request", required=True)
    assess = sub.add_parser("assess")
    assess.add_argument("--expect", required=True)
    assess.add_argument("--decision", choices=["revise", "ready"], required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--expect", required=True)
    freeze.add_argument("--request", required=True)
    freeze.add_argument("--title", required=True)
    for name in ["verify", "index", "context", "status", "package-check"]:
        sub.add_parser(name)
    a = p.parse_args()
    b = Book(a.root)
    try:
        if a.cmd == "init":
            result = b.init(a.repository, a.branch, a.title, a.platform)
        elif a.cmd == "configure":
            result = b.configure(a.title, a.platform)
        elif a.cmd == "begin":
            result = b.begin(a.request)
        elif a.cmd == "assess":
            result = b.assess(a.expect, a.decision)
        elif a.cmd == "freeze":
            result = b.freeze(a.expect, a.request, a.title)
        elif a.cmd == "status":
            s, baseline = b.snapshot()
            result = {"state": s, "pending": b.pending(s), "state_sha256": baseline}
        else:
            result = getattr(b, a.cmd.replace("-", "_"))()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (Problem, OSError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as e:
        p.exit(1, "未完成：" + str(e) + "\n")


if __name__ == "__main__":
    main()
