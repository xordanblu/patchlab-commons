from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import commit_all, init_repo


class ActionSecurityTests(unittest.TestCase):
    def _consumer(self) -> tuple[Path, str, str]:
        repo = Path(tempfile.mkdtemp(prefix="patchlab-consumer-")) / "repo"
        init_repo(repo)
        (repo / "patchlab.toml").write_text(
            """[project]\nname = \"consumer\"\n[execution]\nmode = \"native\"\nallow_unsafe_native = true\n[scope]\nallow = [\"**\"]\n[policy]\n[[commands]]\nname = \"tests\"\ncommand = [\"python\", \"-c\", \"print('candidate command')\"]\n""",
            encoding="utf-8",
        )
        (repo / "value.txt").write_text("base\n", encoding="utf-8")
        base = commit_all(repo, "base")
        (repo / "value.txt").write_text("head\n", encoding="utf-8")
        head = commit_all(repo, "head")
        return repo, base, head

    def test_action_bootstrap_ignores_hostile_python_modules(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "action_entry.py"
        repo, base, head = self._consumer()
        marker = repo / "MODULE_HIJACKED"
        payload = f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
        for relative in (
            "sitecustomize.py",
            "usercustomize.py",
            "json.py",
            "pip/__main__.py",
            "patchlab_commons/__init__.py",
            "patchlab_commons/__main__.py",
        ):
            target = repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(payload, encoding="utf-8")

        workspace = repo.parent
        hostile_tools = workspace / "hostile-tools"
        hostile_tools.mkdir()
        tool_marker = workspace / "TOOL_HIJACKED"
        for name in ("git", "python", "docker", "podman"):
            executable = hostile_tools / name
            executable.write_text(
                f"#!/bin/sh\nprintf hijacked > {str(tool_marker)!r}\nexit 97\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
        github_output = workspace / "github-output.txt"
        summary = workspace / "summary.md"
        environment = os.environ.copy()
        environment.update(
            {
                "GITHUB_WORKSPACE": str(workspace),
                "GITHUB_OUTPUT": str(github_output),
                "GITHUB_STEP_SUMMARY": str(summary),
                "PATCHLAB_BASE": base,
                "PATCHLAB_HEAD": head,
                "PATCHLAB_REPOSITORY": repo.name,
                "PATCHLAB_CONFIG": "patchlab.toml",
                "PATCHLAB_OUTPUT": ".patchlab/action",
                "PATCHLAB_CONFIG_SOURCE": "base",
                "PATCHLAB_FAIL_ON_REVIEW": "false",
                "PATCHLAB_EXECUTION_MODE": "static",
                "PATCHLAB_CONTAINER_RUNTIME": "auto",
                "PATCHLAB_CONTAINER_IMAGE": "",
                "PATCHLAB_NETWORK": "false",
                "PYTHONPATH": str(repo),
                "PYTHONHOME": "",
                "PYTHONSTARTUP": str(repo / "sitecustomize.py"),
                "PATH": f"{hostile_tools}{os.pathsep}{environment.get('PATH', '')}",
            }
        )
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(script)],
            cwd=repo,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertFalse(tool_marker.exists())
        output = github_output.read_text(encoding="utf-8")
        self.assertIn("outcome<<", output)
        self.assertIn("needs_review", output)
        self.assertIn("bundle_sha256<<", output)
        self.assertIn("static-no-execution", summary.read_text(encoding="utf-8"))

    def test_action_refuses_mutable_local_action_layout(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "action_entry.py"
        output = Path(tempfile.mkdtemp()) / "out"
        environment = os.environ.copy()
        environment.update(
            {
                "GITHUB_WORKSPACE": str(root),
                "GITHUB_OUTPUT": str(output),
                "PATCHLAB_BASE": "0" * 40,
                "PATCHLAB_HEAD": "1" * 40,
            }
        )
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(script)],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uses: ./ is not safe", result.stderr)

    def test_composite_action_has_no_untrusted_python_bootstrap(self) -> None:
        root = Path(__file__).resolve().parents[1]
        action = (root / "action.yml").read_text(encoding="utf-8")
        self.assertNotIn("python -m pip", action)
        self.assertNotIn("python -m patchlab", action)
        self.assertNotIn("python - ", action)
        self.assertNotIn("run: python ", action)
        self.assertIn('"$python_executable" -I -S scripts/action_entry.py', action)
        self.assertIn("requires actions/setup-python", action)
        self.assertIn("working-directory: ${{ github.action_path }}", action)


if __name__ == "__main__":
    unittest.main()
