# Résultat du prototype — 8 octobre 2026

**Les 21 expériences réelles satisfont les critères prévus.** Pour chaque
montage, les trois répétitions donnent le même verdict et le même tick de
reconnaissance. Les neuf fins reconnues ont été restaurées dans une copie
indépendante et restent inchangées pendant 200 ticks supplémentaires.

## Résultats

| Montage | Répétitions | Verdict | Tick de reconnaissance |
| --- | ---: | --- | ---: |
| Activation du piston | 3 | Terminée | 7 |
| Désactivation du piston | 3 | Terminée | 7 |
| Chaîne de trois répéteurs | 3 | Terminée | 27 |
| Hopper avec cooldown et trois diamants | 3 | Indéterminée | 32 |
| Hopper vide verrouillé | 3 | Indéterminée | 1 |
| Hopper vide déverrouillé | 3 | Indéterminée | 1 |
| Horloge de deux observers | 3 | Plafond atteint | 36 000 |

- Chaque transition de piston simple comporte trois ticks sans changement de
  blocs avec un événement encore programmé, puis deux observations de pistons
  mobiles. Le détecteur attend leur disparition et une observation identique.
- La chaîne de répéteurs comporte **21 ticks sans changement visible avec un
  événement en attente**. Les répéteurs agissent aux ticks 8, 16 et 24 ; le
  dernier mouvement se termine au tick 26 et le repos est reconnu au tick 27.
- Les trois diamants passent du hopper au coffre aux ticks **8, 16 et 24**.
  Les files de ticks et d'événements de blocs sont vides pendant ces transferts.
  Le dernier cooldown expire au tick 32. Le champ en mémoire `lastTickTime`
  continue ensuite de changer : le prototype conserve le verdict indéterminé.
- Les hoppers vides, verrouillés ou déverrouillés, gardent leurs inventaires
  inchangés, mais actualisent aussi `lastTickTime`. Leur suivi diagnostique de
  200 ticks confirme cette évolution ; aucun champ interne n'est normalisé.
- Chaque horloge présente **18 000 changements de blocs** et un tick programmé
  en attente à chacune des **36 000 observations**. Les 18 000 pauses visuelles
  restantes ne provoquent aucune fausse fin.

## Conditions et preuves

Exécution réelle sous Windows avec Java 25, Minecraft Java 1.21.11, Yarn
1.21.11+build.3, Fabric Loader 0.19.5, Loom 1.14.10 et Gradle 9.2.1.
Commande exécutée depuis la racine :

```powershell
pwsh -File app/prototype-transition/run.ps1
```

Les mondes, copies de vérification, journaux et traces brutes sont conservés
localement dans `.runtime/experiment-20261008-230001-7107f8ed/`.
Le verdict complet figure dans [RESULT.json](RESULT.json). Les empreintes du
mod exécuté et des 21 traces et résultats sont dans [EVIDENCE.json](EVIDENCE.json).
Les données volumineuses et dépendances restent hors Git ; le lanceur permet
de reproduire toute l'expérience.

L'instrumentation vérifie la disponibilité des ticks de blocs et des block
entities avant de préparer chaque montage, puis à chaque tick mesuré. Un chunk
simplement chargé ne suffit pas : une première expérience non retenue a montré
un tick de répéteur exécuté en retard pendant l'initialisation d'un chunk.
L'attente de disponibilité est distincte de la transition mesurée.

Les copies des fins reconnues retrouvent l'état pertinent avant leur premier
tick. Leur état reste contrôlé pendant la remise en disponibilité du chunk,
puis pendant les 200 ticks tracés. Les originaux sauvegardés ne sont pas avancés.

Le comparateur vérifie les traces continues, les positions finales du piston
et de la pierre, les transferts aux ticks attendus, les copies et la concordance
des trois répétitions. Un contrôle négatif sur une copie des traces a remplacé
la cause du tick 1 de `piston-open-1` par `quiescent`, alors qu'un tick de
répéteur restait programmé. Le comparateur refuse cette fausse fin et indique
`piston-open-1 : invalid or skipped trace ticks`.

## Décision retenue et limites

Pour ces montages, les files pertinentes vides, l'absence de piston mobile et
deux états pertinents consécutifs identiques permettent de reconnaître le repos.
L'égalité visuelle seule ne suffit pas. L'activité hors des files doit également
être observée ; le hopper avec cooldown en fournit un cas réel.

La lecture NBT seule ne capture pas `lastTickTime` du hopper dans cette version.
Sans expérience justifiant son traitement ou sa normalisation, le prototype
refuse de certifier l'immobilité de son état interne, même lorsqu'il est verrouillé.
Ce verdict ne démontre pas une défaillance fonctionnelle du hopper.

La couverture reste limitée à ces fixtures isolées, sans entités ou composants
aléatoires. Le suivi de 200 ticks n'est pas une preuve universelle d'immobilité.
Le tick de reconnaissance peut suivre le dernier mouvement d'un tick : il ne
définit pas le temps d'ouverture ou de fermeture du référentiel. Aucune API,
règle de conformité ou implémentation de production n'est ajoutée.

La branche `codex/prototype-transition` conserve ce prototype jetable comme
source primaire ; le prototype de checkpoint existant reste inchangé.
