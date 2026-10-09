# Entrées directe et par répéteur — prototype jetable

Question : peut-on reproduire [MC-172213](https://bugs.mojang.com/browse/MC/issues/MC-172213)
sans joueur, puis obtenir les mêmes états de construction par les deux modes ?

## Lancement

Depuis la racine, avec PowerShell 7 et un JDK 21 ou supérieur :

```powershell
pwsh -File app/prototype-input/run.ps1
```

`-Java 'C:/chemin/jdk/bin/java.exe'` permet de choisir le JDK. Le lanceur
accepte aussi `-Fixtures piston` pour rejouer uniquement les cas d'un montage.
Sans ce paramètre, les quatre montages sont exécutés et contrôlés.
Le lanceur
réutilise les dépendances de `prototype-checkpoint/.runtime` et, lorsqu'il existe,
le cache serveur de `prototype-transition/.runtime`. Sans ces caches, les
dépendances officielles sont téléchargées. Les sources des prototypes précédents
ne sont pas modifiées.

Versions : Minecraft **1.21.11**, Yarn **1.21.11+build.3**, Loader **0.19.5**,
Loom **1.14.10**, Gradle **9.2.1**, lanceur Fabric **1.1.2**.
Les serveurs jetables utilisent `127.0.0.1:25579..25582`, une whitelist vide,
`online-mode=true`, aucun RCON et aucun joueur. Le lanceur configure `eula=true`
pour ces seules instances, soumises à l'[EULA Minecraft](https://www.minecraft.net/eula).

## Principe

Le serveur démarre gelé. Il attend que le chunk `(0,0)` soit prêt à traiter les
ticks, prépare le montage pendant 20 ticks, puis sauvegarde et arrête le monde.
Chaque essai utilise une nouvelle copie de ce checkpoint, sans `session.lock`.
L'état complet observé, horloges comprises, doit être identique avant le premier
tick. La construction doit rester identique pendant le chargement du chunk,
puis après 20 ticks de préparation de l'adaptateur.

Le bloc d'entrée en `(4,80,2)` est alimenté depuis l'ouest :

- **Direct** : levier ou bouton mural en `(3,80,2)`, fixé au bloc d'entrée.
- **Répéteur** : répéteur en `(3,80,2)`, `facing=west`, délai 1, sortie vers
  l'est ; il lit le bloc en `(2,80,2)`, alimenté par le dispositif mural en
  `(1,80,2)`.

Un mixin au début de `ServerWorld.tickTime` incrémente l'index de simulation,
puis appelle `LeverBlock.togglePower` ou `ButtonBlock.powerOn` avec un joueur
nul. Ces méthodes vanilla conservent leurs notifications, sons, événements et
ticks programmés. Aucun tick n'est ajouté ou retranché artificiellement.
Le répéteur extérieur est actionné uniquement par son alimentation vanilla.

Le ticket explique que les interactions joueur précèdent l'incrément du temps
du monde ; les événements programmés durant un tick utilisent déjà le temps
incrémenté. Un temps du monde seul masque la différence : les traces enregistrent
donc l'index de simulation **et la phase**, ainsi que l'heure du monde et les
échéances des événements. Les transitions de blocs sont observées à la sortie
de `World.setBlockState`, y compris celles pendant le tick programmé du répéteur.
Ce hook est observateur ; il ne modifie pas le monde.

## Montages et protocole

| Montage | Construction commune |
| --- | --- |
| `torch` | Torche redstone murale en `(5,80,2)`, fixée au bloc d'entrée. |
| `repeater-1` | Répéteur en `(5,80,2)`, sortie est, délai 1. |
| `repeater-4` | Même répéteur, délai 4. |
| `piston` | Torche, poussière en `(6,80,2)`, piston collant en `(7,80,2)` vers l'est et pierre initialement en `(8,80,2)`. Au repos initial, le piston est étendu et la pierre est en `(9,80,2)`. |

La poussière utilise `RedstoneWireBlock.getPlacementState` avec un contexte de
pose sur le sol, après la pose de ses voisins. Son état initial est ainsi la
ligne vanilla attendue, plutôt que le point non connecté de `getDefaultState`.

Chaque construction contient aussi un coffre en `(5,80,4)` avec sept diamants,
pour inclure un inventaire/NBT dans les comparaisons. La zone observée est
`x=0..10, y=79..82, z=0..5`, entièrement dans le chunk forcé. Les adaptateurs
occupent `x=0..3` ; la construction commune occupe `x=4..10`.

Les quatre montages sont exécutés avec levier, bouton en pierre et bouton en
chêne, dans les deux modes, trois fois chacun : **72 cycles et quatre checkpoints**.
Les trois répétitions d'un même cas s'exécutent en parallèle, dans des processus
et mondes indépendants sur les ports 25580, 25581 et 25582. La préparation des
checkpoints utilise le port 25579. Ces ports doivent être libres.
Le levier est désactivé au tick suivant la reconnaissance de l'état alimenté
au repos. Les boutons se relâchent naturellement : aucune désactivation manuelle
ni compensation de leur durée n'est appliquée.
L'impulsion mesurée au dispositif joueur est de 19 ticks pour la pierre et
29 pour le chêne. Le répéteur extérieur transmet l'activation après un tick de
simulation, mais le relâchement programmé après deux : les impulsions au bloc
d'entrée deviennent naturellement 20 et 30 ticks. Le comparateur contrôle
ces différences, au lieu de forcer une durée commune.

Une borne intermédiaire exige une construction inchangée entre deux observations,
sans tick de construction en attente, événement de bloc ou piston mobile. Le
tick de relâchement du bouton extérieur reste autorisé à cette borne. La borne
finale exige aussi le repos de l'adaptateur. Chaque transition est limitée à
36 000 ticks de simulation. Les opérations du lanceur ont une sécurité distincte
de 600 secondes réelles ; l'attente initiale du chunk est bornée à 60 secondes.

## Traces et comparaison

L'expérience reste dans `.runtime/experiment-*`. Chaque cas contient le monde,
le journal serveur et `traces/<cas>.jsonl` ainsi que `<cas>.result.json`.
Les observations complètes contiennent les blocs, les NBT typés, les files de
ticks de blocs/fluides et les événements de blocs. L'ordre des listes et des
événements est conservé ; seules les clés des compounds NBT sont triées.
Les adaptateurs sont enregistrés dans un champ séparé.

```powershell
pwsh -File app/prototype-input/compare.ps1 -ExperimentDirectory 'C:/chemin/experience'
```

Le comparateur vérifie la continuité des ticks, la concordance des événements
avec les observations, les phases d'entrée, les délais propres aux composants,
la durée des impulsions, la répétabilité et l'égalité des bornes entre modes.
Il produit `verdict.json` et `verdict.md`. Le lanceur échoue si le verdict est
négatif. Les preuves de `EVIDENCE.zip` s'analysent après extraction, comme
indiqué dans `RESULT.md`.

Pour les comparaisons de construction, seuls les adaptateurs et les horloges
globales sont séparés. Pour comparer les traces entre répétitions, les échéances
des ticks programmés sont exprimées relativement à l'heure de l'entrée initiale :
l'attente du chunk peut varier. Les échéances absolues restent dans les traces ;
leurs relations aux phases et à l'heure du monde sont contrôlées séparément.
Priorités, ordre et tous les champs NBT internes sont conservés. Voir `RESULT.md`
pour les observations réelles et les preuves conservées.

## Limites

Prototype limité à ces montages sans entités. Il reproduit le mécanisme temporel
de l'entrée joueur ; aucun client réseau réel n'est validé. Le bouton en bois
est représenté par le bouton en chêne. La preuve ne couvre pas tous les composants
du ticket ni toutes les constructions possibles. Le petit cycle à piston ne
constitue pas une certification géométrique de porte StoneBench.
Le tick de reconnaissance du repos reste distinct du dernier mouvement.
Aucune API MCP, normalisation d'état interne ou implémentation de production
n'est ajoutée. La branche `codex/prototype-input` conserve ce prototype jetable.
