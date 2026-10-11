# Issue #11 evidence

Prepared source table and geometry fixtures; real MCP run remains pending tool registration.

Sources: `docs/rules/regular-door.md` records the native Door Rules revision and both local source-cache SHA256s. Full native documents remain local ignored evidence.

Executed before shared integration:

- `scripts/build.ps1 -Java <JDK21> -CacheSource <issue-7 runtime> -Offline`: compilation and existing observation/streaming runners passed for the initial modules.
- Local ignored Gradle init task `geometryChecksLocal`: compiled main/test classes and ran `stonebench.GeometryChecks`; passed. This avoids editing shared build.gradle during the parallel phase.
- Pinned Python 3.12 MCP venv `-m py_compile tests/geometry.py`: passed.

These pure/build checks are not Minecraft or MCP acceptance. `tests/geometry.py` is the actual server fixture, to run after describe_rules/check_geometry/test entity registration and integration of live Inputs. No checkpoint protocol or dynamic measurement has been validated by this preparation.
