"""Own one pinned Minecraft child and supervise explicit checkpoint restart requests."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import sys
import threading
from checkpoint_restore import apply_restore, recover_incomplete, rollback_boot


def serve(root, java, port, execution, test=False):
    root = Path(root).resolve()
    for required in ("fabric-server.jar", "server.properties", "mods/stonebench-controller.jar"):
        if not (root / required).is_file():
            raise ValueError("Prepared pinned server root required: " + required)
    properties = dict(line.split("=", 1) for line in (root / "server.properties").read_text(encoding="utf-8").splitlines()
                      if "=" in line and not line.lstrip().startswith("#"))
    if properties.get("level-name") != "world":
        raise ValueError("Checkpoint supervisor requires level-name=world under its owned root")
    control = root / "stonebench"
    control.mkdir(exist_ok=True)
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    process = None
    handles = []
    boot = time.time_ns()
    stopping = threading.Event()
    def listen():
        for line in sys.stdin:
            if line.strip() == "stop":
                stopping.set()
                return
    threading.Thread(target=listen, daemon=True).start()

    def stop():
        nonlocal process
        if process is not None:
            if process.poll() is None:
                process.stdin.write("stop\n")
                process.stdin.flush()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=30)
                    raise RuntimeError("Owned child required termination after stop timeout")
            process.stdin.close()
            process = None
        for handle in handles:
            handle.close()
        handles.clear()

    def start():
        nonlocal process, boot
        recover_incomplete(root)
        boot += 1
        (control / "ready").unlink(missing_ok=True)
        stdout = (logs / f"boot-{boot}-stdout.log").open("xb")
        stderr = (logs / f"boot-{boot}-stderr.log").open("xb")
        handles.extend((stdout, stderr))
        command = [java, "-Xms256M", "-Xmx1G", f"-Dstonebench.port={port}", "-Dstonebench.supervised=true",
                   f"-Dstonebench.tickExecution={execution}"]
        if test:
            command.append("-Dstonebench.test=true")
        command.extend(("-jar", "fabric-server.jar", "nogui"))
        process = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        (root / "server.pid").write_text(str(process.pid), encoding="ascii")
        deadline = time.monotonic() + 180
        while not (control / "ready").exists():
            if process.poll() is not None:
                raise RuntimeError("Owned Minecraft child exited during boot; see boot logs")
            if time.monotonic() > deadline:
                raise TimeoutError("Checkpoint boot readiness deadline reached")
            time.sleep(.1)

    try:
        start()
        while process.poll() is None and not stopping.is_set():
            request_path, response_path = control / "restore-request.json", control / "restore-response.json"
            if request_path.exists() and response_path.exists():
                request = json.loads(request_path.read_text(encoding="utf-8"))
                response = json.loads(response_path.read_text(encoding="utf-8"))
                if request["request_id"] == response["request_id"]:
                    stop()
                    apply_restore(root)
                    try:
                        start()
                    except Exception as error:
                        stop()
                        rollback_boot(root, request["request_id"], str(error))
                        raise
            time.sleep(.1)
    finally:
        stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", required=True)
    parser.add_argument("--java", required=True)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--execution", choices=("unit", "sprint"), default="sprint")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    serve(args.server_root, args.java, args.port, args.execution, args.test)
