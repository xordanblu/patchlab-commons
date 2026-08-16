#!/usr/bin/env python3
"""Exercise the real Docker/Podman isolation boundary on a Linux host."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from patchlab_commons.config import CommandConfig
from patchlab_commons.runner import ExecutorSelection, run_command


def _runtime_environment(home: Path) -> dict[str, str]:
    environment: dict[str, str] = {}
    for key in ("PATH", "SYSTEMROOT", "WINDIR", "PATHEXT", "COMSPEC", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if value:
            environment[key] = value
    environment.update(
        {
            "HOME": os.fspath(home),
            "DOCKER_CONFIG": os.fspath(home / ".docker"),
            "XDG_CONFIG_HOME": os.fspath(home / ".config"),
        }
    )
    return environment


def _container_names(runtime: Path, environment: dict[str, str]) -> set[str]:
    result = subprocess.run(
        [
            os.fspath(runtime),
            "ps",
            "-a",
            "--filter",
            "name=patchlab-",
            "--format",
            "{{.Names}}",
        ],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"could not inspect container cleanup: {result.stderr.strip()}")
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--host-canary", required=True)
    args = parser.parse_args()
    runtime = Path(args.runtime).resolve()
    host_canary = Path(args.host_canary).resolve()
    workspace = Path(tempfile.mkdtemp(prefix="patchlab-container-e2e-"))
    workspace.chmod(0o755)
    (workspace / "readonly.txt").write_text("source\n", encoding="utf-8")
    secret_name = "PATCHLAB_E2E_SECRET"
    secret_value = "must-not-enter-container"
    host_canary_literal = repr(os.fspath(host_canary))
    secret_name_literal = repr(secret_name)
    code = rf'''
import os
from pathlib import Path
import socket
import subprocess
import sys

assert os.getuid() == 65532, os.getuid()
assert os.getgid() == 65532, os.getgid()
assert not Path("/var/run/docker.sock").exists()
assert not Path({host_canary_literal}).exists()
assert {secret_name_literal} not in os.environ
status = {{}}
for line in Path("/proc/self/status").read_text().splitlines():
    if ":" in line:
        key, value = line.split(":", 1)
        status[key] = value.strip()
assert os.getpid() == 1, os.getpid()
assert status.get("NoNewPrivs") == "1", status.get("NoNewPrivs")
assert int(status.get("CapEff", "1"), 16) == 0, status.get("CapEff")
assert status.get("Seccomp") == "2", status.get("Seccomp")
mounts = {{}}
for line in Path("/proc/self/mountinfo").read_text().splitlines():
    fields = line.split()
    mounts[fields[4]] = set(fields[5].split(","))
assert "ro" in mounts.get("/", set()), mounts.get("/")
assert "ro" in mounts.get("/workspace", set()), mounts.get("/workspace")
try:
    Path("/patchlab-root-write").write_text("bad")
except OSError:
    pass
else:
    raise AssertionError("container root filesystem was writable")
try:
    Path("/workspace/readonly.txt").write_text("changed")
except OSError:
    pass
else:
    raise AssertionError("workspace was writable")
try:
    Path("/workspace/evidence-from-candidate").write_text("bad")
except OSError:
    pass
else:
    raise AssertionError("candidate could alter host evidence paths")
probe = Path("/tmp/patchlab-probe")
probe.write_text("#!/bin/sh\nexit 0\n")
probe.chmod(0o755)
try:
    subprocess.run([str(probe)], check=False)
except OSError:
    pass
else:
    raise AssertionError("/tmp allowed executable files")
Path("/tmp/patchlab-ok").write_text("ok")
try:
    socket.create_connection(("1.1.1.1", 53), timeout=0.5)
except OSError:
    pass
else:
    raise AssertionError("network was available")
children = []
limited = False
try:
    for _ in range(96):
        children.append(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"]))
except OSError:
    limited = True
finally:
    for child in children:
        child.terminate()
    for child in children:
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()
assert limited, "PID limit was not reached"
print("container isolation checks passed")
'''
    selected = ExecutorSelection(
        mode="container",
        runtime_name=runtime.name,
        runtime_path=str(runtime),
        container_image=args.image,
        network=False,
        memory_mb=256,
        cpus=1.0,
        pids_limit=24,
        tmpfs_mb=16,
    )
    with tempfile.TemporaryDirectory(prefix="patchlab-e2e-runtime-") as runtime_home_raw:
        runtime_environment = _runtime_environment(Path(runtime_home_raw))
        before = _container_names(runtime, runtime_environment)
        with patch.dict(os.environ, {secret_name: secret_value}, clear=False):
            result = run_command(
                CommandConfig(
                    name="container-e2e",
                    command=("python", "-c", code),
                    timeout_seconds=30,
                ),
                "head",
                workspace,
                selected,
            )
        if not result.passed:
            raise SystemExit(
                f"container E2E failed:\nstdout={result.stdout}\nstderr={result.stderr}"
            )
        timeout_result = run_command(
            CommandConfig(
                name="container-timeout-e2e",
                command=("python", "-c", "import time; time.sleep(30)"),
                timeout_seconds=1,
            ),
            "head",
            workspace,
            selected,
        )
        if not timeout_result.timed_out or timeout_result.passed:
            raise SystemExit(
                "container timeout E2E did not report a failed timeout: "
                f"stdout={timeout_result.stdout} stderr={timeout_result.stderr}"
            )
        after = _container_names(runtime, runtime_environment)
    if after != before:
        raise SystemExit(f"PatchLab containers survived cleanup: before={before}, after={after}")
    if (workspace / "readonly.txt").read_text(encoding="utf-8") != "source\n":
        raise SystemExit("container changed the host snapshot")
    if not host_canary.is_file() or host_canary.read_text(encoding="utf-8") != "host-only\n":
        raise SystemExit("host canary changed or disappeared")
    if (workspace / "evidence-from-candidate").exists():
        raise SystemExit("candidate created evidence outside the isolated container")
    print(result.stdout.strip())
    print("container timeout cleanup checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
