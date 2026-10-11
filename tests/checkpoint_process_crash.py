"""Real Windows orphan-child refusal, followed by explicit owned-child stop/reprise."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from checkpoint_server import ensure_previous_child_absent
from checkpoint_restart import check


def world_files(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root / "world").rglob("*") if p.is_file() and p.name != "session.lock"}


def run(root, java, port, output):
    root = Path(root).resolve()
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/checkpoint_server.py"),
               "--server-root", str(root), "--java", java, "--port", str(port)]
    (root / "stonebench/ready").unlink(missing_ok=True)
    wrapper = subprocess.Popen(command, stdin=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    child = None
    try:
        deadline = time.monotonic() + 180
        while not (root / "stonebench/ready").exists():
            assert wrapper.poll() is None, "Initial supervisor failed"
            assert time.monotonic() < deadline, "Initial readiness timeout"
            time.sleep(.1)
        # This PID is the child just created by this test's supervisor, not a PID
        # discovered from another attempt. Production code never kills it.
        child = int((root / "server.pid").read_text())
        before = world_files(root)
        journal = (root / "stonebench/operations.jsonl").read_bytes()
        wrapper.kill()
        wrapper.wait(timeout=30)
        with_child_alive = subprocess.run(command, input="stop\n", text=True, capture_output=True, timeout=30)
        assert with_child_alive.returncode != 0, with_child_alive
        assert "still alive" in with_child_alive.stderr, with_child_alive.stderr
        assert world_files(root) == before, "Refused relaunch changed world bytes"
        assert (root / "stonebench/operations.jsonl").read_bytes() == journal
        # Also cover the Popen-before-PID-publication window using the real held lock.
        (root / "server.pid").unlink()
        lock_refusal = subprocess.run(command, input="stop\n", text=True, capture_output=True, timeout=30)
        assert lock_refusal.returncode != 0 and "World lock is held" in lock_refusal.stderr, lock_refusal.stderr
        assert world_files(root) == before
        (root / "server.pid").write_text(str(child))
        os.kill(child, signal.SIGTERM)  # Explicitly stop only this test's owned child.
        deadline = time.monotonic() + 30
        while True:
            try:
                ensure_previous_child_absent(root)
                break
            except RuntimeError:
                assert time.monotonic() < deadline, "Owned child did not exit"
                time.sleep(.1)
        child = None
        reprise = str(Path(output).with_suffix(".reprise.json"))
        check(root, java, port, reprise)
        result = {"success": True, "supervisor_killed_with_java_alive": True,
                  "refused_without_world_or_journal_mutation": True, "missing_pid_held_lock_refused": True,
                  "diagnostic": with_child_alive.stderr.strip(), "after_owned_child_stop": json.loads(Path(reprise).read_text())}
        Path(output).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        if wrapper.poll() is None:
            wrapper.stdin.write("stop\n")
            wrapper.stdin.flush()
            wrapper.wait(timeout=60)
        wrapper.stdin.close()
        if child is not None:
            os.kill(child, signal.SIGTERM)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", required=True)
    parser.add_argument("--java", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.server_root, args.java, args.port, args.output)
