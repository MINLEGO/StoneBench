"""Rel launch the delivered supervisor on a stopped, already-used checkpoint root."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def check(root, java, port, output):
    root = Path(root).resolve()
    control = root / "stonebench"
    logs = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "logs").glob("boot-*-*.log")}
    journal = (control / "operations.jsonl").read_bytes()
    (control / "ready").unlink(missing_ok=True)
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/checkpoint_server.py"),
                                "--server-root", str(root), "--java", java, "--port", str(port)],
                               stdin=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    def call(name, arguments=None):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": arguments or {}}}).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", body,
                                         {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                                          "MCP-Protocol-Version": "2025-11-25"})
        with urllib.request.urlopen(request, timeout=10) as response:
            envelope = json.loads(response.read())
        return envelope["result"]["structuredContent"]
    def ready():
        deadline = time.monotonic() + 180
        while True:
            if process.poll() is not None:
                raise AssertionError("Supervisor exited during relaunch")
            if (control / "ready").exists() and not (control / "restore-request.json").exists():
                try:
                    call("describe_task")
                    return
                except (OSError, ValueError, KeyError):
                    pass
            if time.monotonic() > deadline:
                raise AssertionError("Relaunch readiness timeout")
            time.sleep(.1)
    started = time.monotonic()
    try:
        ready()
        listed = call("list_checkpoints")
        assert listed["status"] == "ok", listed
        checkpoints = listed["checkpoints"]
        identifier = checkpoints[0]["checkpoint_id"]
        request = call("restore_checkpoint", {"checkpoint_id": identifier})
        assert request["status"] == "ok", request
        request_id = request["restore"]["request_id"]
        deadline = time.monotonic() + 180
        while True:
            if process.poll() is not None:
                raise AssertionError("Supervisor exited during restore after relaunch")
            try:
                description = call("describe_task")
                restoration = description.get("restoration") or {}
                if restoration.get("request_id") == request_id:
                    break
            except (OSError, ValueError, KeyError):
                pass
            if time.monotonic() > deadline:
                raise AssertionError("Restoration after relaunch timeout")
            time.sleep(.1)
        assert restoration["status"] == "equal", restoration
        assert restoration["comparison"]["useful_ticks_before_comparison"] == 0, restoration
        assert restoration["preparation_game_ticks"] == 0, restoration
        assert call("list_checkpoints")["checkpoints"] == checkpoints
        assert (control / "operations.jsonl").read_bytes().startswith(journal)
        assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in logs.items())
        result = {"success": True, "existing_boot_logs_preserved": len(logs), "historical_journal_prefix_preserved": True,
                  "checkpoints_preserved": len(checkpoints), "test_flag": False,
                  "restoration": restoration, "wall_seconds": time.monotonic() - started}
        Path(output).write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        if process.poll() is None:
            process.stdin.write("stop\n")
            process.stdin.flush()
            process.wait(timeout=60)
        process.stdin.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", required=True)
    parser.add_argument("--java", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    check(args.server_root, args.java, args.port, args.output)
