"""Compact original evidence export; no worlds/dependencies or source native text copied."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/issue-13'
OUT.mkdir(parents=True,exist_ok=True)

def sha(path):
    return hashlib.file_digest(path.open('rb'),'sha256').hexdigest()

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()

logs=['.runtime-build13-final.txt','.runtime-minecraft13-review.txt','.runtime-sprint13-final.txt','.runtime-rules13-review.txt','.runtime-protocol13-final.txt','.runtime-storage13-final.txt','.runtime-replay13-review.txt']
def logpath(name):
    current=ROOT/name
    return current if current.exists() else ROOT/'app/controller/.runtime/history13'/name
roots=[]
for name in logs[1:3]:
    text=logpath(name).read_text(encoding='utf-8-sig')
    assert 'Integration suite finished' in text, name+' did not pass all launcher checks'
    root=Path(re.search(r'Disposable server data and logs: (.+)',text).group(1).strip())
    assert root.is_relative_to(ROOT/'app/controller/.runtime'),root
    roots.append(root)
jar=ROOT/'app/controller/build/libs/stonebench-controller-0.1.0.jar'
expected_jar=sha(jar)
source_files=[p for folder in ['app/controller/src','scripts'] for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.java','.json','.py','.ps1') and '__pycache__' not in p.parts]
source_files += [ROOT/name for name in ['app/controller/build.gradle','app/controller/gradle.properties','app/controller/settings.gradle','tests/measurements.py','tests/measurements_rules.py','tests/measurements_replay.py','tests/measurements_archive.py','docs/measurements.md']]
manifest={'source_head':git('rev-parse','HEAD'),'base_head':'71c0f239c73bf15a9292e01c1fae3e6596b66f05',
          'jar_sha256':expected_jar,'versions':{'minecraft':'1.21.11','yarn':'1.21.11+build.3','fabric_loader':'0.19.5','java':'21.0.12','mcp_sdk':'1.26.0','loom':'1.14.10','gradle':'9.2.1'},
          'roots':[str(p) for p in roots],'sources':{},'copied_jars':{},'entries':{}}
files={}
def add(path,name):
    assert path.is_file() and not path.is_symlink(),path
    files[name]=path
    manifest['entries'][name]={'bytes':path.stat().st_size,'sha256':sha(path)}
for path in source_files:
    relative=path.relative_to(ROOT).as_posix()
    manifest['sources'][relative]={'sha256':sha(path),'git_blob':git('hash-object',str(path))}
    add(path,'source/'+relative)
add(jar,'build/stonebench-controller-0.1.0.jar')
for name in logs:add(logpath(name),'logs/'+name.removeprefix('.runtime-'))
for name in ['measurements-reviewed.json','measurements-sprint.json']:
    add(ROOT/'app/controller/.runtime'/name,'summaries/'+name)
for index,root in enumerate(roots):
    for server in root.glob('server-*'):
        for current,dirs,names in os.walk(server):
            dirs[:]=[d for d in dirs if d not in ('world','libraries','versions','.fabric','mods')]
            for name in names:
                path=Path(current)/name
                if path.suffix not in ('.json','.jsonl','.log','.txt','.pid') and name not in ('ready',):continue
                add(path,f'runtime-{index}/'+path.relative_to(root).as_posix())
        for path in server.rglob('mods/stonebench-controller*.jar'):
            value=sha(path)
            assert value==expected_jar,(path,value)
            manifest['copied_jars'][str(path)]=value
archive=OUT/'minecraft-proof.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,path in sorted(files.items()):z.write(path,name)
    z.writestr('evidence-manifest.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(archive) as z:
    assert len(z.namelist())==len(files)+1
    for name,expected in manifest['entries'].items():
        data=z.read(name)
        assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256'],name
    assert json.loads(z.read('evidence-manifest.json'))==manifest
manifest['archive']={'sha256':sha(archive),'bytes':archive.stat().st_size,'entries':len(files)+1,'verified':True}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(OUT/'minecraft-proof.sha256').write_text(manifest['archive']['sha256']+'  minecraft-proof.zip\n',encoding='ascii')
print(json.dumps({'archive':manifest['archive'],'source_head':manifest['source_head'],'jar_sha256':expected_jar,'copied_jars':len(manifest['copied_jars'])}))
