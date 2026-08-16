from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from patchlab_commons.config import CommandConfig, ExecutionConfig
from patchlab_commons.runner import (
    ExecutionUnavailable,
    ExecutorSelection,
    _container_command,
    _resolve_native_command,
    _runtime_environment,
    run_command,
    sanitized_environment,
    select_executor,
)


_DIGEST_IMAGE = "python@sha256:" + ("a" * 64)


class ExecutionSecurityTests(unittest.TestCase):
    def test_static_executor_never_runs_commands(self) -> None:
        selected = select_executor(ExecutionConfig(mode="static"))
        self.assertEqual(selected.mode, "static")
        self.assertFalse(selected.network)

    def test_native_executor_requires_explicit_acknowledgement(self) -> None:
        with self.assertRaisesRegex(ExecutionUnavailable, "requires"):
            select_executor(ExecutionConfig(mode="native"))
        selected = select_executor(
            ExecutionConfig(mode="native", allow_unsafe_native=True)
        )
        self.assertEqual(selected.mode, "native")
        self.assertTrue(selected.network)
        self.assertEqual(selected.label, "native")

    def test_static_selection_cannot_execute_a_command(self) -> None:
        with self.assertRaisesRegex(ExecutionUnavailable, "cannot execute"):
            run_command(
                CommandConfig(name="test", command=("true",)),
                "head",
                Path(tempfile.mkdtemp()),
                ExecutorSelection(mode="static"),
            )

    def test_auto_never_silently_falls_back_to_native(self) -> None:
        config = ExecutionConfig(mode="auto", container_image=_DIGEST_IMAGE)
        with patch("patchlab_commons.runner.shutil.which", return_value=None):
            with self.assertRaisesRegex(ExecutionUnavailable, "no supported container"):
                select_executor(config)

    def test_explicit_container_requires_available_runtime(self) -> None:
        config = ExecutionConfig(mode="container", container_image=_DIGEST_IMAGE)
        with patch("patchlab_commons.runner.shutil.which", return_value=None):
            with self.assertRaisesRegex(ExecutionUnavailable, "not available"):
                select_executor(config)

    def test_container_selection_preserves_limits(self) -> None:
        config = ExecutionConfig(
            mode="container",
            container_runtime="docker",
            container_image=_DIGEST_IMAGE,
            network=True,
            memory_mb=512,
            cpus=0.5,
            pids_limit=32,
            tmpfs_mb=16,
        )
        with patch("patchlab_commons.runner.shutil.which", return_value="/usr/bin/docker"):
            selected = select_executor(config)
        self.assertEqual(selected.runtime_path, "/usr/bin/docker")
        self.assertEqual(selected.label, "container:docker")
        self.assertTrue(selected.network)
        self.assertEqual(selected.memory_mb, 512)
        self.assertEqual(selected.pids_limit, 32)

    def test_container_command_has_required_isolation_flags(self) -> None:
        workspace = Path(tempfile.mkdtemp(prefix="patchlab-workspace-"))
        command_config = CommandConfig(
            name="test",
            command=("python", "-V"),
            allow_env=("SAFE_VALUE",),
        )
        selected = ExecutorSelection(
            mode="container",
            runtime_name="docker",
            runtime_path="/usr/bin/docker",
            container_image=_DIGEST_IMAGE,
            network=False,
            memory_mb=256,
            cpus=0.5,
            pids_limit=24,
            tmpfs_mb=12,
        )
        with patch.dict(os.environ, {"SAFE_VALUE": "not-in-argv"}, clear=False):
            argv = _container_command(selected, workspace, "patchlab-test", command_config)
        rendered = "\n".join(argv)
        self.assertIn("--network\nnone", rendered)
        self.assertIn("--cap-drop=ALL", argv)
        self.assertIn("--security-opt=no-new-privileges", argv)
        self.assertIn("--read-only", argv)
        self.assertIn("--pids-limit\n24", rendered)
        self.assertIn("--memory\n256m", rendered)
        self.assertIn("--cpus\n0.5", rendered)
        self.assertIn("--user\n65532:65532", rendered)
        self.assertIn(f"{workspace.resolve()}:/workspace:ro", argv)
        self.assertNotIn("docker.sock", rendered)
        self.assertIn("SAFE_VALUE", argv)
        self.assertNotIn("not-in-argv", rendered)
        self.assertEqual(argv[-3:], [_DIGEST_IMAGE, "python", "-V"])

    def test_container_network_must_be_explicit(self) -> None:
        workspace = Path(tempfile.mkdtemp())
        selected = ExecutorSelection(
            mode="container",
            runtime_name="podman",
            runtime_path="/usr/bin/podman",
            container_image=_DIGEST_IMAGE,
            network=True,
            memory_mb=128,
            cpus=1.0,
            pids_limit=16,
            tmpfs_mb=8,
        )
        argv = _container_command(
            selected,
            workspace,
            "patchlab-network",
            CommandConfig(name="test", command=("true",)),
        )
        index = argv.index("--network")
        self.assertEqual(argv[index + 1], "bridge")

    def test_runtime_environment_exposes_only_allowed_values(self) -> None:
        home = Path(tempfile.mkdtemp())
        with patch.dict(
            os.environ,
            {"SAFE_VALUE": "visible", "DEMO_TOKEN": "hidden"},
            clear=False,
        ):
            environment = _runtime_environment(home, ("SAFE_VALUE",))
        self.assertEqual(environment["SAFE_VALUE"], "visible")
        self.assertNotIn("DEMO_TOKEN", environment)
        self.assertEqual(environment["DOCKER_CONFIG"], str(home / ".docker"))

    def test_relative_native_program_cannot_escape_snapshot(self) -> None:
        parent = Path(tempfile.mkdtemp())
        cwd = parent / "repo"
        cwd.mkdir()
        outside = parent / "outside"
        outside.write_text("#!/bin/sh\n", encoding="utf-8")
        outside.chmod(outside.stat().st_mode | stat.S_IXUSR)
        with self.assertRaisesRegex(ExecutionUnavailable, "escapes"):
            _resolve_native_command(("../outside",), cwd, {"PATH": os.defpath})

    @unittest.skipIf(os.name == "nt", "POSIX process groups are required")
    def test_native_runner_terminates_descendants_after_parent_exit(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        marker = cwd / "descendant-survived"
        code = (
            "import subprocess,sys; "
            f"subprocess.Popen([sys.executable,'-c',\"import time;time.sleep(1);"
            f"open({str(marker)!r},'w').write('bad')\"]); "
            "print('parent done')"
        )
        result = run_command(
            CommandConfig(name="children", command=(sys.executable, "-c", code)),
            "head",
            cwd,
        )
        self.assertTrue(result.passed, result.stderr)
        time.sleep(1.2)
        self.assertFalse(marker.exists())

    def test_bare_native_program_is_resolved_to_absolute_path(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        resolved = _resolve_native_command(("python", "-V"), cwd, {"PATH": os.environ["PATH"]})
        self.assertTrue(Path(resolved[0]).is_absolute())
        self.assertEqual(resolved[1], "-V")


class ContainerRuntimeBehaviorTests(unittest.TestCase):
    def _runtime(self, body: str) -> Path:
        directory = Path(tempfile.mkdtemp())
        runtime = directory / "fake-runtime"
        runtime.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        runtime.chmod(0o755)
        return runtime

    def _selection(self, runtime: Path) -> ExecutorSelection:
        return ExecutorSelection(
            mode="container",
            runtime_name="docker",
            runtime_path=str(runtime),
            container_image=_DIGEST_IMAGE,
            network=False,
            memory_mb=128,
            cpus=1.0,
            pids_limit=16,
            tmpfs_mb=8,
        )

    def test_fake_container_runtime_executes_and_captures_bounded_output(self) -> None:
        runtime = self._runtime(
            "import sys\n"
            "if len(sys.argv) > 1 and sys.argv[1] == 'run':\n"
            "    print('CONTAINER-START')\n"
            "    print('x' * 40000)\n"
            "    print('CONTAINER-END')\n"
            "    print('stderr-value', file=sys.stderr)\n"
        )
        cwd = Path(tempfile.mkdtemp())
        result = run_command(
            CommandConfig(name="container", command=("python", "-V")),
            "head",
            cwd,
            self._selection(runtime),
        )
        self.assertTrue(result.passed, result.stderr)
        self.assertEqual(result.executor, "container:docker")
        self.assertFalse(result.network_enabled)
        self.assertIn("CONTAINER-START", result.stdout)
        self.assertIn("CONTAINER-END", result.stdout)
        self.assertIn("omitted", result.stdout)
        self.assertIn("stderr-value", result.stderr)

    def test_fake_container_runtime_timeout_is_reported(self) -> None:
        runtime = self._runtime(
            "import sys,time\n"
            "if len(sys.argv) > 1 and sys.argv[1] == 'run':\n"
            "    print('running', flush=True)\n"
            "    time.sleep(5)\n"
        )
        cwd = Path(tempfile.mkdtemp())
        result = run_command(
            CommandConfig(
                name="container-timeout",
                command=("python", "-V"),
                timeout_seconds=1,
            ),
            "head",
            cwd,
            self._selection(runtime),
        )
        self.assertTrue(result.timed_out)
        self.assertFalse(result.passed)
        self.assertIn("removed the isolated container", result.stderr)

    def test_missing_container_runtime_is_reported_as_launch_error(self) -> None:
        cwd = Path(tempfile.mkdtemp())
        selected = self._selection(cwd / "missing-runtime")
        result = run_command(
            CommandConfig(name="container-missing", command=("true",)),
            "head",
            cwd,
            selected,
        )
        self.assertFalse(result.passed)
        self.assertIsNone(result.exit_code)
        self.assertIn("could not start container runtime", result.stderr)

    def test_container_path_with_colon_is_rejected(self) -> None:
        workspace = Path(tempfile.mkdtemp()) / "bad:path"
        workspace.mkdir()
        with self.assertRaisesRegex(ExecutionUnavailable, "colon"):
            _container_command(
                self._selection(Path("/usr/bin/docker")),
                workspace,
                "name",
                CommandConfig(name="test", command=("true",)),
            )

    def test_unknown_executor_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ExecutionUnavailable, "cannot execute"):
            run_command(
                CommandConfig(name="test", command=("true",)),
                "head",
                Path(tempfile.mkdtemp()),
                ExecutorSelection(mode="unknown"),
            )

    def test_non_linux_container_and_auto_paths_are_explicit(self) -> None:
        with patch("patchlab_commons.runner.sys_platform_linux", return_value=False):
            with self.assertRaisesRegex(ExecutionUnavailable, "Linux"):
                select_executor(
                    ExecutionConfig(mode="container", container_image=_DIGEST_IMAGE)
                )
            selected = select_executor(
                ExecutionConfig(mode="auto", allow_unsafe_native=True)
            )
            self.assertEqual(selected.mode, "native")
            with self.assertRaisesRegex(ExecutionUnavailable, "cannot provide"):
                select_executor(ExecutionConfig(mode="auto"))

    def test_auto_without_image_or_runtime_has_clear_error(self) -> None:
        with patch("patchlab_commons.runner._find_container_runtime", return_value=("", "")):
            with self.assertRaisesRegex(ExecutionUnavailable, "no digest-pinned"):
                select_executor(ExecutionConfig(mode="auto"))
            selected = select_executor(
                ExecutionConfig(mode="auto", allow_unsafe_native=True)
            )
            self.assertEqual(selected.mode, "native")

    def test_container_mode_without_image_is_rejected_by_selector(self) -> None:
        with patch("patchlab_commons.runner._find_container_runtime", return_value=("docker", "/bin/docker")):
            with self.assertRaisesRegex(ExecutionUnavailable, "requires"):
                select_executor(ExecutionConfig(mode="container"))

    def test_home_can_be_explicitly_preserved(self) -> None:
        with patch.dict(os.environ, {"HOME": "/trusted/home"}, clear=False):
            environment = sanitized_environment(("HOME",), sandbox_home=Path("/ignored"))
        self.assertEqual(environment["HOME"], "/trusted/home")

    def test_allowed_temp_variable_is_not_overwritten(self) -> None:
        with patch.dict(os.environ, {"TMPDIR": "/trusted/tmp"}, clear=False):
            environment = sanitized_environment(
                ("TMPDIR",),
                sandbox_tmp=Path("/sandbox/tmp"),
            )
        self.assertEqual(environment["TMPDIR"], "/trusted/tmp")
        self.assertEqual(environment["TEMP"], "/sandbox/tmp")
        self.assertEqual(environment["TMP"], "/sandbox/tmp")


if __name__ == "__main__":
    unittest.main()
