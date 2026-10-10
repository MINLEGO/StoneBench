# StoneBench

Minecraft Java 1.21.11 controller for regular DOOR attempts, exposed through MCP. This is the foundation of the alpha; construction and conformity tools follow in subsequent issues.

- [Controller and tool contract](docs/controller.md)
- [Real Minecraft/MCP integration tests](docs/runtime-tests.md)
- [Domain context](CONTEXT.md)

On Windows with PowerShell 7 and JDK 21:

```powershell
.\scripts\build.ps1 -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe'
```

To seed an independent worktree without repeated network downloads, stop source builds first and copy its read-only runtime cache (the script excludes locks and partial files):

```powershell
.\scripts\build.ps1 -Java 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe' -CacheSource 'C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime' -Offline
```

Run tests with a separate Python 3.12 environment and the pinned `tests/requirements.txt`; see the test guide. Worlds, Gradle caches and jars stay under ignored `app/controller/.runtime`. Published proof journals are under `docs/evidence/issue-5`.
