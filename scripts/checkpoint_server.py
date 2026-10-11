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


def ensure_previous_child_absent(root):
    """Fail closed before recovery; never terminate a process discovered on disk."""
    import ctypes
    root = Path(root)
    recorded = root / "server.pid"
    if recorded.exists():
        try:
            pid = int(recorded.read_text(encoding="ascii"))
            if pid <= 0:
                raise ValueError("Invalid previous child PID")
            if os.name == "nt":
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.restype = ctypes.c_void_p
                handle = kernel.OpenProcess(0x1000, False, pid)
                if not handle:
                    if ctypes.get_last_error() != 87:  # No such PID.
                        raise RuntimeError("Previous child ownership/liveness is uncertain")
                else:
                    try:
                        code = ctypes.c_ulong()
                        if not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
                            raise RuntimeError("Previous child liveness is uncertain")
                        if code.value == 259:
                            raise RuntimeError("Previous Minecraft child is still alive; no world recovery performed")
                    finally:
                        kernel.CloseHandle(ctypes.c_void_p(handle))
            else:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise RuntimeError("Previous child is alive or uncertain; no world recovery performed")
        except (OSError, ValueError) as error:
            raise RuntimeError("Previous child ownership/liveness is uncertain") from error
    # Covers a supervisor dying between Popen and PID publication. An exclusive
    # open refuses active Java file handles, including worlds moved into history.
    locks = list((root / "world").glob("session.lock"))
    locks += list((root / "stonebench/restore-history").glob("*/world-*/session.lock"))
    for lock in locks:
        if os.name == "nt":
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.restype = ctypes.c_void_p
            kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                          wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
            handle = kernel.CreateFileW(str(lock), 0xC0000000, 0, None, 3, 0x80, None)
            if handle == ctypes.c_void_p(-1).value:
                raise RuntimeError("World lock is held or uncertain; no world recovery performed")
            kernel.CloseHandle(ctypes.c_void_p(handle))
        else:
            import fcntl
            with lock.open("rb+") as stream:
                try:
                    fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    raise RuntimeError("World lock is held or uncertain; no world recovery performed") from error


def serve(root, java, port, execution, test=False):
    root = Path(root).resolve()
    for required in ("fabric-server.jar", "server.properties", "mods/stonebench-controller.jar"):
        if not (root / required).is_file():
            raise ValueError("Prepared pinned server root required: " + required)
    properties = dict(line.split("=", 1) for line in (root / "server.properties").read_text(encoding="utf-8").splitlines()
                      if "=" in line and not line.lstrip().startswith("#"))
    if properties.get("level-name") != "world":
        raise ValueError("Checkpoint supervisor requires level-name=world under its owned root")
    ensure_previous_child_absent(root)
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
        ensure_previous_child_absent(root)
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
        try:
            start()
        except Exception as error:
            stop()
            marker = control / "resume.json"
            if marker.exists():
                pending = json.loads(marker.read_text(encoding="utf-8"))
                rollback_boot(root, pending["request_id"], str(error))
            raise
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
