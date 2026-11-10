"""V4.6复查回归：教材路径、接管备份、空包身份和发布源。"""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import make_init_package
import novel_state as workspace
import task_executor
from release_source_guard import assert_clean_source


class AuditRegressionTests(unittest.TestCase):
    def test_reference_and_inline_path_arguments_cannot_escape_or_use_abbreviations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for reference in (["--references", "../outside.json"], ["--references=../outside.json"],
                              ["--references", "/outside.json"], ["--refer=../outside.json"]):
                args = ["--root", "book", "brief-request", *reference, "--out", "drafts/brief.json"]
                with self.subTest(args=args), self.assertRaises(task_executor.ns.WorkspaceError):
                    task_executor.command_spec(root, {"script": "novel_state.py", "args": args})
            for output in ("--out=../outside.md", "--out=book/state.json", "--ou=drafts/abbreviated.md"):
                with self.subTest(output=output), self.assertRaises(task_executor.ns.WorkspaceError):
                    task_executor.command_spec(root, {"script": "novel_state.py", "args": ["--root", "book", "context", output]})
            for reference in (["--references", "drafts/packet.json"], ["--references=drafts/packet.json"]):
                command = {"script": "novel_state.py", "args": ["--root", "book", "brief-request", *reference, "--out=drafts/brief.json"]}
                self.assertEqual(task_executor.command_spec(root, command)[2:], command["args"])

    def test_snapshot_restores_reference_bridge_and_its_import_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); book = base / "book"
            workspace.init(book, "合成备份验证", {"strict_length": False})
            snapshot = base / "snapshot.zip"; workspace.snapshot(book, snapshot)
            with zipfile.ZipFile(snapshot) as archive:
                self.assertIn("SYSTEM/tools/reference_bridge.py", archive.namelist())
                archive.extractall(base / "restored")
            run = subprocess.run([sys.executable, "tools/reference_bridge.py", "--help"],
                                 cwd=base / "restored/SYSTEM", capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_rebuilding_from_an_active_project_keeps_its_readme_out_of_the_empty_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); source = base / "active-project"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns("__pycache__"))
            (source / "README.md").write_text("# SYNTHETIC_OLD_BOOK_ID\n原书的第99章已写完。")
            output = base / "new.zip"; make_init_package.build(source, output)
            with zipfile.ZipFile(output) as archive:
                self.assertNotIn(b"SYNTHETIC_OLD_BOOK_ID", archive.read("README.md"))
                self.assertEqual(archive.read("README.md"), (source / "templates/新书说明.md").read_bytes())
                self.assertNotIn("book/state.json", archive.namelist())


class ReleaseSourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); (self.root / "tools").mkdir()
        (self.root / ".gitignore").write_text("__pycache__/\nignored.py\n")
        (self.root / "tools/main.py").write_text("# synthetic fixture\n")
        self.git("init"); self.git("config", "user.name", "Synthetic Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("add", "."); self.git("commit", "-m", "synthetic base")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()

    def test_clean_source_returns_actual_commit(self):
        self.assertEqual(assert_clean_source(self.root, ["tools"]), self.git("rev-parse", "HEAD"))

    def test_untracked_python_source_is_rejected(self):
        (self.root / "tools/new.py").write_text("# synthetic untracked fixture")
        with self.assertRaises(workspace.WorkspaceError): assert_clean_source(self.root, ["tools"])

    def test_ignored_python_source_is_also_rejected(self):
        (self.root / "tools/ignored.py").write_text("# synthetic ignored source")
        self.assertFalse(self.git("status", "--porcelain"))
        with self.assertRaises(workspace.WorkspaceError): assert_clean_source(self.root, ["tools"])

    def test_modified_tracked_source_is_rejected(self):
        (self.root / "tools/main.py").write_text("# modified synthetic fixture")
        with self.assertRaises(workspace.WorkspaceError): assert_clean_source(self.root, ["tools"])

    def test_ignored_compiled_cache_does_not_block_a_valid_build(self):
        cache = self.root / "tools/__pycache__"; cache.mkdir()
        (cache / "main.pyc").write_bytes(b"synthetic cache bytes")
        self.assertEqual(assert_clean_source(self.root, ["tools"]), self.git("rev-parse", "HEAD"))


if __name__ == "__main__": unittest.main()
