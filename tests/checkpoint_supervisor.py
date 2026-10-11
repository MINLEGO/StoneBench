"""Stopped-process world replacement, used by the owning checkpoint test supervisor.

The caller must have stopped and waited for its own child Minecraft process. No PID
discovery or termination occurs here. All writes stay under the named server root.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_id(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Expected canonical UUID")
    return value


def file_map(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Unsafe/missing directory: {root}")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in immutable checkpoint: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = digest(path)
        elif not path.is_dir():
            raise ValueError(f"Unsupported checkpoint file type: {path}")
    return result


def write_json(path, value):
    partial = path.with_name(path.name + ".partial-" + str(uuid.uuid4()))
    try:
        with partial.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def validate(server, request):
    identifier = canonical_id(request["checkpoint_id"])
    canonical_id(request["request_id"])
    attempt = canonical_id(request["attempt_id"])
    control = server / "stonebench"
    store = control / "checkpoints"
    checkpoint = store / identifier
    for path in (control, store, checkpoint):
        if path.is_symlink() or path.resolve().is_relative_to(server) is False:
            raise ValueError("Checkpoint path escaped owned server root")
    manifest_path = checkpoint / "manifest.json"
    if digest(manifest_path) != request["manifest_sha256"]:
        raise ValueError("Checkpoint manifest SHA-256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["format"] != 1 or manifest["checkpoint_id"] != identifier:
        raise ValueError("Checkpoint format/identity mismatch")
    actual = file_map(checkpoint)
    actual.pop("manifest.json")
    if actual != manifest["files"]:
        raise ValueError("Checkpoint file set/content SHA-256 mismatch")
    if "world/level.dat" not in actual or any(Path(key).name == "session.lock" for key in actual):
        raise ValueError("Checkpoint world incomplete or contains process lock")
    context = json.loads((checkpoint / "context.json").read_text(encoding="utf-8"))
    identity = json.loads((control / "attempt.json").read_text(encoding="utf-8"))
    if context["attempt_id"] != attempt or identity["attempt_id"] != attempt:
        raise ValueError("Restore belongs to another attempt")
    return checkpoint, manifest, context


def apply_restore(server_root):
    """Validate/stage before swapping; preserve the old world and every historical artifact."""
    server = Path(server_root).absolute()
    if server.is_symlink() or server != server.resolve():
        raise ValueError("Server root must be a resolved real directory")
    control = server / "stonebench"
    request_path = control / "restore-request.json"
    if request_path.is_symlink():
        raise ValueError("Unsafe restore request")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    checkpoint, manifest, context = validate(server, request)
    history = control / "restore-history"
    if history.is_symlink():
        raise ValueError("Unsafe restore history")
    history.mkdir(exist_ok=True)
    transaction = history / canonical_id(request["request_id"])
    transaction.mkdir()  # A request ID cannot be applied twice.
    stage = transaction / "world-staged"
    backup = transaction / "world-before"
    world = server / "world"
    if world.is_symlink() or not world.is_dir():
        raise ValueError("Owned world is missing/unsafe")
    moved = False
    try:
        shutil.copytree(checkpoint / "world", stage, symlinks=False)
        expected = {key.removeprefix("world/"): value for key, value in manifest["files"].items() if key.startswith("world/")}
        if file_map(stage) != expected:
            raise ValueError("Staged world SHA-256 mismatch")
        # Verify the source again after copying; never publish a concurrently altered source.
        validate(server, request)
        os.replace(world, backup)
        moved = True
        os.replace(stage, world)
        marker = dict(request, status="awaiting_loaded_comparison", previous_world=str(backup.relative_to(server)),
                      preparation_game_ticks=0)
        write_json(control / "resume.json", marker)
        write_json(transaction / "transaction.json", marker)
        os.replace(request_path, transaction / "request.json")
        return marker
    except Exception as error:
        if moved:
            # Preserve an installed new world separately before restoring the old directory.
            if world.exists():
                os.replace(world, transaction / "world-failed")
            os.replace(backup, world)
        (control / "resume.json").unlink(missing_ok=True)
        write_json(transaction / "failure.json", dict(request, status="failed", diagnostic=str(error), old_world_restored=moved))
        raise


def rollback_boot(server_root, request_id, diagnostic):
    """Called only after the supervisor's failed child exited; keep all failed-world evidence."""
    server = Path(server_root).resolve()
    transaction = server / "stonebench" / "restore-history" / canonical_id(request_id)
    backup = transaction / "world-before"
    if not backup.is_dir() or backup.is_symlink() or transaction.is_symlink():
        raise ValueError("No safe restore backup")
    world = server / "world"
    if world.is_symlink():
        raise ValueError("Unsafe live world")
    os.replace(world, transaction / "world-failed-boot")
    os.replace(backup, world)
    (server / "stonebench" / "resume.json").unlink(missing_ok=True)
    write_json(transaction / "failure.json", {"status": "boot_failed", "request_id": request_id,
                                             "diagnostic": diagnostic, "old_world_restored": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", required=True)
    args = parser.parse_args()
    print(json.dumps(apply_restore(args.server_root), ensure_ascii=False))
