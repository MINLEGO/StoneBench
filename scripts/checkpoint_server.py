"""Own one pinned Minecraft child and supervise explicit checkpoint restart requests."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import sys
import threading
from contextlib import contextmanager
from checkpoint_restore import apply_restore, recover_incomplete, rollback_boot, write_json


@contextmanager
def supervisor_lease(root):
    """One non-inherited OS handle owns the root until this supervisor exits."""
    path = Path(root) / "supervisor.lock"
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
        handle = kernel.CreateFileW(str(path), 0xC0000000, 0, None, 4, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise RuntimeError("Supervisor lease held or ownership uncertain; no world recovery performed")
        try:
            yield
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    else:
        import fcntl
        with path.open("a+b") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise RuntimeError("Supervisor lease held; no world recovery performed") from error
            yield


def ensure_previous_child_absent(root):
    """Fail closed before recovery; never terminate a process discovered on disk."""
    import ctypes
    root = Path(root)
    if (root / "stonebench/child-starting.json").exists():
        raise RuntimeError("Child launch ownership uncertain; establish its exit before removing child-starting.json")
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


def serve(root, java, port, execution, test=False, verification_mcp_port=None, verification_game_port=None):
    root = Path(root).resolve()
    with supervisor_lease(root):
        _serve_owned(root, java, port, execution, test, verification_mcp_port, verification_game_port)


def _serve_owned(root, java, port, execution, test=False, verification_mcp_port=None, verification_game_port=None):
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
    verification_thread = None
    verification_workers = None
    verification_directory = None
    heartbeat_time = 0
    verification_seen = set()
    from verification_worker import Workers, run as run_verification, VERSION
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
            starting = control / "child-starting.json"
            if starting.exists():
                owner = json.loads(starting.read_text(encoding="utf-8"))
                if owner.get("supervisor_pid") == os.getpid() and owner.get("boot") == boot:
                    starting.unlink()  # This owned child is now confirmed stopped.
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
                   f"-Dstonebench.tickExecution={execution}", "-Dstonebench.verificationSupervisor=true"]
        if test:
            command.append("-Dstonebench.test=true")
        command.extend(("-jar", "fabric-server.jar", "nogui"))
        # Fail closed even if this process dies before it can publish the new PID.
        starting = control / "child-starting.json"
        write_json(starting, {"supervisor_pid": os.getpid(), "boot": boot, "status": "child_launch_pending"})
        try:
            process = subprocess.Popen(command, cwd=root, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                       text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        except Exception:
            starting.unlink()
            raise
        (root / "server.pid").write_text(str(process.pid), encoding="ascii")
        starting.unlink()
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
            if verification_thread is None or not verification_thread.is_alive():
                for candidate in sorted((control / "verifications").glob("*/request.json")):
                    if not candidate.is_file():
                        continue
                    if candidate.parent.name in verification_seen or (candidate.parent / "result.json").exists():
                        continue
                    verification_seen.add(candidate.parent.name)
                    verification_directory = candidate.parent
                    verification_workers = Workers()
                    verification_thread = threading.Thread(target=run_verification, args=(root, candidate.parent, java, execution, test, verification_workers,
                        verification_mcp_port or port + 2, verification_game_port or int(properties["server-port"]) + 2), daemon=True)
                    verification_thread.start()
                    break
            if verification_thread is not None and verification_thread.is_alive():
                # Owner liveness is separate from progress: each finite phase has its own watchdog.
                if time.monotonic()-heartbeat_time >= 1:
                    try:
                        write_json(verification_directory / "heartbeat.json", dict(verification_workers.state(), owner_time_ms=int(time.time()*1000), supervisor_pid=os.getpid()))
                        heartbeat_time = time.monotonic()
                    except PermissionError:
                        # Windows can briefly deny replace while Java reads the old
                        # heartbeat. Keep it intact and retry on the next owner turn.
                        pass
                if (verification_directory / "cancel.json").exists() or time.monotonic()>verification_workers.phase_deadline:
                    cancelled = (verification_directory / "cancel.json").exists()
                    marker = json.loads((verification_directory / "cancel.json").read_text(encoding="utf-8")) if cancelled else {}
                    reason = marker.get("reason", "user_cancelled") if cancelled else "individual_phase_watchdog:" + verification_workers.phase
                    if not cancelled:
                        write_json(verification_directory / "cancel.json", {"reason": reason})
                    verification_workers.stop(reason)
                    with verification_workers.lock:
                        if not (verification_directory / "result.json").exists():
                            # A stalled I/O thread cannot retain the working lease
                            # after its owned JVMs are confirmed stopped.
                            request = json.loads((verification_directory / "request.json").read_text(encoding="utf-8"))
                            timed_out = reason.startswith("individual_phase_watchdog:")
                            write_json(verification_directory / "result.json", {
                                "request_id": request["request_id"], "checkpoint_id": request["checkpoint_id"],
                                "protocol_version": VERSION,
                                "manifest_sha256": request["manifest_sha256"], "criteria": [], "boundaries": [],
                                "copies": [], "verdict": "infrastructure_error", "conforms_to_alpha": False,
                                "stop_cause": "individual_phase_watchdog" if timed_out else "verification_interrupted", "first_difference": None,
                                "infrastructure_error": {"kind": "phase_timeout" if timed_out else "cancelled", "diagnostic": reason,
                                                         "progress": verification_workers.state()},
                                "retained_worker_directory": str(verification_directory),
                                "late_worker_result": "late-worker-result.json if the worker thread returns"})
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
        if verification_workers is not None:
            verification_workers.stop("owner_stopping")
        if verification_thread is not None:
            verification_thread.join(timeout=40)
        stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", required=True)
    parser.add_argument("--java", required=True)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--execution", choices=("unit", "sprint"), default="sprint")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--verification-mcp-port", type=int)
    parser.add_argument("--verification-game-port", type=int)
    args = parser.parse_args()
    serve(args.server_root, args.java, args.port, args.execution, args.test, args.verification_mcp_port, args.verification_game_port)
