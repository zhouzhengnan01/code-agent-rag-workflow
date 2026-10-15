"""Skill runtime preflight uses only isolated fixtures and mocked Docker calls."""
import base64
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

from backend.app import db, skill_packages
from backend.app import coding_skill_runtime as runtime


class SkillRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.patches = [patch.object(db, "DB_PATH", str(self.root / "db.sqlite")), patch.object(skill_packages, "package_root", return_value=self.root / "packages"), patch.object(runtime, "tenant_workspace", return_value=self.root)]
        for item in self.patches: item.start()
        db.init_db()
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as archive:
            archive.writestr("demo/SKILL.md", "---\nname: Demo\n---\nUse scripts/demo.py")
            archive.writestr("demo/skill.json", json.dumps({"name": "Demo", "version": "1.0.0", "dependencies": [{"type": "python", "name": "httpx", "version": ">=0.27"}, "npm:typescript@^5.7.0"]}))
            archive.writestr("demo/scripts/demo.py", "print('fixture only')")
        self.skill = skill_packages.import_package("demo.zip", raw.getvalue())
        self.agent = {"skill_ids": [self.skill["id"]]}
        self.runner = patch.object(runtime, "run_command", new=AsyncMock(return_value={"exit_code": 0, "output": json.dumps({"tools": [], "dependencies": [{"name": "httpx", "status": "missing"}], "ready": False, "automatic_install": False})})); self.run = self.runner.start()

    async def asyncTearDown(self):
        self.runner.stop()
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    async def test_verified_authorized_package_checked_in_read_only_broker(self):
        report = await runtime.execute("skill_check_environment", {"skill_id": self.skill["id"]}, self.agent, self.root)
        self.assertTrue(report["integrity_verified"])
        self.assertFalse(report["ready"])
        self.assertFalse(report["automatic_install"])
        command, mode, cwd = self.run.call_args.args
        self.assertEqual(mode, "read-only"); self.assertEqual(cwd, ".")
        self.assertTrue(command.startswith("python -c "))
        self.assertNotIn("pip install", command)

    async def test_unauthorized_skill_cannot_probe_environment(self):
        with self.assertRaises(PermissionError): await runtime.execute("skill_check_environment", {"skill_id": self.skill["id"]}, {}, self.root)
        self.run.assert_not_awaited()

    async def test_tampering_and_unregistered_extra_file_fail_closed(self):
        package = skill_packages.package_path(self.skill)
        (package / "unregistered.py").write_text("print('not run')")
        with self.assertRaisesRegex(ValueError, "文件集合"): await runtime.execute("skill_check_environment", {"skill_id": self.skill["id"]}, self.agent, self.root)
        self.run.assert_not_awaited()

    async def test_manifest_tamper_fails_hash_before_broker(self):
        (skill_packages.package_path(self.skill) / "skill.json").write_text('{}')
        with self.assertRaisesRegex(ValueError, "完整性"): await runtime.execute("skill_check_environment", {"skill_id": self.skill["id"]}, self.agent, self.root)
        self.run.assert_not_awaited()


class DependencyParserTests(unittest.TestCase):
    def test_supported_dependency_forms(self):
        self.assertEqual(runtime._dependency("python:httpx>=0.27"), {"type": "python", "name": "httpx", "version": ">=0.27"})
        self.assertEqual(runtime._dependency("npm:@scope/name@^1.2.0"), {"type": "npm", "name": "@scope/name", "version": "^1.2.0"})
        self.assertEqual(runtime._dependency("binary:node>=20")["name"], "node")

    def test_shell_injection_and_traversal_are_rejected(self):
        for value in ("python:foo;curl evil", "npm:../../secret", "npm:@scope/..", {"type": "binary", "name": "git;id"}, {"name": "httpx", "version": "$(env)"}):
            with self.assertRaises(ValueError): runtime._dependency(value)

    def test_checker_reports_missing_mismatch_and_unsupported_without_environment_output(self):
        packet = {"dependencies": [{"type": "python", "name": "present", "version": ">=2.0"}, {"type": "python", "name": "present", "version": ">=1.0,<2.0"}, {"type": "python", "name": "present", "version": "1.x"}, {"type": "binary", "name": "arbitrary-user-command", "version": ""}]}
        arguments = ["checker", base64.b64encode(json.dumps(packet).encode()).decode()]
        output = io.StringIO()
        with patch("sys.argv", arguments), patch("shutil.which", return_value=None), patch("importlib.metadata.version", return_value="1.5.0"), contextlib.redirect_stdout(output):
            exec(runtime.CHECKER, {"__name__": "__main__"})
        report = json.loads(output.getvalue())
        self.assertEqual([item["status"] for item in report["dependencies"]], ["version_mismatch", "ok", "unsupported_constraint", "unsupported"])
        self.assertEqual({item["name"] for item in report["tools"]}, {"python", "node", "npm", "git"})
        self.assertNotIn("PATH", output.getvalue())
        self.assertFalse(report["automatic_install"])


if __name__ == "__main__": unittest.main()
