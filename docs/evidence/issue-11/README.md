# Issue #11 evidence

## Executed results

- Java 21.0.12 offline build passed, including GeometryChecks and existing ObservationChecks, StreamingChecks, InputComparisonChecks and RestChecks.
- `tests/geometry.py`: real Minecraft 1.21.11 / MCP SDK 1.26.0, two fresh dedicated worlds, native sprint backend; **1 suite passed in 10.550 seconds**, with 13 geometry reports. Four opposing vanilla sticky pistons moved a 2x2 quartz door closed and open over two 8-tick advances. The closed trace contains exactly 8 complete real observations. Geometry checks themselves executed zero ticks, remained frozen and reported `mutated=false`.
- `tests/integration.py`: fresh independent controller regression, **1 suite passed in 11.526 seconds**, including the 6000-tick advance, isolation, limits, serialization and real chunk-readiness loss.
- `tests/verify_observation_artifacts.py` verified exported artifact bytes, SHA256s, row counts and trace references: geometry archive has 254 artifacts / 33861 rows; the controller archive is checked separately in `artifact-verification.json`.

The first launch also discovered an imported base unittest after the geometry suite had run. That unrelated fresh-world test failed on the already-started worlds. Importing the integration module without exporting its base class corrected test selection; both the final isolated geometry suite and a separate fresh-world base regression passed. This was a harness-selection failure, not a fabricated geometry pass.

## Source-derived fixtures

Expected results come from `docs/rules/regular-door.md` and the executable frozen table, not file structure:

| Fixture | Result / source |
| --- | --- |
| Open and closed regular 2x2 quartz door | Frame pattern satisfied, Rules 30358; closed composition satisfied, Rules 2932/31749. Piston-head inward collision faces form a valid physical enclosure. |
| Obstacle inside opened fixed frame | Frame-state failed, Rules 30358. |
| Obstacle farther down the fixed hallway ray | CONTINUABLE failed, Rules 14017 / Dummies 5274. |
| Removed physical floor / shifted frame request | Enclosure failed; passage-shifting request rejected before observation. |
| Real item entity inside construction bounds | Alpha entity exclusion failed. Bounds and entity details are retained; absence is scoped to the observed construction envelope. |
| Top and bottom input | Live declaration rejected; lateral input satisfied, including its actual driver after real repeater adaptation. |
| Two frame layers | Regular arrangement, frame state and canonical quartz composition satisfied; no universal depth-one rule. |
| Stone instead of quartz inside closed frame | Composition indeterminate: physical properties do not establish behavior-preserving quartz substitution. |
| Input and piston-head roles | Input block and piston-head circuitry retained as wiring; validated external driver/adapter separated. Arbitrary exclusion argument rejected. |
| Unprepared external influence | Coverage insufficient; continuation and influence completeness indeterminate; no alpha conformity. |
| Clock necessity, stability and temporal completeness | Indeterminate in standalone snapshot; require the downstream functional protocol. |
| Community reliability, isolation and seamless record rules | Not verified, outside alpha coverage. |

## Reproduction

```powershell
scripts/build.ps1 -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -CacheSource C:\Users\minle\.codex\worktrees\issue-7\StoneBench\app\controller\.runtime -Offline
scripts/test-server.ps1 -Suite tests/geometry.py -AcceptEula -SkipBuild -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -Python C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime\test-venv\Scripts\python.exe -ServerCacheSource 'C:\Users\minle\Documents\projets\StoneBench\app\prototype-transition\.runtime\server-cache' -BaseMcpPort 19265 -BaseGamePort 26081
# Separate fresh worlds, same launcher arguments, -Suite tests/integration.py
C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime\test-venv\Scripts\python.exe tests/verify_observation_artifacts.py docs/evidence/issue-11/geometry-artifacts.zip docs/evidence/issue-11/controller-regression-artifacts.zip
```

`geometry-summary.json` contains every geometry report. Zip archives retain the original immutable JSONL data, descriptor metadata, attempt metadata, journals and server logs. `archive-manifest.json` pins file hashes and the tested remapped controller jar. Worlds remain in the local disposable test directories named by the logs. The native source caches stay ignored and are not published; protocol revision and hashes are recorded in the rule table.

## Limits

This is real geometric diagnosis of a door fixture, not checkpoint verification, the complete alpha cycle protocol or a community record certificate. The snapshot deliberately does not certify rest, required-clock absence or temporal influence completeness. Noncanonical quartz-like materials require substitution evidence; unusual partial enclosure shapes require traversal evidence. Entity diagnostics cover the observed envelope, not arbitrary entity influence elsewhere. No dynamic volume/opening-time measurement or general sprint equivalence experiment is claimed here: the existing validated controller backend is reused unchanged. Issue #12 combines these diagnostics with its independent functional proofs; issue #13 implements the source-defined events and conditional exclusions.
