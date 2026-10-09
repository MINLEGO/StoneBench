# Résultat — 9 octobre 2026

**MC-172213 est reproduit sur Minecraft Java 1.21.11 sans joueur connecté.**
Les méthodes vanilla de levier et de bouton, appelées avant l'incrément du temps
du monde, reproduisent le tick de délai perdu. Un répéteur extérieur réel
transmet ensuite le signal dans la phase des ticks programmés.

## Résultats mesurés

La matrice retenue contient **72 cycles** : quatre montages, trois dispositifs,
deux modes et trois répétitions. Les **24 groupes de répétitions** ont les mêmes
traces pertinentes et les **12 paires de modes** ont des états intermédiaires et
finaux identiques. Chaque cycle revient à l'état initial de sa construction.
Le coffre conserve ses sept diamants ; ses données NBT participent aux comparaisons.

| Composant observé | Activation directe | Activation après répéteur | Désactivation directe par levier | Désactivation après répéteur |
| --- | ---: | ---: | ---: | ---: |
| Torche | 1 | 2 | 1 | 2 |
| Répéteur délai 1 | 1 | 2 | 1 | 2 |
| Répéteur délai 4 | 7 | 8 | 7 | 8 |
| Torche du mécanisme à piston | 1 | 2 | 1 | 2 |

Les valeurs sont des **ticks de simulation depuis le changement du signal au
bloc d'entrée**, avec la phase de ce changement enregistrée. Elles excluent
le délai de l'adaptateur extérieur. Les états et déplacements du piston sont
également tracés ; la dernière ligne mesure sa torche de commande, pas le
temps d'ouverture d'une porte.

Le relâchement naturel des boutons intervient pendant un tick programmé : il
conserve le délai nominal du composant observé, dans les deux modes. L'impulsion
au dispositif joueur dure **19 ticks pour la pierre et 29 pour le chêne**.
Le répéteur extérieur transmet l'activation après un tick et le relâchement
après deux ; l'impulsion au bloc d'entrée devient **20 ou 30 ticks**.
Aucune correction artificielle de durée ou de délai n'est appliquée.

## Conditions et correction du montage

Exécution réelle sous Windows, JDK Eclipse Adoptium **25.0.2**, Minecraft
**1.21.11**, Yarn **1.21.11+build.3**, Fabric Loader **0.19.5**, Loom **1.14.10**
et Gradle **9.2.1**. Le mod compile avec une cible Java 21. Les processus sont
isolés, gelés entre les pas unitaires, sans joueur, sur les ports locaux
25579 à 25582. Le chunk observé est forcé et sa disponibilité est contrôlée.

Les checkpoints initiaux sont copiés à froid après sauvegarde flushée et arrêt
du serveur. L'état observé doit être identique avant le premier tick de chaque
reprise. Les adaptateurs sont préparés à l'extérieur de la construction ; cette
préparation doit préserver son état initial.

La première campagne a validé les **54 cycles de torche et répéteurs**, mais
rejeté les 18 cycles à piston : la poussière avait été initialisée par
`getDefaultState`, en point non connecté. Le premier cycle la transformait en
ligne et empêchait le retour exact à l'état initial. Cette différence a été
conservée dans le diagnostic, sans normaliser les connexions de la poussière.

La préparation corrigée place les voisins avant la poussière et utilise
`RedstoneWireBlock.getPlacementState` avec un contexte vanilla de pose sur le
sol. Les **18 cycles à piston ont alors été rejoués et validés**. Les deux
compilations effectivement utilisées sont conservées dans l'archive ; la
correction ne concerne que la préparation du montage à piston.

## Preuves et contrôle négatif

- [RESULT.json](RESULT.json) : verdict complet, délais, répétabilité et comparaison des modes.
- [EVIDENCE.zip](EVIDENCE.zip) : 72 traces complètes, résultats, checkpoints observés, journaux et les deux mods exécutés ; 1 068 509 octets.
- [EVIDENCE.json](EVIDENCE.json) : versions, origine des deux campagnes et SHA-256 des fichiers et de l'archive.
- [NEGATIVE_CONTROL.json](NEGATIVE_CONTROL.json) : refus d'une altération limitée à l'observation initiale d'une trace.

L'archive a été extraite, tous ses fichiers vérifiés par SHA-256, puis acceptée
par le comparateur. Sur cette seule copie extraite, le nombre de diamants du
coffre `(5,80,4)` a été changé de sept à huit dans la première observation de
`torch-lever-direct-1`. Le comparateur a refusé cette trace avec :

```text
torch-lever-direct-1 : initial trace differs from checkpoint
```

Les campagnes originales et l'archive publiée restent inchangées. Pour refaire
l'analyse des preuves, depuis la racine du dépôt :

```powershell
Expand-Archive app/prototype-input/EVIDENCE.zip app/prototype-input/.runtime/evidence-copy
pwsh -File app/prototype-input/compare.ps1 -ExperimentDirectory app/prototype-input/.runtime/evidence-copy
```

Les horloges globales restent enregistrées séparément. Pour comparer les traces
entre répétitions, les échéances programmées sont exprimées relativement à
l'entrée initiale, car l'attente de disponibilité du chunk peut varier.
L'ordre des événements, les priorités et tous les champs NBT sont conservés.
Aucun champ interne de construction n'est normalisé pour obtenir l'égalité.

## Limites

La preuve couvre ces montages isolés et le mécanisme temporel de l'entrée joueur.
Elle ne valide pas un paquet reçu depuis un client réel, tous les composants du
ticket, tous les états internes JVM ni une construction arbitraire. Le cycle à
piston ne certifie pas les critères géométriques d'une porte StoneBench.
Le tick de reconnaissance du repos reste distinct du dernier mouvement.
Aucune API MCP ni règle de conformité de production n'est ajoutée.
