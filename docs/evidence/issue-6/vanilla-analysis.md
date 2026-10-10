# Analyse vanilla 1.21.11 : callbacks et préparation des chunks

Cette note relève les signatures et le comportement du binaire Minecraft utilisé par l’issue #6. Elle ne modifie aucun code Java et ne revendique pas un build ni un test serveur.

## Provenance

Le contrôleur issue-6 déclare Minecraft `1.21.11` et Yarn `1.21.11+build.3` dans `app/controller/build.gradle`. L’inspection a utilisé le jar nommé déjà présent dans le cache de la branche issue-5, avec les mêmes coordonnées de mapping :

```text
C:\Users\minle\.codex\worktrees\issue-5\StoneBench\app\controller\.runtime\gradle-home\caches\fabric-loom\minecraftMaven\net\minecraft\minecraft-merged\1.21.11-net.fabricmc.yarn.1_21_11.1.21.11+build.3-v2\minecraft-merged-1.21.11-net.fabricmc.yarn.1_21_11.1.21.11+build.3-v2.jar
SHA-256: 86588E7262508E391095CA9921161B83ED2AF79FAB38D4048E2C1759AA61E6B8
```

Les signatures et instructions ont été lues avec `C:\Program Files\Java\jdk-21.0.12\bin\javap.exe` (`-p`, `-c`, et `-constants`). Aucune source générée ni compilation n’a été nécessaire.

## `WorldChunk.setBlockState` et les callbacks

Les constantes `Block` du jar sont :

| Constante | Valeur | Effet pertinent |
| --- | ---: | --- |
| `NOTIFY_NEIGHBORS` | 1 | Active les notifications de voisins et la branche `onStateReplaced` de l’ancien état. |
| `NOTIFY_LISTENERS` | 2 | Active `World.updateListeners` si le chunk satisfait le niveau requis. |
| `FORCE_STATE` | 16 | Dans `World.setBlockState`, saute la séquence `prepare` / `updateNeighbors` / `prepare` avec profondeur. |
| `SKIP_DROPS` | 32 | Supprime le traitement de drops concerné par les flags. |
| `MOVED` | 64 | Passe `moved=true` et active aussi la branche `onStateReplaced`. |
| `SKIP_BLOCK_ENTITY_REPLACED_CALLBACK` | 256 | Supprime `BlockEntity.onBlockReplaced` lors du retrait d’un block entity remplacé. |
| `SKIP_BLOCK_ADDED_CALLBACK` | 512 | Supprime `BlockState.onBlockAdded`. |
| `FORCE_STATE_AND_SKIP_CALLBACKS_AND_DROPS` | 816 | Combinaison `16 + 32 + 256 + 512`. |

Signatures publiques des méthodes d’état :

```text
BlockState.onStateReplaced(ServerWorld, BlockPos, boolean moved)
BlockState.onBlockAdded(World, BlockPos, BlockState oldState, boolean moved)
```

`WorldChunk.setBlockState(BlockPos, BlockState, int)` écrit d’abord dans `ChunkSection` (offsets 64–86). Il retourne immédiatement si l’état n’a pas changé (offsets 78–85). Pour un changement réel, le bytecode établit `moved` depuis le bit 64 (offsets 344–356) et calcule si l’appel du callback de block entity est permis depuis l’absence du bit 256 (offsets 358–371).

Après le remplacement éventuel du block entity, l’ancien callback d’état est appelé côté serveur si le bit 1 est présent ou si `moved` vaut vrai (offsets 438–493). Cette branche est atteinte quand le bloc change d’identité **ou** quand l’ancien bloc est un `AbstractRailBlock`. Le nouvel état reçoit `onBlockAdded` côté serveur à moins que le bit 512 soit présent (offsets 514–545). Cette dernière règle couvre aussi un changement de propriétés qui conserve le même bloc.

Le retrait d’un ancien block entity et son callback sont distincts des deux callbacks d’état : si le nouvel état ne conserve pas le block entity, `WorldChunk` appelle `BlockEntity.onBlockReplaced` côté serveur quand le bit 256 est absent, puis retire le block entity (offsets 373–438). La méthode vanilla `BlockEntity.onBlockReplaced` appelle `ItemScatterer.spawn` lorsqu’il s’agit d’un `Inventory` et que le monde est défini. Le flag 256 supprime donc aussi cette dispersion d’inventaire; `SKIP_DROPS` seul ne remplace pas ce contrôle.

## Comportement de `World.setBlockState`

`World.setBlockState(pos, state, flags)` délègue à la surcharge à quatre arguments avec une profondeur maximale de 512. Cette surcharge appelle `WorldChunk.setBlockState`, puis, en cas de succès :

1. appelle `updateListeners` si le bit 2 est actif et si le niveau du chunk le permet;
2. avec le bit 1, appelle `updateNeighbors(pos, oldState.getBlock())`, puis met à jour les comparateurs lorsque le **nouvel** état fournit une sortie de comparateur;
3. sauf si `FORCE_STATE` est actif et si la profondeur restante est positive, appelle dans l’ordre `oldState.prepare`, `newState.updateNeighbors`, `newState.prepare` avec les flags de propagation dérivés et une profondeur décrémentée;
4. appelle toujours `World.onBlockStateChanged(pos, oldState, newState)` après les étapes précédentes. Dans `ServerWorld`, ce hook met à jour le stockage des points d’intérêt lorsque leur type change.

Ainsi, `FORCE_STATE_AND_SKIP_CALLBACKS_AND_DROPS` permet d’installer les états de tout un lot sans les callbacks d’état ni les notifications de voisins. Il supprime aussi les listeners, l’ancien callback de block entity et les drops associés. La création ou le retrait des block entities et leur ticker restent gérés par `WorldChunk`; un inventaire demandé peut être rempli après le placement de tous les états.

Pour rejouer les callbacks d’état ensuite, conserver l’ancien et le nouvel `BlockState` de chaque placement et traiter les placements dans l’ordre soumis. Avec `moved=false`, reproduire la condition vanilla de `onStateReplaced` : ancien bloc différent du nouveau, ou ancien bloc de type `AbstractRailBlock`. Appeler `onBlockAdded` pour chaque état réellement changé, y compris lorsque seule une de ses propriétés change. Pour un placement donné, l’ordre vanilla est ancien `onStateReplaced`, puis nouvel `onBlockAdded`.

La décision de rejouer ces deux callbacks doit être séparée de l’option de notifications de voisins si l’API veut permettre de construire sans voisins tout en conservant les effets propres à l’ajout/remplacement de blocs. Les deux notions sont distinctes dans vanilla : `onBlockAdded` est contrôlé par le bit 512; la propagation par le bit 1 et `FORCE_STATE`.

## Attente de chunks pendant une extension gelée

Les méthodes examinées montrent qu’une extension peut attendre la préparation sans avancer l’horloge du monde :

- `MinecraftServer.tick(BooleanSupplier)` appelle `tickWorlds` à chaque boucle serveur; `tickWorlds` appelle `ServerWorld.tick` pour chaque monde.
- `ServerWorld.tick` lit `TickManager.shouldTick`. Quand il est faux, il saute `tickTime`, les scheduled ticks de blocs/fluides, les raids et les événements de blocs synchronisés. `World.tickBlockEntities` lit aussi `shouldTick` et n’exécute aucun ticker si la valeur est fausse; l’itérateur d’entités utilise `TickManager.shouldSkipTick` pour sauter les entités non-joueurs gelées.
- `ServerWorld.tick` appelle quand même `ServerChunkManager.tick(BooleanSupplier, true)`.
- Quand `shouldTick` est faux et que le second argument vaut vrai, `ServerChunkManager.tick` saute `ChunkTicketManager.tick`, mais appelle toujours `updateChunks()` puis `ServerChunkLoadingManager.tick(...)`.
- `ServerChunkManager.updateChunks()` appelle `ChunkLevelManager.update(chunkLoadingManager)`, `ServerChunkLoadingManager.updateHolderMap()` et `ServerChunkLoadingManager.updateChunks()` à chaque boucle. Ce dernier traite la liste de loaders en attente.
- `ServerChunkManager.setChunkForced` délègue à `ChunkTicketManager.setChunkForced`; le ticket forcé est ajouté immédiatement et l’ajout appelle le `loadingLevelUpdater` lorsqu’il améliore le niveau du chunk. `ChunkLevelManager.update` applique ensuite ces mises à jour et fait évoluer les futurs des `ChunkHolder`.
- `ServerChunkManager.isTickingFutureReady(long)` n’est vrai que si `ServerWorld.shouldTickBlocksInChunk` l’est, qu’un `ChunkHolder` existe et que son `tickingFuture` contient un `WorldChunk` présent.

Le hook `afterTick` peut sonder le prédicat de readiness sur les boucles serveur suivantes tandis que le tick manager reste gelé. Le delta `world.getTime()` doit rester nul pendant cette phase; il ne faut pas demander un `step(1)` pour attendre l’extension. Le timeout de l’opération reste nécessaire si les futurs n’atteignent jamais l’état prêt.

