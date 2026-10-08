# Checkpoint statique — prototype jetable

Question : une sauvegarde Minecraft Java 1.21.11, prise au repos, permet-elle de
retrouver le même état et de reproduire exactement un cycle redstone ?

## Lancement

Depuis la racine de StoneBench, avec PowerShell 7 et Java 21 ou supérieur :

```powershell
pwsh -File app/prototype-checkpoint/run.ps1
```

Pour choisir un JDK :

```powershell
pwsh -File app/prototype-checkpoint/run.ps1 -Java 'C:/chemin/jdk/bin/java.exe'
```

Le script compile le mod, télécharge Gradle et le lanceur Fabric si nécessaire,
crée une nouvelle instance dans `.runtime/experiment-*`, puis exécute les quatre
séquences. Les fichiers Minecraft restent soumis à l'[EULA Minecraft](https://www.minecraft.net/eula) ;
le script configure `eula=true` pour lancer cette instance locale.
Il n'utilise aucun monde existant. Le serveur écoute uniquement sur
`127.0.0.1:25579`, avec une whitelist vide et sans RCON. Ce port doit être libre.

Versions : Minecraft **1.21.11**, Yarn **1.21.11+build.3**, Fabric Loader
**0.19.5**, lanceur Fabric **1.1.2**, Loom **1.14.10**, Gradle **9.2.1**.
Pas de Fabric API, de client Minecraft, de modèle ou de MCP requis.

## Expérience

Le monde plat utilise la seed `731928`. Le chunk `(0,0)` reste chargé.
La zone observée est `x=0..9, y=79..82, z=0..5` ; son sol est en pierre.
Un levier en `(1,80,1)` alimente un répéteur avec `facing=west` (sortie vers l'est), délai 2, puis un piston
collant orienté est en `(3,80,1)`, poussant une pierre en `(4,80,1)`.
Un coffre en `(7,80,3)` contient sept diamants dans son premier emplacement.

1. Le mod gèle le serveur **avant le chargement du monde**, à chaque démarrage.
2. `sb prepare` place le montage et avance de 20 ticks pour terminer sa préparation.
   Avant d'autoriser la sauvegarde, il vérifie l'absence de piston mobile,
   de ticks de blocs/fluides et d'événements de blocs en attente dans la zone.
3. Le script attend l'accusé de `save-all flush`, puis copie le monde gelé.
   Le verrou de processus `session.lock` est exclu ; Minecraft le recrée au lancement.
4. `sb record reference` enregistre l'état initial, actionne le levier par
   `LeverBlock.togglePower`, avance de 40 ticks, actionne le levier à nouveau,
   puis avance de 40 ticks. Le piston doit s'étendre et ramener la pierre.
5. Le script arrête le serveur et remplace uniquement le monde de cette instance
   jetable par la sauvegarde. Trois démarrages rejouent la même séquence,
   sans reconstruire le montage ni remettre l'heure à zéro.

La référence continue dans le serveur qui a créé le checkpoint. Elle n'est pas
elle-même issue d'un redémarrage. La sauvegarde est copiée avant son activation.
Les interactions sont injectées dans le thread serveur à la même frontière de
tick pour chaque séquence ; ce prototype n'étudie pas le placement par joueur.

## Observations et verdict

Chaque fichier JSONL contient **83 observations** : état initial, activation,
40 ticks, désactivation et 40 ticks. Chaque observation conserve :

- Les 240 états de blocs de la zone, air compris.
- Le NBT complet sérialisé des block entities, avec types numériques, inventaires,
  positions et champs temporels. Seules les clés des compounds non ordonnés sont
  triées ; l'ordre des listes est conservé.
- Les ticks de blocs et de fluides programmés : position, type, échéance absolue,
  priorité et ordre secondaire ; les événements de blocs en attente gardent leur ordre.
- L'heure totale du monde et l'heure du jour, sans normalisation.

Les traces sont prises après les ticks de monde, jamais au milieu de leur traitement.
L'instrumentation lit les ordonnanceurs de chunks chargés et la file
`ServerWorld.blockEventQueue` via des accessors Mixin de cette version exacte.
Il s'agit d'une observation des états sérialisés et des files pertinentes du montage,
pas d'une capture de toute la mémoire JVM ou des générateurs aléatoires du serveur.

Le dossier affiché en fin de lancement contient `reference.jsonl`, les trois
`replay-N.jsonl`, `verdict.json` et `verdict.md`. Les journaux de chaque démarrage
sont conservés dans le dossier de l'expérience. Une divergence produit un code
de sortie non nul **après** la rédaction du verdict, avec le premier tick et les
champs différents. Une erreur de fixture ou une trace incomplète ne peut pas donner
un verdict positif.

Pour refaire uniquement la comparaison :

```powershell
pwsh -File app/prototype-checkpoint/compare.ps1 -TraceDirectory 'C:/chemin/experience/server/traces'
```

Une réussite démontre uniquement la répétabilité de ce montage, avec cette
séquence et ces versions. Les checkpoints en mouvement, horloges internes,
autres composants, autres entrées et performances ne sont pas évalués.

## Résultat observé

Voir [RESULT.md](RESULT.md) pour le verdict obtenu lors du développement.
La branche dédiée `codex/prototype-checkpoint` conserve ce prototype ; il ne
constitue pas l'implémentation de production des checkpoints StoneBench.
