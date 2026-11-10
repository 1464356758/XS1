"""阻止把未提交或未跟踪的源文件标记成某个正式Git版本。"""
from pathlib import Path
import subprocess

from novel_state import WorkspaceError

PACKAGED_SUFFIXES = {".py", ".mjs", ".js", ".json", ".md", ".txt", ".html", ".css", ".svg", ".webmanifest", ".yml", ".log"}


def assert_clean_source(repository, paths):
    root = Path(repository).resolve()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)
    try:
        dirty = git("status", "--porcelain", "--untracked-files=all", "--", *paths).decode().strip()
        if dirty:
            raise WorkspaceError("发布源有未提交或未跟踪的变更，请提交后构建。")
        tracked = set(filter(None, git("ls-files", "-z", "--", *paths).decode().split("\0")))
        for relative in paths:
            target = (root / relative).resolve()
            if not target.is_relative_to(root):
                raise WorkspaceError("发布源路径必须留在仓库内。")
            candidates = target.rglob("*") if target.is_dir() else [target]
            for file in candidates:
                if not file.is_file() or any(part in ("__pycache__", "node_modules", ".git") for part in file.relative_to(root).parts):
                    continue
                if file.suffix in PACKAGED_SUFFIXES or file.name == ".gitignore":
                    if file.relative_to(root).as_posix() not in tracked:
                        raise WorkspaceError("发布源含未跟踪的可打包文件，包括被忽略的文件；请先提交或移走。")
        return git("rev-parse", "HEAD").decode().strip()
    except (subprocess.CalledProcessError, OSError) as error:
        raise WorkspaceError("无法核实发布源的Git版本。") from error
