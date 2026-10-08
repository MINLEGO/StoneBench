# Fin de transition — prototype jetable

Question : sur des montages Minecraft réels, peut-on distinguer une fin de
transition d'une pause visuelle, d'un piston encore mobile ou d'un transfert
différé de hopper ?

## Lancement

Depuis la racine, avec PowerShell 7 et Java 21 ou supérieur :

```powershell
pwsh -File app/prototype-transition/run.ps1
```

Un JDK peut être choisi avec `-Java 'C:/chemin/jdk/bin/java.exe'`.
Le lanceur télécharge les dépendances manquantes et réutilise leur cache dans
`../prototype-checkpoint/.runtime` s'il existe. Il ne modifie aucun fichier
source du prototype de checkpoint. Sans ce cache, il prépare son propre cache.
Les bibliothèques et fichiers Fabric sont ensuite mis en cache dans
`.runtime/server-cache` pour éviter leur téléchargement à chaque montage neuf.

Versions : Minecraft **1.21.11**, Yarn **1.21.11+build.3**, Fabric Loader
**0.19.5**, lanceur Fabric **1.1.2**, Loom **1.14.10**, Gradle **9.2.1**.
Le lancement configure `eula=true` pour ces seules instances jetables, soumises
à l'[EULA Minecraft](https://www.minecraft.net/eula).
Le port local `127.0.0.1:25579` doit être libre. Whitelist vide, aucun joueur,
aucun client Minecraft et aucun RCON. Aucun monde existant n'est utilisé.

## Protocole

Sept cas sont chacun exécutés trois fois dans un nouveau monde plat de seed
`731928`. Le chunk `(0,0)` reste chargé ; la zone observée est
`x=0..9, y=79..82, z=0..5` et son sol est en pierre.
Le contrôleur attend d'abord que le chunk soit chargé **et prêt à traiter les
ticks** (`shouldTickBlocksInChunk`, `isTickingFutureReady` et niveau
`BLOCK_TICKING` du chunk, ou supérieur). Cette attente est bornée à 60 secondes
réelles et ne fait pas partie de la transition mesurée.
Chaque montage se prépare ensuite pendant 20 ticks avant l'interaction observée.
La disponibilité reste contrôlée à chaque observation ; sa perte invalide le cas.

| Cas | Montage / interaction |
| --- | --- |
| `piston-open` | Levier, répéteur délai 2, piston collant et pierre ; activation. |
| `piston-close` | Même montage, initialement étendu ; désactivation. |
| `delayed` | Trois répéteurs délai 4 avant le piston ; activation. |
| `hopper-cooldown` | Trois diamants dans un hopper vers un coffre, cooldown initial de 8 ticks. |
| `hopper-locked` | Hopper vide alimenté par un bloc de redstone, sortie vers un coffre. |
| `hopper-empty` | Hopper vide déverrouillé, sortie vers un coffre. |
| `clock` | Deux observers face à face, laissés en oscillation. |

Le serveur est gelé avant le chargement du monde. Le contrôleur avance exactement
un tick à la fois et observe après `MinecraftServer.tickWorlds`, sur le thread
serveur. `tick rate 10000` accélère l'expérience sans remplacer ce pas unitaire.
La limite de transition est **36 000 ticks de jeu**, distincte du délai de
sécurité de 600 secondes réelles de chaque opération du lanceur.

## Décision

Le prototype lit les ticks de blocs/fluides des ordonnanceurs de chunks chargés,
la file des événements de blocs, les états de blocs, le NBT complet typé et
l'activité des pistons et hoppers. Il conserve l'ordre des événements et des
listes NBT ; seules les clés des compounds sont triées.

Une fin exige des files pertinentes vides, aucun piston mobile, aucune activité
différée identifiée et l'égalité de deux états pertinents consécutifs. Cette
égalité complète les contrôles d'activité : elle ne remplace pas ces contrôles.
Les horloges globales sont enregistrées séparément de cette égalité. **Aucun
champ NBT ou temporel interne n'est retiré.**

Pour les hoppers, deux accessors lisent aussi `transferCooldown` et
`lastTickTime` en mémoire. Le bytecode de la version nommée, inspecté avec
`javap -p -c`, montre que `serverTick` décrémente le cooldown et affecte
`lastTickTime` avant de vérifier si un transfert est possible. `writeData`
sérialise `TransferCooldown`, mais pas `lastTickTime`. Se limiter au NBT ne
capture donc pas tout cet état interne.

Les résultats sont :

- `terminated` : fin reconnue pour les montages sans composant incertain.
- `limit-reached` : activité toujours présente au tick 36 000.
- `indeterminate` : composant dont le repos complet n'est pas établi ; la cause
  est explicite. Les hoppers attendent leur cooldown et leurs transferts possibles
  avant ce résultat. Un hopper vide, même verrouillé, reste indéterminé car son
  `lastTickTime` évolue. Le prototype ne prétend pas que cela empêche une porte
  de fonctionner : il refuse de certifier l'immobilité de tout son état interne.

Une fin reconnue est sauvegardée avec `save-all flush`, puis le serveur est
arrêté. Le monde est copié dans `verification-world`, sans `session.lock`.
L'original est conservé. La copie redémarre gelée, doit retrouver l'état pertinent
de détection avant son premier tick. L'état reste aussi contrôlé pendant l'attente
de disponibilité du chunk, puis pendant **200 ticks** supplémentaires tracés.
La durée de cette attente est enregistrée dans `warmupTicks`.
Le premier changement provoque une erreur. Les cas indéterminés sont suivis
pendant 200 ticks supplémentaires dans leur monde d'origine, à titre diagnostique.

## Traces et verdict

Le chemin de l'expérience est affiché au lancement. Chaque sous-dossier de cas
contient le monde, les journaux de console et `traces/` :

- `<cas>-<répétition>.jsonl` : état complet initial, puis blocs changés par tick,
  horloges, files complètes et cause de décision. Les blocs inchangés se
  reconstruisent à partir de l'observation précédente.
- `*.result.json` : verdict, tick de décision, état complet à la décision et
  compteurs des situations effectivement rencontrées.
- `*.verification.jsonl` et `*.verification.json` : suivi de la copie pour les
  seules fins reconnues.

`compare.ps1` contrôle les 21 résultats, la continuité des traces, les montages
attendus, les transferts, l'oscillation, le suivi des copies et la concordance du
résultat et du tick entre répétitions. Il écrit `verdict.json` et `verdict.md` ;
le lanceur échoue si les critères ne sont pas satisfaits. Une erreur serveur ou
une trace incomplète ne peut pas produire un verdict positif.

Pour refaire uniquement l'analyse :

```powershell
pwsh -File app/prototype-transition/compare.ps1 -ExperimentDirectory 'C:/chemin/experience'
```

Voir [RESULT.md](RESULT.md) pour les résultats réellement obtenus. La branche
`codex/prototype-transition` conserve l'expérience comme source primaire.

## Limites

Le détecteur est limité à ces fixtures isolées, sans entités, composants
aléatoires ou influence extérieure. Les files sont filtrées dans la zone ; ce
n'est pas un détecteur pour une construction arbitraire connectée hors zone.
L'observation ne couvre pas toute la mémoire JVM. Le suivi de 200 ticks est
une vérification bornée, sans preuve universelle de repos. Aucun benchmark ni
critère géométrique de conformité des portes StoneBench n'est ajouté.

La distinction entre fin du mouvement et tick de reconnaissance est conservée :
l'égalité entre états consécutifs peut reconnaître la fin un tick après le dernier
changement. Ce tick de reconnaissance ne définit pas le temps d'ouverture ou de
fermeture du référentiel. Aucun champ interne n'est normalisé et aucune API de
production n'est introduite.
