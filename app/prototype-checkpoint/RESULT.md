# Résultat du prototype — 8 octobre 2026

**Le checkpoint statique a été restauré et le cycle reproduit à l'identique dans
les trois reprises.** Les quatre fichiers de trace sont également identiques
octet pour octet, y compris les horloges et les champs NBT.

## Conditions

Exécution réelle sous Windows avec Java 25, Minecraft Java 1.21.11, Fabric Loader
0.19.5 et le mod de cette branche. Commande exécutée depuis ce dossier :

```powershell
./run.ps1
```

Expérience conservée localement dans :
`.runtime/experiment-20261008-214930-6a3ee7e6/`.
Les traces et le verdict détaillé se trouvent dans `server/traces/` ; les quatre
journaux de console sont au niveau du dossier de l'expérience.

## Observations

| Exécution | État initial | Trace de l'exécution |
| --- | --- | --- |
| Référence, sans redémarrage après sauvegarde | Temps monde 20 | 83 observations, jusqu'au temps monde 100 |
| Reprise 1 | Identique à la référence | Identique |
| Reprise 2 | Identique à la référence | Identique |
| Reprise 3 | Identique à la référence | Identique |

Chaque séquence comprend 80 ticks observés et deux interactions de levier.
Huit observations contiennent des ticks de blocs programmés et quatre contiennent
des pistons mobiles. Le piston s'étend avant la seconde interaction, puis ramène
la pierre. Le coffre conserve ses sept diamants.

Les quatre traces font chacune **1 027 351 octets** et ont le même SHA-256 :

```text
6af0db4127fdba6000719db570ef4c4e75e926b320206dd0016163053be52a97
```

Le contrôle négatif manuel a modifié uniquement le nombre de diamants dans une
copie de la première observation. Le comparateur a refusé l'égalité et indiqué :

```text
tick 0, événement initial
$.state.blocks[177].nbt.value.Items.value[0].value.count.value
attendu : 7 ; obtenu : 8
```

## Conclusion retenue

La sauvegarde flushée et le rechargement du monde, gelé avant son chargement,
suffisent à reproduire ce cycle depuis ce montage statique. La référence est
bien une continuation du serveur d'origine, pas un quatrième rechargement.
Le verrou Windows `session.lock` est exclu de la copie et recréé au lancement.

Ce résultat justifie de poursuivre les expériences avec d'autres montages au
repos. Il ne valide pas les checkpoints pendant un mouvement, les horloges
internes, tous les composants vanilla, l'intégralité de la mémoire du serveur
ou les performances. Aucun mécanisme de restauration en production n'est ajouté
à StoneBench par ce prototype.
