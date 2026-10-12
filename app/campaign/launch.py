"""Sequential lifecycle, frozen provenance and exportable failure/success archives."""
import argparse
from hashlib import sha256
from importlib.metadata import version, distributions
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

from .plan import MODEL, TASKS, digest, plan, plan_hash, require_authorization

REPO = Path(__file__).resolve().parents[2]
SOURCE_DIRS = ("app/campaign", "app/harness", "app/controller/src", "scripts", "docs/adr", "docs/agents")
SOURCE_FILES = ("app/controller/build.gradle", "app/controller/gradle.properties", "app/harness/requirements.txt",
                "app/campaign/requirements.txt",
                "docs/cadrage-alpha.md", "docs/controller.md", "docs/harness.md", "docs/measurements.md",
                "docs/verification.md", "docs/rules/regular-door.md", "docs/campaign.md", "tests/campaign.py",
                "tests/campaign_completion.py", "tests/campaign_revalidation.py", "tests/verify_journals.py")


def source_files():
    files = {path for directory in SOURCE_DIRS for path in (REPO/directory).rglob("*")
             if path.is_file() and ".runtime" not in path.parts and "__pycache__" not in path.parts}
    files.update(REPO/path for path in SOURCE_FILES if (REPO/path).is_file())
    files.update((REPO/"tests").glob("campaign*.py"))
    return sorted(files)


def snapshot_sources(root):
    inventory = {}
    for source in source_files():
        relative = source.relative_to(REPO)
        target = root / "source" / relative
        target.parent.mkdir(parents=True,exist_ok=True)
        data = source.read_bytes()
        target.write_bytes(data)
        inventory[relative.as_posix()] = digest(data)
    jar = REPO/"app/controller/build/libs/stonebench-controller-0.1.0.jar"
    if not jar.exists():
        raise ValueError("Build controller before campaign launch")
    target = root/"source/controller.jar"
    target.write_bytes(jar.read_bytes())
    inventory["controller.jar"] = digest(target.read_bytes())
    return inventory


def archive(root, runtime_roots):
    """Archive only explicit owned evidence/source; secret/runtime dependencies excluded."""
    target = root.with_suffix(".tar.xz")
    entries = []
    for source in root.rglob("*"):
        if source.is_file():
            entries.append((source, "campaign/" + source.relative_to(root).as_posix()))
    for index,runtime in enumerate(runtime_roots):
        # Complete world/checkpoint/verification data, logs and settings; libraries are
        # immutable copied dependencies whose deployed hashes are in source/controller.
        for source in runtime.rglob("*"):
            relative = source.relative_to(runtime)
            if source.is_file() and not any(part in {"libraries","versions",".fabric","mods"} for part in relative.parts):
                entries.append((source, f"runtime-{index}/" + relative.as_posix()))
    inventory = [{"path":name,"bytes":source.stat().st_size,"sha256":digest(source.read_bytes())} for source,name in entries]
    manifest = {"schema":1,"plan_sha256":plan_hash(),"payloads":inventory}
    (root/"archive-manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    with tarfile.open(target,"w:xz") as stream:
        for source,name in entries:
            stream.add(source,arcname=name,recursive=False)
        stream.add(root/"archive-manifest.json",arcname="campaign/archive-manifest.json",recursive=False)
    # Verify archive bytes, including failed/incomplete attempts, before delivery.
    with tarfile.open(target,"r:xz") as stream:
        for row in inventory:
            data = stream.extractfile(row["path"]).read()
            if len(data) != row["bytes"] or digest(data) != row["sha256"]:
                raise RuntimeError("Archived payload mismatch")
    (root/"archive-check.json").write_text(json.dumps({"archive":target.name,"sha256":digest(target.read_bytes()),
        "payload_count":len(inventory),"verified":True}),encoding="utf-8")
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["plan","rehearsal","calibration","paid"])
    parser.add_argument("--output",type=Path)
    parser.add_argument("--authorization",type=Path)
    parser.add_argument("--calibration",type=Path,help="Reviewed accepted calibration status.json for the exact plan")
    parser.add_argument("--task",choices=TASKS,action="append",help="Paid task selection; repeat only for an explicitly authorized subset")
    parser.add_argument("--java",default=r"C:\Program Files\Java\jdk-21.0.12\bin\java.exe")
    parser.add_argument("--server-cache",default=r"C:\Users\minle\Documents\projets\StoneBench\app\prototype-transition\.runtime\server-cache")
    parser.add_argument("--mcp-port",type=int,default=19765)
    parser.add_argument("--game-port",type=int,default=26581)
    args=parser.parse_args()
    if args.task and args.mode!="paid":parser.error("--task is only available for paid mode")
    tasks=tuple(args.task) if args.task else TASKS
    if args.mode=="plan":
        print(json.dumps({**plan(),"plan_sha256":plan_hash()},indent=2));return
    if args.mode in {"paid","calibration"}:
        if args.authorization is None:
            parser.error("Paid inference requires --authorization for this exact plan and scope")
        require_authorization(args.authorization,args.mode,task_ids=tasks if args.mode=="paid" else None)
    if args.mode=="paid":
        if args.calibration is None:
            parser.error("Paid campaign requires accepted --calibration status.json")
        checked=json.loads(args.calibration.read_text(encoding="utf-8"))
        if checked.get("plan_sha256") != plan_hash() or checked.get("mode") != "calibration" or checked.get("calibration_validation",{}).get("accepted") is not True:
            parser.error("Calibration absent, stale or rejected; no eight-task inference permitted")
    if args.output is None:
        parser.error("An explicit new --output directory is required")
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    frozen = snapshot_sources(root)
    provenance = {"plan":plan(),"plan_sha256":plan_hash(),"mode":args.mode,"source_sha256":frozen,
        "git_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
        "packages":{item.metadata["Name"]:item.version for item in distributions()},
        "python":sys.version,"java_executable":args.java,"platform":sys.platform,
        "tasks":[],"selected_task_ids":list(tasks) if args.mode!="calibration" else list(TASKS[:1]),
        "authorized_task_ids":list(tasks) if args.mode=="paid" else None,
        "paid_inference":args.mode in {"paid","calibration"}}
    roots=[]
    failed=False
    tasks=TASKS[:1] if args.mode=="calibration" else tasks
    try:
        for task_id in tasks:
            # Independently created roots/processes; ports reused only after the
            # previous lifecycle returns and its owned children have stopped.
            attempt=root/task_id
            env=os.environ.copy()
            env.update(STONEBENCH_CAMPAIGN_TASK=task_id,STONEBENCH_CAMPAIGN_MODE=args.mode,
                       STONEBENCH_CAMPAIGN_ATTEMPT=str(attempt))
            if args.authorization:
                env["STONEBENCH_CAMPAIGN_AUTHORIZATION"] = str(args.authorization.resolve())
            env.pop("OPENROUTER_API_KEY",None)
            before=set((REPO/"app/controller/.runtime").glob("tests-*"))
            command=["pwsh","-NoProfile","-File",str(REPO/"scripts/test-server.ps1"),
                "-AcceptEula","-SkipBuild","-UseCheckpointSupervisor","-ProductionServer",
                "-ServerCount","1",
                "-Java",args.java,"-Python",sys.executable,"-Suite","app/campaign/run_attempt.py",
                "-ServerCacheSource",args.server_cache,"-BaseMcpPort",str(args.mcp_port),"-BaseGamePort",str(args.game_port)]
            print(f"{args.mode}: starting {task_id}",flush=True)
            log=root/(task_id+"-lifecycle.txt")
            process=None
            try:
                with log.open("w",encoding="utf-8") as output:
                    process=subprocess.Popen(command,cwd=REPO,env=env,stdout=output,stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=="nt" else 0)
                    returncode=process.wait()
            finally:
                if process is not None and process.poll() is None:
                    # Lifecycle owns all of its children; never search for/stop foreign PIDs.
                    import signal
                    process.send_signal(signal.CTRL_BREAK_EVENT if os.name=="nt" else signal.SIGINT)
                    try:process.wait(timeout=45)
                    except subprocess.TimeoutExpired:
                        if os.name=="nt":subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True)
                        else:process.kill()
                        process.wait()
                created=set((REPO/"app/controller/.runtime").glob("tests-*"))-before
                if len(created)==1:
                    runtime=created.pop();roots.append(runtime)
                else:
                    raise RuntimeError("Cannot establish exactly one owned runtime root")
            dependency_files = [path for path in runtime.rglob("*") if path.is_file() and
                (any(part in {"libraries","versions",".fabric","mods"} for part in path.relative_to(runtime).parts)
                 or path.name=="fabric-server.jar")]
            dependencies={path.relative_to(runtime).as_posix():digest(path.read_bytes()) for path in dependency_files}
            status=json.loads((attempt/"status.json").read_text(encoding="utf-8")) if (attempt/"status.json").exists() else {"status":"infrastructure_error"}
            provenance["tasks"].append({"task_id":task_id,"exit_code":returncode,"runtime":str(runtime),
                "deployed_dependency_sha256":dependencies,"status":status})
            (root/"campaign.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
            if returncode:
                failed=True
                # Independent failures remain auditable and do not skip later tasks.
            validation=status.get("calibration_validation" if args.mode=="calibration" else "provider_validation",{})
            if args.mode in {"calibration","paid"} and (status.get("total_tokens") is None or validation.get("accepted") is not True):
                failed=True
                provenance["campaign_stop"]="provider_usage_or_validation_rejected"
                break
            if snapshot_source_drift(frozen):
                raise RuntimeError("Source changed during campaign; comparable environment revoked")
    finally:
        (root/"campaign.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
        target=archive(root,roots)
        print(f"Archived {len(provenance['tasks'])} attempts: {target}",flush=True)
    if failed:
        raise SystemExit("One or more attempts failed; archived diagnostics retained")


def snapshot_source_drift(frozen):
    return any(not (REPO/path).exists() or digest((REPO/path).read_bytes()) != expected
        for path,expected in frozen.items() if path != "controller.jar") or digest(
            (REPO/"app/controller/build/libs/stonebench-controller-0.1.0.jar").read_bytes()) != frozen["controller.jar"]


if __name__=="__main__":
    main()
