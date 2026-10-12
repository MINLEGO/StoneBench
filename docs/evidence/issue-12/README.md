# Issue #12 — vérification réelle d'un checkpoint

La vérification démarre un job MCP consultable et annulable, puis exécute le protocole livré sur deux vrais serveurs Minecraft indépendants depuis le même checkpoint immuable. Le monde de travail reste gelé. Voir [le contrat](../../verification.md).

## Identification reproductible

Source exécutée : `cd24baee9c8708a89a0240a0ebc95e73e9836b8d`. La livraison ajoute ensuite uniquement ces preuves, sans changement du JAR ni des scripts exécutés. `manifest.json` contient le head source, les blobs Git et SHA-256 des sources/scripts, le SHA-256 du JAR, les hashes de chaque JAR copié et des fichiers exportés. `minecraft-proof.sha256` vérifie l'archive compacte ; son `evidence_manifest.json` contient la même liste. Les mondes binaires et dépendances restent conservés localement, sans gonfler l'archive.

Archive : 41 527 828 octets, 3 350 entrées de preuves, SHA-256 `d3bed7f30e04a2d8daa42e30e41912338e2c76beb9be7576d356ca76682eb84d`. Les 22 JAR copiés portent tous le hash testé `a427a921eac3dcc19dbc909da30235ce4e297ddfe4cc6e06e2ffdf1341af0198`. Chaque entrée, taille/hash et manifeste interne a été vérifié ; les artefacts référencés par les rapports/protocoles et journaux workers sont inclus transitivement. Seuls les snapshots redondants propres aux polls de status sont omis de l'export, jamais des traces de simulation ; les originaux restent locaux.

```powershell
(Get-FileHash ./minecraft-proof.zip -Algorithm SHA256).Hash.ToLower() -eq (Get-Content ./minecraft-proof.sha256).Split(' ')[0]
```

Racine finale : `app/controller/.runtime/tests-13fe1ab978bd40ce8ebd05cfc92725ca`. Monde de travail : MCP 19465/19466, jeu 26281/26282. Copies : MCP 19467/19468 et 19471/19472, jeu 26283/26284 et 26287/26288. Bibliothèques, cache Fabric, mondes, artefacts et JVM sont propres à chaque copie ; les caches source sont seulement lus ou copiés.

```powershell
./scripts/build.ps1 -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -CacheSource C:/Users/minle/.codex/worktrees/issue-7/StoneBench/app/controller/.runtime -Offline
$env:STONEBENCH_VERIFICATION_EVIDENCE='<worktree>/app/controller/.runtime/verification-summary.json'
./scripts/test-server.ps1 -Suite tests/verification.py -AcceptEula -SkipBuild -UseCheckpointSupervisor -Java 'C:/Program Files/Java/jdk-21.0.12/bin/java.exe' -Python C:/Users/minle/.codex/worktrees/issue-5/StoneBench/app/controller/.runtime/test-venv/Scripts/python.exe -ServerCacheSource C:/Users/minle/Documents/projets/StoneBench/app/prototype-transition/.runtime/server-cache -BaseMcpPort 19465 -BaseGamePort 26281
```

## Contrôles et portée

La fixture naturelle est une vraie regular DOOR 2×2 quartz, quatre pistons collants, leviers et câblage vanilla, sans torche/inverseur. Une interaction vanilla établit l'état0 fermé avec levier actif ; la préparation sur la copie répéteur désactive temporairement l'entrée, pose l'adaptateur, réactive et prouve le retour exact de construction avant les cycles mesurés. Ses ticks/horloges sont archivés séparément. Les deux copies passent le contrôle de reprise gelée tick0, puis les états ouverts/fermés, repos et traces réels. Les durées peuvent différer entre entrée directe et répéteur.

Les scénarios `recurrence2`, `no_return5`, `direct_block`, `direct_inventory`, `direct_internal` et `bad_open` injectent des fautes **test-only sur les vraies copies Minecraft**. Ils exercent le protocole MCP livré, sans réimplémentation ni rapport fabriqué. Ils ne prouvent pas une récurrence naturelle de deux cycles. Les opérations exactes injectées et transitions supplémentaires bornées sont archivées. Les hooks sont absents/refusés en production.

Le contrôle `publication_failure` provoque une véritable erreur IO de publication atomique : diagnostic explicite, aucun job actif, snapshot identique et avancement ultérieur accepté. `publish_watchdog` pause après un verdict provisoire positif : le vrai watchdog du propriétaire écrit d'abord une annulation durable avec raison de phase, puis le résultat et son éventuel rapport tardif sont tous deux infrastructure/non conformes. Le test contrôle le marker, la gate et les deux publications réelles. Les interruptions couvrent aussi annulation pendant le boot d'un worker et terminaison du PID appartenant précisément à la requête ; chaque résultat conserve exactement le monde de travail. Aucun budget global walltime/ticks n'est ajouté : heartbeat de propriétaire 90s, watchdogs individuels, transitions 36000 ticks, maximum protocolaire dérivé 432000 ticks.

Les fichiers `fixture-*-failure.txt` et `heartbeat-sharing-failure.txt` sont des diagnostics historiques conservés, **pas** les preuves du head final : géométrie refusée pour fixture incomplète, câblage instable/crossfeed/atténuation, puis collision de remplacement de heartbeat Windows corrigée. `checkpoint-regression.txt` conserve la régression réelle #10 effectuée avant les derniers hooks/fixes ; les preuves de reprise exactes du head final sont celles de la suite finale.

Les huit tests du comparateur/protocole et neuf tests du stockage/recovery passent. La couverture positive indique explicitement `restorable_observed_scope=true`, `uncovered_components=[]` et les limites générales `universal_capture=false` ; provenance mémoire manquante/gappée, scope incomplet et trace incomplète ont des contrôles négatifs indéterminés. Le build vérifie aussi les contrôles Java checkpoint/géométrie/entrée/observation/repos/streaming. La suite finale et son bilan sont consignés dans `minecraft-tests.txt` et `verification-summary.json` de l'archive. La suite intermédiaire `7c6b54c` a été volontairement arrêtée pour incorporer le blocker de publication avant répétition finale ; son log distinct ne représente pas un échec spontané du protocole.

Suite MCP finale : **OK, 594,394 secondes**. Les deux positifs naturels arrêtent au premier cycle : répéteur 7+7 ticks, direct 5+5 ticks, 24 ticks protocolaires. Préparations exclues de ce compte.

| Contrôle injecté | Cycles répéteur | Ticks de transitions | Verdict attendu obtenu |
|---|---:|---:|---|
| Récurrence 2 | 2 | 41 | retour au cycle 2 |
| Aucun retour 5 | 5 | 86 | échec |
| Bloc direct divergent | 1 | 26 | échec |
| Inventaire direct divergent | 1 | 26 | échec |
| Champ interne direct divergent | 1 | 26 | échec |
| Ouverture incorrecte | 1 | 25 | échec de borne |
| Publication tardive/watchdog | 1 | 24 avant annulation | infrastructure, jamais conforme |

## Limites transmises à #13 et #14

Un snapshot géométrique seul reste indéterminé. Le vérificateur compose les critères individuels avec des preuves temporelles réelles ; la frame fermée du même mécanisme fonde arrangement/matériau à l'ouverture. Quartz identité seulement ; substitution non-quartz sans preuve, mémoire hopper/torch non couverte et tout mandatory indeterminate restent non conformes. Aucune garantie universelle de mémoire JVM ou de fiabilité indéfinie.

#13 reçoit les limites de transition, ticks, horloges absolues, temps réel, repos et références de traces. Volume dynamique et fin de mouvement au sens des sources ne sont pas encore certifiés. #14 peut soumettre le checkpoint explicite, suivre/annuler le job et récupérer le rapport/artefacts sans modifier la construction de travail. Aucun appel modèle ni boucle propriétaire ajouté.
