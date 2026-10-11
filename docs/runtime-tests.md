# Tests du serveur Minecraft réel via MCP

**tests/integration.py** se connecte à deux serveurs Minecraft indépendants sur le transport MCP Streamable HTTP avec le SDK officiel Python. Le client exige **mcp 1.26.0** et s’arrête si une autre version est installée.

## Lancement

Utiliser PowerShell 7, Java 21 et Python 3.12. La commande ci-dessous suppose que l’environnement virtuel du dépôt est app\controller\.runtime\test-venv; installer les dépendances épinglées dans cet environnement avant de lancer le harness. -AcceptEula confirme que la licence Minecraft est acceptée pour ces serveurs jetables :

    $java = 'C:\Program Files\Java\jdk-21.0.12\bin\java.exe'
    $python = 'app\controller\.runtime\test-venv\Scripts\python.exe'
    python -m venv app\controller\.runtime\test-venv
    & $python -m pip install -r tests\requirements.txt
    .\scripts\test-server.ps1 -AcceptEula -Java $java -Python $python

Le lanceur démarre deux serveurs Fabric indépendants en mode test, attend leur disponibilité, puis exécute le client. Les ports MCP par défaut sont 127.0.0.1:18765/mcp et 127.0.0.1:18766/mcp. Si un cache serveur existe déjà, passer le paramètre -ServerCacheSource avec un dossier racine contenant libraries et versions pour réutiliser ces dépendances.

Pour lancer le client séparément, démarrer d’abord les deux processus serveur avec -Dstonebench.test=true, puis exécuter :

    $env:STONEBENCH_MCP_PORTS = "18765,18766"
    python tests\integration.py

La variable STONEBENCH_MCP_PORTS doit contenir exactement les deux ports où les serveurs écoutent sur localhost. Le client utilise toujours le chemin /mcp.

L’environnement serveur attendu est épinglé par le build du contrôleur : Java 21, Minecraft 1.21.11, Yarn 1.21.11+build.3, Fabric Loader 0.19.5 et Fabric Loom 1.14.10. Chaque describe_task expose ces versions et le test les vérifie.

## Couverture

Le client SDK négocie la session MCP et découvre les outils via tools/list. Il démarre une tentative 2x2-volume par processus, puis vérifie que les identifiants diffèrent. La description vérifie le budget, l’objectif, le référentiel, le repère du passage, le cadre 2×2 et la version de l’environnement.

Les scénarios utilisent les outils MCP pour vérifier l’air en (1024, 80, 1024), placer une pierre en mode test dans un seul monde, et confirmer que l’autre processus conserve de l’air au même emplacement. Ils vérifient aussi le rejet structuré d’un second start_attempt et des bornes invalides pour advance : 0, 6001, un décimal, une chaîne et un booléen.

La disponibilité des chunks est testée de deux façons : retrait des tickets avant un avancement, puis retrait pendant un avancement de 60 ticks. Le premier cas doit échouer sans exécuter de tick. Le second doit interrompre l’opération après une perte réelle, rapporter les ticks déjà exécutés et laisser le monde gelé. Le test restaure ensuite les chunks et attend que chunks_ready soit vrai.

Enfin, le test lance deux appels advance concurrents sur une même session, vérifie le nombre exact de ticks, attend pendant que le monde est au repos pour confirmer le gel, puis exécute exactement 6 000 ticks.

Les outils de test __test_* doivent être absents des serveurs de campagne et visibles uniquement avec -Dstonebench.test=true. Ils pilotent un petit scénario contrôlé et ne remplacent pas les mécanismes du serveur réel.

Le mode de reference `unit` prend environ 300 secondes pour 6000 ticks a 20 TPS. Le sprint natif mesure son debit sans plafond artificiel. Le controleur conserve une securite de 420 secondes pour `advance` et de 2400 secondes pour `transition`; HTTP et le SDK 1.26.0 acceptent explicitement 2450 secondes. Le transport serveur attend le resultat sans delai plus court. La preparation ou perte des chunks est observee au plus 120 secondes, avec `describe_task` toutes les 500 ms.

Le résultat concerne ces builds, cet environnement et ces deux processus locaux. Il ne mesure pas le débit maximal ni la conformité d’une porte.



For a short client/serialization regression, set STONEBENCH_TEST_SMOKE=1 before launching; it replaces only the final 6000-tick advance with 40 ticks. The default suite always tests 6000. The launcher also verifies every operation journal against the actual world-time increments, independently of the simulation counter. Evidence and exact results are in [docs/evidence/issue-5](evidence/issue-5/README.md).

Le lanceur accepte `-TickExecution unit|sprint` et `-SecondTickExecution unit|sprint` pour les comparaisons entre processus. `-InitialPreparationTicks 120` est réservé aux fixtures d'équivalence: il établit une préparation initiale contrôlée sur l'air avant toute construction, avec de vrais ticks conservés dans le compteur. La valeur normale est 0. Les mesures portent sur les ticks de jeu; `execution.wall_seconds` et `execution.measured_tps` décrivent séparément le temps réel. Les opérations `advance`, `act_input` et `transition` partagent le backend sélectionné. Le scénario complet #9 est `-Suite tests/transition.py`, et la preuve différentielle est `-Suite tests/transition_sprint.py -TickExecution unit -SecondTickExecution sprint -InitialPreparationTicks 120`.
